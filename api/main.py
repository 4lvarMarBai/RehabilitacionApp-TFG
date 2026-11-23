"""Operaciones HTTP y validaciones de permisos antes de acceder a los datos."""

import logging
import secrets
from datetime import datetime, UTC
from threading import BoundedSemaphore

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.access import clinical_scope, log_access
from psycopg_pool import PoolTimeout

from servidor import clinician_leave
from servidor import auth
from servidor import catalogos as cat
from servidor import services as svc
from servidor.ai_clinical import OllamaError, OllamaTimeoutError
from api.db import get_conn, lifespan
from api.pagination import paginate_query
from api.queries import read_table
from api.schemas import (
    AreaCreate,
    AreaState,
    Assignment,
    Consent,
    Discharge,
    Login,
    PasswordChange,
    SpecialtyCreate,
    SpecialtyState,
    TreatmentSession,
    UserCreate,
    WaitingRequest,
    ProfessionCreate,
    ProfessionState,
    ClinicianLeave,
    TreatmentReassignment,
)
from api.schemas import AISummaryRequest
from servidor.ai_policy import (
    ai_use_mode, clinical_consent_version, require_summary_mode,
    PROMPT_VERSION, CLINICAL_PROMPT_VERSION, digest,
)
from api.security import (
    admin_user,
    medical_user,
    request_author,
    care_user,
    bearer,
    current_user,
    issue_session,
    limit_login,
    ready_user,
    token_hash,
)
from api.serialization import encode, table
from comun.roles import can_use_ai_summary, role_for_profession
from servidor.database import fetch_all, iso_utc_from_date
from comun.validators import (
    is_valid_dni,
    validar_hora_sesion,
    validar_preferencias_tratamiento,
)


app = FastAPI(title="API de Rehabilitación", version="1.0.0", lifespan=lifespan)
logger = logging.getLogger("rehabilitacion.api")
ai_slot = BoundedSemaphore(1)


@app.exception_handler(RequestValidationError)
async def invalid_input(_request: Request, exc: RequestValidationError):
    # No incluir contraseñas ni textos clínicos del cuerpo en los errores.
    errors = [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(psycopg.Error)
@app.exception_handler(PoolTimeout)
async def database_error(_request: Request, exc: Exception):
    logger.error("Database operation failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "La base de datos no está disponible. Consulta al administrador."
        },
    )


@app.exception_handler(ValueError)
async def invalid_operation(_request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(svc.DuplicateRequestError)
async def duplicate_request(_request: Request, exc: svc.DuplicateRequestError):
    return JSONResponse(status_code=409, content={"detail": {
        "code": "DUPLICATE_REQUEST",
        "message": str(exc),
        "duplicates": exc.duplicates,
    }})


@app.exception_handler(PermissionError)
async def forbidden_operation(_request: Request, exc: PermissionError):
    record_denial(_request, 403)
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(OllamaTimeoutError)
async def ai_timeout(_request: Request, _exc: OllamaTimeoutError):
    return JSONResponse(
        status_code=504,
        content={
            "detail": "Ollama tardó demasiado en generar el informe. Vuelve a intentarlo más tarde."
        },
    )


@app.exception_handler(OllamaError)
async def ai_error(_request: Request, _exc: OllamaError):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Ollama no está disponible en el servidor. Consulta al administrador."
        },
    )


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception):
    logger.error("Unhandled API error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500, content={"detail": "No se pudo completar la operación."}
    )


def treatment(conn, rehab_id: int, *, active=False, viewer=None):
    scope, scope_params = clinical_scope(viewer or {})
    lock = " FOR UPDATE" if active else ""
    columns, rows = fetch_all(conn, f"""
        WITH selected AS (
            SELECT * FROM rehab_active WHERE id = %s AND ({scope}){lock}
        ), visited AS (
            INSERT INTO clinical_visit_log (clinician_dni, patient_id, visit_date)
            SELECT %s, patient_id, (NOW() AT TIME ZONE 'Europe/Madrid')::date FROM selected
            ON CONFLICT DO NOTHING
        ), audited AS (
            INSERT INTO security_access_log(actor, action, outcome, rehab_active_id, patient_id)
            SELECT %s, 'LECTURA_TRATAMIENTO', 'PERMITIDO', id, patient_id FROM selected
        )
        SELECT * FROM selected
    """, (rehab_id, *scope_params, viewer["dni"], viewer["dni"]))
    if not rows:
        raise HTTPException(403, "No tienes acceso a este tratamiento o ya no está disponible.")
    result = dict(zip(columns, rows[0]))
    if active and result["status"] != "ACTIVO":
        raise HTTPException(409, "El tratamiento ya no está activo.")
    return result


def record_denial(request, status):
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        return
    route = getattr(request.scope.get("route"), "path", "sin_ruta")
    user = getattr(request.state, "authenticated_user", None)
    try:
        rehab_id = int(request.path_params.get("rehab_id", ""))
        rehab_id = rehab_id if 0 < rehab_id < 2**63 else None
    except (ValueError, TypeError):
        rehab_id = None
    try:
        # Una conexión independiente conserva el rechazo aunque la operación se revierta.
        with pool.connection(timeout=5) as conn:
            log_access(conn, user, f"HTTP_{status}:{route}", "DENEGADO", rehab_id)
    except Exception:
        # Un fallo de registro nunca debe convertir una denegación en una entrega de datos.
        logger.error("No se pudo registrar un rechazo de acceso; no se entregaron datos.")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code in {401, 403, 429}:
        record_denial(request, exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(body: Login, request: Request, conn=Depends(get_conn)):
    username = body.username.strip()
    limit_login(conn, request, username)
    user = auth.authenticate_user(conn, username, body.password)
    if user is None:
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    token, expires_at = issue_session(conn, user["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": user,
    }


@app.get("/bootstrap")
def bootstrap(
    include_stats: bool = True,
    area_specialty: str | None = Query(default=None, min_length=1, max_length=150),
    user=Depends(current_user), conn=Depends(get_conn),
):
    # Una sola petición para autenticar y preparar la cabecera y los filtros.
    if user["must_change_password"]:
        return {"user": user}
    if user["role"] not in ("ADMIN", "CLINICO", "MEDICO"):
        raise HTTPException(403, "Rol no autorizado.")
    result = {
        "user": user,
        "ai_use_mode": ai_use_mode(),
        "specialties": encode(cat.get_especialidades(conn, only_active=False)),
    }
    if include_stats:
        waiting, active, discharged = svc.get_stats(conn)
        result["stats"] = {
            "waiting": waiting,
            "active": active,
            "discharged": discharged,
        }
    if area_specialty and any(
        name == area_specialty and requires_area and active
        for name, requires_area, active in result["specialties"]
    ):
        # El filtro lateral usa estas áreas en todas las secciones.
        result["areas"] = {
            "specialty_name": area_specialty,
            "rows": encode(cat.get_areas_por_especialidad(
                conn, area_specialty, only_active=False,
            )),
        }
    return result


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@app.post("/auth/logout")
def logout(
    credentials=Depends(bearer), _user=Depends(current_user), conn=Depends(get_conn)
):
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM api_sessions WHERE token_hash = %s",
            (token_hash(credentials.credentials),),
        )
    return {"ok": True}


@app.post("/auth/change-password")
def change_password(
    body: PasswordChange, user=Depends(current_user), conn=Depends(get_conn)
):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM users WHERE id = %s FOR UPDATE",
                (user["id"],),
            )
            stored_hash = cur.fetchone()[0]
        if not auth.verify_password(body.current_password, stored_hash):
            raise HTTPException(400, "La contraseña actual no es correcta.")
        if not body.new_password.strip() or auth.verify_password(
            body.new_password, stored_hash
        ):
            raise HTTPException(400, "Elige una contraseña diferente de la actual.")
        auth.change_user_password(conn, user["id"], body.new_password)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM api_sessions WHERE user_id = %s", (user["id"],))
    return {"ok": True, "message": "Contraseña actualizada. Inicia sesión de nuevo."}


@app.get("/stats")
def stats(_user=Depends(ready_user), conn=Depends(get_conn)):
    waiting, active, discharged = svc.get_stats(conn)
    return {"waiting": waiting, "active": active, "discharged": discharged}


@app.get("/catalog/specialties")
def specialties(
    only_active: bool = True, _user=Depends(ready_user), conn=Depends(get_conn)
):
    return encode(cat.get_especialidades(conn, only_active=only_active))


@app.get("/catalog/areas")
def areas(
    specialty_name: str = Query(min_length=1, max_length=150),
    only_active: bool = True,
    _user=Depends(ready_user),
    conn=Depends(get_conn),
):
    return encode(
        cat.get_areas_por_especialidad(conn, specialty_name, only_active=only_active)
    )


@app.get("/tables/{name}")
def tables(
    name: str,
    specialty: str | None = None,
    subspecialty: str | None = None,
    priority: str | None = None,
    eligible_only: bool = False,
    dni: str | None = None,
    patient_id: str | None = Query(default=None, pattern=r"^[0-9]{6}$"),
    event: str | None = Query(default=None, max_length=100),
    ai_consent: str | None = Query(
        default=None, pattern=r"^(accepted|rejected|missing)$"
    ),
    rehab_active_id: int | None = Query(default=None, ge=1),
    year: int | None = Query(default=None, ge=2020, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=1000, ge=1, le=5000),
    page: int | None = Query(default=None, ge=1, le=1_000_000_000),
    page_size: int = Query(default=50, ge=1, le=100),
    user=Depends(ready_user),
    conn=Depends(get_conn),
):
    result = read_table(
        conn,
        name,
        user,
        specialty=specialty,
        subspecialty=subspecialty,
        priority=priority,
        eligible_only=eligible_only,
        dni=dni,
        patient_id=patient_id,
        event=event,
        ai_consent=ai_consent,
        rehab_active_id=rehab_active_id,
        year=year,
        month=month,
        limit=limit,
        page=page,
        page_size=page_size,
    )
    return encode(result) if page is not None else table(result)


@app.get("/requests/preview")
def preview(
    specialty_filter: str | None = None,
    subspecialty_filter: str | None = None,
    slot_type_filter: str | None = None,
    time_preference_filter: str | None = None,
    transport_mode_filter: str | None = None,
    _user=Depends(ready_user),
    conn=Depends(get_conn),
):
    return encode(
        svc.preview_next_patient(
            conn,
            specialty_filter,
            subspecialty_filter,
            slot_type_filter,
            time_preference_filter,
            transport_mode_filter,
        )
    )


@app.post("/requests")
def create_request(
    body: WaitingRequest, user=Depends(request_author), conn=Depends(get_conn)
):
    error = validar_preferencias_tratamiento(
        body.slot_type, body.time_preference, body.transport_mode, body.preferred_hour
    )
    if error:
        raise HTTPException(400, error)
    specialties_active = {row[0]: bool(row[1]) for row in cat.get_especialidades(conn)}
    _, area_rows = fetch_all(
        conn,
        "SELECT specialty_name, name FROM subspecialties_config WHERE active = TRUE",
    )
    areas_by_specialty = {}
    for specialty_name, area_name in area_rows:
        areas_by_specialty.setdefault(specialty_name, set()).add(area_name)
    seen = set()
    for item in body.requests:
        if item.specialty not in specialties_active:
            raise HTTPException(400, "La especialidad no está activa.")
        key = (item.specialty, item.subspecialty)
        if key in seen:
            raise HTTPException(
                400, "Hay especialidades y áreas duplicadas en la solicitud."
            )
        seen.add(key)
        available_areas = areas_by_specialty.get(item.specialty, set())
        if (
            specialties_active[item.specialty]
            and item.subspecialty not in available_areas
        ):
            raise HTTPException(400, "Selecciona un área activa para esa especialidad.")
        if item.subspecialty and item.subspecialty not in available_areas:
            raise HTTPException(
                400, "El área no pertenece a esa especialidad o no está activa."
            )
    svc.add_waiting_patient_multiple(
        conn,
        patient_id=body.patient_id,
        priority_level=body.priority_level,
        requests=[item.model_dump() for item in body.requests],
        request_date_iso=iso_utc_from_date(body.request_date),
        eligible=body.eligible,
        actor=user["dni"],
        slot_type=body.slot_type,
        time_preference=body.time_preference,
        transport_mode=body.transport_mode,
        preferred_hour=body.preferred_hour,
        coordination_rule=body.coordination_rule,
        ai_consent_accepted=body.ai_consent_accepted,
        confirm_duplicate=body.confirm_duplicate,
    )
    return {"ok": True}


@app.post("/treatments/assign")
def assign(body: Assignment, user=Depends(care_user), conn=Depends(get_conn)):
    result = svc.assign_next_patient(
        conn,
        assigned_by=user["dni"],
        assigned_clinician_dni=user["dni"],
        assigned_clinician_name=user["full_name"],
        assigned_clinician_profession=user["profession"],
        specialty_filter=body.specialty_filter,
        subspecialty_filter=body.subspecialty_filter,
        attendance_days=body.attendance_days,
        slot_type_filter=body.slot_type_filter,
        time_preference_filter=body.time_preference_filter,
        transport_mode_filter=body.transport_mode_filter,
    )
    return encode(result)


@app.post("/treatments/{rehab_id}/discharge")
def discharge(
    rehab_id: int, body: Discharge, user=Depends(care_user), conn=Depends(get_conn)
):
    if body.reason == "OTRO" and not body.comment.strip():
        raise HTTPException(400, "Debes indicar un comentario para el motivo OTRO.")
    with conn.transaction():
        treatment(conn, rehab_id, active=True, viewer=user)
        return {
            "ok": svc.discharge_patient(conn, rehab_id, body.reason, body.comment, user["dni"])
        }


@app.post("/treatments/{rehab_id}/sessions")
def add_session(
    rehab_id: int,
    body: TreatmentSession,
    user=Depends(care_user),
    conn=Depends(get_conn),
):
    with conn.transaction():
        # Serializa el registro con las altas y otras modificaciones del mismo tratamiento.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM rehab_active WHERE id = %s FOR UPDATE", (rehab_id,)
            )
        selected = treatment(conn, rehab_id, active=True, viewer=user)
        if body.status in {"REALIZADA", "REVISION"}:
            error = validar_hora_sesion(selected, body.session_time_value)
            if error:
                raise HTTPException(400, error)
        elif not body.absence_reason.strip():
            raise HTTPException(400, "Debes indicar el motivo de la falta.")
        days = [
            item.strip()
            for item in (selected["attendance_days"] or "").split(",")
            if item.strip()
        ]
        weekdays = (
            "Lunes",
            "Martes",
            "Miércoles",
            "Jueves",
            "Viernes",
            "Sábado",
            "Domingo",
        )
        if (
            days
            and weekdays[body.session_date_value.weekday()] not in days
            and not body.out_of_schedule_reason.strip()
        ):
            raise HTTPException(
                400, "Indica el motivo del registro fuera de los días establecidos."
            )
        values = body.model_dump()
        if body.status not in {"REALIZADA", "REVISION"}:
            values["session_time_value"] = None
            values["pain_eva"] = None
        svc.add_treatment_session(
            conn,
            rehab_active_id=rehab_id,
            patient_id=selected["patient_id"],
            specialty=selected["specialty"],
            subspecialty=selected["subspecialty"],
            recorded_by=user["dni"],
            **values,
        )
    return {"ok": True}


@app.get("/treatments/{rehab_id}/sessions")
def sessions(
    rehab_id: int,
    page: int | None = Query(default=None, ge=1, le=1_000_000_000),
    page_size: int = Query(default=50, ge=1, le=100),
    _user=Depends(care_user), conn=Depends(get_conn),
):
    if page is not None:
        return encode(read_table(conn, "session_history", _user,
                                 rehab_active_id=rehab_id, page=page, page_size=page_size))
    treatment(conn, rehab_id, viewer=_user)
    return table(svc.get_treatment_sessions(conn, rehab_id))


@app.get("/treatments/{rehab_id}/session-summary")
def session_summary(rehab_id: int, _user=Depends(care_user), conn=Depends(get_conn)):
    treatment(conn, rehab_id, viewer=_user)
    return svc.get_session_summary(conn, rehab_id)


@app.get("/treatments/{rehab_id}/initial-note")
def initial_note(rehab_id: int, user=Depends(care_user), conn=Depends(get_conn)):
    with conn.transaction():
        treatment(conn, rehab_id, viewer=user)
        _, rows = fetch_all(conn, """
            SELECT w.initial_note, COALESCE(u.full_name, w.initial_note_author), w.created_at
            FROM rehab_active a
            JOIN waitlist w ON w.id = a.source_waitlist_id
            LEFT JOIN users u ON u.dni = w.initial_note_author
            WHERE a.id = %s
        """, (rehab_id,))
    if not rows or not rows[0][0]:
        return {"note": "", "author": None, "created_at": None}
    note, author, created_at = rows[0]
    return encode({"note": note, "author": author, "created_at": created_at})


@app.get("/treatments/{rehab_id}/followup")
def followup_bundle(rehab_id: int, _user=Depends(care_user), conn=Depends(get_conn)):
    """Comparte los mismos indicadores entre el resumen y el informe."""
    treatment(conn, rehab_id, viewer=_user)
    summary = svc.get_clinical_followup_summary(conn, rehab_id)
    return encode(
        {"summary": summary, "report": svc.format_clinical_followup_report(summary)}
    )


@app.get("/treatments/{rehab_id}/followup-summary")
def followup_summary(rehab_id: int, _user=Depends(care_user), conn=Depends(get_conn)):
    treatment(conn, rehab_id, viewer=_user)
    return encode(svc.get_clinical_followup_summary(conn, rehab_id))


@app.get("/treatments/{rehab_id}/report")
def report(rehab_id: int, _user=Depends(care_user), conn=Depends(get_conn)):
    treatment(conn, rehab_id, viewer=_user)
    return {"report": svc.generate_clinical_followup_report(conn, rehab_id)}


@app.get("/treatments/{rehab_id}/pain-series")
def pain_series(rehab_id: int, _user=Depends(care_user), conn=Depends(get_conn)):
    treatment(conn, rehab_id, viewer=_user)
    return table(svc.get_patient_pain_series(conn, rehab_id))


@app.get("/treatments/{rehab_id}/status-distribution")
def status_distribution(
    rehab_id: int, _user=Depends(care_user), conn=Depends(get_conn)
):
    treatment(conn, rehab_id, viewer=_user)
    return table(svc.get_patient_status_distribution(conn, rehab_id))


@app.get("/dashboard/{name}")
def dashboard(name: str, _user=Depends(medical_user), conn=Depends(get_conn)):
    operations = {
        "specialties": svc.get_dashboard_specialty_summary,
        "sessions": svc.get_dashboard_session_summary,
        "adherence": svc.get_dashboard_adherence_by_specialty,
    }
    if name not in operations:
        raise HTTPException(404, "Indicador no disponible.")
    return table(operations[name](conn))


@app.get("/patients/{patient_id}/ai-consent")
def get_consent(
    patient_id: str,
    rehab_id: int | None = Query(default=None, ge=1),
    user=Depends(ready_user),
    conn=Depends(get_conn),
):
    if len(patient_id) != 6 or not patient_id.isascii() or not patient_id.isdigit():
        raise HTTPException(422, "El NHC debe tener seis cifras.")
    mode = ai_use_mode()
    if mode == "demo":
        allowed = can_use_ai_summary(user) or (
            user["role"] == "CLINICO"
            and svc.has_clinical_assignment(conn, patient_id, user["dni"], rehab_id)
        )
        return {"accepted": svc.get_patient_ai_consent(conn, patient_id) if allowed else None,
                "can_manage": allowed, "can_generate": can_use_ai_summary(user)}
    allowed = (
        mode == "clinical"
        and (can_use_ai_summary(user) or (
            user["role"] == "CLINICO"
            and svc.has_clinical_assignment(conn, patient_id, user["dni"], rehab_id)
        ))
    )
    return {
        "can_manage": allowed,
        "can_generate": mode == "clinical" and can_use_ai_summary(user),
        "consent_version": clinical_consent_version() if allowed else None,
        "accepted": svc.get_patient_ai_consent(conn, patient_id, version=clinical_consent_version())
        if allowed else None,
    }


@app.put("/patients/{patient_id}/ai-consent")
def save_consent(
    patient_id: str, body: Consent, user=Depends(care_user), conn=Depends(get_conn)
):
    if len(patient_id) != 6 or not patient_id.isascii() or not patient_id.isdigit():
        raise HTTPException(422, "El NHC debe tener seis cifras.")
    mode = ai_use_mode()
    if mode == "disabled":
        raise PermissionError("La IA está deshabilitada.")
    if mode == "clinical":
        if not can_use_ai_summary(user) and not (
            user["role"] == "CLINICO"
            and svc.has_clinical_assignment(conn, patient_id, user["dni"])
        ):
            raise PermissionError("Se requiere una asignación clínica activa para este paciente.")
        if body.accepted and not body.evidence_reference:
            raise HTTPException(422, "Indica la referencia del consentimiento explícito documentado.")
        svc.set_patient_ai_consent(
            conn, patient_id, body.accepted, user["dni"],
            version=clinical_consent_version(), evidence_reference=body.evidence_reference,
        )
    else:
        if not can_use_ai_summary(user) and not svc.has_clinical_assignment(conn, patient_id, user["dni"]):
            raise PermissionError("No tienes una asignación activa para este paciente.")
        svc.set_patient_ai_consent(conn, patient_id, body.accepted, user["dni"])
    return {"ok": True}


@app.post("/treatments/{rehab_id}/ai-summary")
def ai_summary(
    rehab_id: int,
    body: AISummaryRequest,
    user=Depends(medical_user),
    conn=Depends(get_conn),
):
    mode = require_summary_mode(body.synthetic_data_confirmed)
    if not ai_slot.acquire(blocking=False):
        raise HTTPException(
            429, "Ya hay un informe de IA en proceso. Inténtalo después."
        )
    try:
        treatment(conn, rehab_id, active=True, viewer=user)
        # Esta función vuelve a comprobar el consentimiento y el rol en el servidor.
        summary, model = svc.generate_ai_clinical_summary(
            conn,
            rehab_id,
            actor=user["dni"],
            synthetic_data_confirmed=body.synthetic_data_confirmed,
            role=user["role"],
        )
        return {
            "summary": summary,
            "model": model,
            "metadata": {
                "ai_generated": True,
                "use_mode": mode,
                "consent_version": clinical_consent_version() if mode == "clinical" else None,
                "synthetic_data_confirmed": mode == "demo",
                "prompt_version": CLINICAL_PROMPT_VERSION if mode == "clinical" else PROMPT_VERSION,
                "human_review_required": True,
                **({"clinical_use_authorized": False} if mode == "demo" else {}),
                "summary_sha256": digest(summary),
                "generated_at": datetime.now(UTC).isoformat(),
            },
        }
    finally:
        ai_slot.release()


@app.get("/admin/users")
def users(
    page: int | None = Query(default=None, ge=1, le=1_000_000_000),
    page_size: int = Query(default=50, ge=1, le=100),
    exclude_current: bool = False,
    admin=Depends(admin_user),
    conn=Depends(get_conn),
):
    if page is not None:
        query = auth.USER_LIST_QUERY
        params = ()
        if exclude_current:
            query += " WHERE id <> %s"
            params = (admin["id"],)
        return encode(paginate_query(
            conn, query, params, order_by="username ASC, id ASC",
            page=page, page_size=page_size,
        ))
    return encode(auth.get_all_users(conn))


@app.post("/admin/users")
def create_user(body: UserCreate, _admin=Depends(admin_user), conn=Depends(get_conn)):
    """Registra una cuenta y devuelve si se ha creado sin duplicar usuario ni DNI."""
    username = body.dni.strip().upper()
    if not body.full_name.strip():
        raise HTTPException(400, "Introduce el nombre completo.")
    if not is_valid_dni(username):
        raise HTTPException(
            400, "El DNI no es válido: debe tener 8 números y la letra correcta."
        )
    if body.profession not in [row[0] for row in cat.get_professions(conn)]:
        raise HTTPException(400, "Profesión no válida.")
    role = role_for_profession(body.profession)
    temporary_password = secrets.token_urlsafe(15)
    with conn.transaction():
        created = auth.create_user(
            conn, username, body.full_name.strip(), username, body.profession, role
        )
        if created:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE username = %s",
                    (auth.hash_password(temporary_password), username),
                )
    return {
        "created": created,
        "temporary_password": temporary_password if created else None,
        "username": username,
    }


@app.put("/admin/users/{user_id}/leave")
def clinician_leave_state(
    user_id: int, body: ClinicianLeave, admin=Depends(admin_user), conn=Depends(get_conn)
):
    return clinician_leave.set_clinician_leave(conn, user_id, body.on_leave, admin["dni"])


@app.post("/admin/treatments/{rehab_id}/reassign")
def reassign_treatment(
    rehab_id: int, body: TreatmentReassignment, admin=Depends(admin_user), conn=Depends(get_conn)
):
    return clinician_leave.reassign_treatment(
        conn, rehab_id, body.expected_clinician_dni, body.target_user_id, admin["dni"]
    )


@app.post("/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, admin=Depends(admin_user), conn=Depends(get_conn)):
    if user_id == admin["id"]:
        raise HTTPException(
            400,
            "Usa el cambio de contraseña de tu cuenta; no puedes restablecer tu propia sesión aquí.",
        )
    temporary_password = secrets.token_urlsafe(15)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s, must_change_password = TRUE WHERE id = %s RETURNING username",
                (auth.hash_password(temporary_password), user_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "El usuario no existe.")
            cur.execute("DELETE FROM api_sessions WHERE user_id = %s", (user_id,))
    return {"temporary_password": temporary_password, "username": row[0]}


@app.post("/admin/catalog/specialties")
def add_specialty(
    body: SpecialtyCreate, _admin=Depends(admin_user), conn=Depends(get_conn)
):
    if not body.name.strip():
        raise HTTPException(400, "Introduce el nombre de la especialidad.")
    cat.add_specialty_config(conn, body.name, body.requires_subspecialty)
    return {"ok": True}


@app.post("/admin/catalog/areas")
def add_area(body: AreaCreate, _admin=Depends(admin_user), conn=Depends(get_conn)):
    if (
        not body.name.strip()
        or body.specialty_name
        not in cat.get_nombres_especialidades(conn, only_active=False)
    ):
        raise HTTPException(400, "Revisa la especialidad y el área.")
    cat.add_subspecialty_config(conn, body.specialty_name, body.name)
    return {"ok": True}


@app.put("/admin/catalog/specialties/state")
def specialty_state(
    body: SpecialtyState, _admin=Depends(admin_user), conn=Depends(get_conn)
):
    cat.set_specialty_active(conn, body.specialty_name, body.active)
    return {"ok": True}


@app.put("/admin/catalog/areas/state")
def area_state(body: AreaState, _admin=Depends(admin_user), conn=Depends(get_conn)):
    cat.set_subspecialty_active(conn, body.specialty_name, body.name, body.active)
    return {"ok": True}


@app.delete("/admin/requests/{waitlist_id}")
def delete_request(waitlist_id: int, admin=Depends(admin_user), conn=Depends(get_conn)):
    ok, message = svc.delete_waitlist_entry(conn, waitlist_id, admin["dni"])
    return {"ok": ok, "message": message}


@app.delete("/admin/treatments/{rehab_id}")
def delete_treatment(rehab_id: int, admin=Depends(admin_user), conn=Depends(get_conn)):
    ok, message = svc.delete_active_treatment(conn, rehab_id, admin["dni"])
    return {"ok": ok, "message": message}


@app.get("/catalog/professions")
def professions(
    only_active: bool = True, _user=Depends(ready_user), conn=Depends(get_conn)
):
    return cat.get_professions(conn, only_active=only_active)


@app.post("/admin/catalog/professions")
def add_profession(
    body: ProfessionCreate, _admin=Depends(admin_user), conn=Depends(get_conn)
):
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(400, "Introduce el nombre de la profesión.")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("LOCK TABLE professions_config IN SHARE ROW EXCLUSIVE MODE")
            cur.execute(
                "SELECT name FROM professions_config WHERE LOWER(name) = LOWER(%s)",
                (name,),
            )
            if cur.fetchone():
                raise HTTPException(
                    409, "La profesión ya existe; puedes activarla si está desactivada."
                )
            cur.execute("INSERT INTO professions_config (name) VALUES (%s)", (name,))
    return {"created": True}


@app.put("/admin/catalog/professions/state")
def profession_state(
    body: ProfessionState, _admin=Depends(admin_user), conn=Depends(get_conn)
):
    if body.name == "Administrador" and not body.active:
        raise HTTPException(400, "La profesión Administrador debe permanecer activa.")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE professions_config SET active = %s WHERE name = %s RETURNING name",
                (body.active, body.name),
            )
            if not cur.fetchone():
                raise HTTPException(404, "La profesión no existe.")
    return {"updated": True}


@app.get("/admin/visits")
def clinical_visits(
    patient_id: str | None = Query(default=None, pattern=r"^[0-9]{6}$"),
    clinician_dni: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=1000, ge=1, le=5000),
    page: int | None = Query(default=None, ge=1, le=1_000_000_000),
    page_size: int = Query(default=50, ge=1, le=100),
    _admin=Depends(admin_user),
    conn=Depends(get_conn),
):
    """Devuelve el registro de consultas a historias solo al administrador."""
    conditions, params = [], []
    if patient_id:
        conditions.append("patient_id = %s")
        params.append(patient_id)
    if clinician_dni:
        conditions.append("clinician_dni = %s")
        params.append(clinician_dni.strip().upper())
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"SELECT clinician_dni, patient_id, visit_date FROM clinical_visit_log {where}"
    order = "visit_date DESC, clinician_dni, patient_id"
    if page is not None:
        return encode(paginate_query(
            conn, query, tuple(params), order_by=order, page=page, page_size=page_size,
        ))
    return table(
        fetch_all(
            conn,
            f"{query} ORDER BY {order} LIMIT %s",
            (*params, limit),
        )
    )
