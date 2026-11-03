"""Cliente HTTP de Streamlit. No contiene SQL ni credenciales de PostgreSQL."""

import json
from copy import deepcopy
import os
from datetime import UTC, date, datetime, time
from urllib.parse import urlsplit

import requests
import streamlit as st


PASSWORD_TEMPORAL_POR_DEFECTO = "123456789"


class ApiError(RuntimeError):
    pass


OllamaError = ApiError  # Compatibilidad con el bloque de errores de la pantalla.


def api_base_url():
    value = os.getenv("API_BASE_URL", "").strip()
    if not value:
        try:
            value = str(st.secrets.get("API_BASE_URL", "")).strip()
        except (FileNotFoundError, KeyError):
            value = ""
    if not value:
        value = "http://127.0.0.1:8000"  # Desarrollo local; la URL remota se configura al distribuir.
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not value or parsed.scheme not in {"http", "https"} or not parsed.hostname:
        st.error("Configura API_BASE_URL en .streamlit/secrets.toml.")
        st.stop()
    if parsed.username or parsed.password or (parsed.scheme != "https" and not local):
        st.error("La API remota debe usar HTTPS y su URL no debe incluir contraseñas.")
        st.stop()
    return value.rstrip("/")


def _decode(value):
    if set(value) == {"__api_type__", "value"}:
        types = {
            "date": date.fromisoformat,
            "datetime": datetime.fromisoformat,
            "time": time.fromisoformat,
        }
        if value["__api_type__"] in types:
            return types[value["__api_type__"]](value["value"])
    return value


def _json_default(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise TypeError(f"Tipo no serializable: {type(value).__name__}")


def begin_api_run():
    """Reutiliza lecturas solo durante esta ejecución de Streamlit."""
    st.session_state["_api_run_cache"] = {}


def _http_session():
    """Conexiones persistentes privadas para cada sesión de usuario."""
    if "_api_http_session" not in st.session_state:
        st.session_state["_api_http_session"] = requests.Session()
    return st.session_state["_api_http_session"]


def _request(method, path, *, data=None, params=None, login=False, timeout=60):
    headers = {}
    if not login:
        token = st.session_state.get("access_token")
        if not token:
            st.session_state["user"] = None
            st.rerun()
        headers["Authorization"] = f"Bearer {token}"
    cache = st.session_state.setdefault("_api_run_cache", {})
    base_url = api_base_url()
    cache_key = (
        base_url,
        st.session_state.get("access_token"),
        path,
        json.dumps(params or {}, sort_keys=True, default=_json_default),
    )
    if method == "GET" and cache_key in cache:
        return deepcopy(cache[cache_key])
    if method != "GET":
        cache.clear()
    payload = (
        json.loads(json.dumps(data, default=_json_default))
        if data is not None
        else None
    )
    try:
        response = _http_session().request(
            method,
            base_url + path,
            json=payload,
            params=params,
            headers=headers,
            timeout=(5, timeout),
            allow_redirects=False,
        )
    except requests.RequestException:
        st.error(
            "No se pudo contactar con la API. Comprueba que el servidor esté disponible. Si estabas guardando datos, revisa el historial antes de repetir la operación."
        )
        st.stop()
    if login and response.status_code == 401:
        return None
    if response.status_code == 401:
        session = st.session_state.get("_api_http_session")
        if session is not None:
            session.close()
        st.session_state.clear()
        st.session_state["_api_notice"] = (
            "La sesión ha caducado o ha sido revocada. Inicia sesión de nuevo."
        )
        st.rerun()
    try:
        result = json.loads(response.text, object_hook=_decode)
    except (ValueError, TypeError):
        st.error("La API devolvió una respuesta no válida.")
        st.stop()
    if not 200 <= response.status_code < 300:
        detail = result.get("detail", "No se pudo completar la operación.")
        if isinstance(detail, list):
            detail = "; ".join(
                f"{'.'.join(str(x) for x in item.get('loc', []))}: {item.get('msg', '')}"
                for item in detail
            )
        st.error(str(detail))
        st.stop()
    if method == "GET":
        cache[cache_key] = deepcopy(result)
    return result


def get_table(conn, name, **filters):
    result = _request("GET", f"/tables/{name}", params=filters)
    return result["columns"], result["rows"]


def authenticate_user(conn, username, password):
    """Envía las credenciales al servidor y conserva el token de la sesión."""
    result = _request(
        "POST",
        "/auth/login",
        data={"username": username, "password": password},
        login=True,
    )
    if result is None:
        st.session_state.pop("access_token", None)
        return None
    st.session_state["access_token"] = result["access_token"]
    return result["user"]


def get_current_session_user():
    result = _request(
        "GET",
        "/bootstrap",
        params={
            "include_stats": st.session_state.get("nav_page", "📊 Panel de control")
            == "📊 Panel de control"
        },
    )
    cache = st.session_state.setdefault("_api_run_cache", {})
    for path, params, key in (
        ("/stats", {}, "stats"),
        ("/catalog/specialties", {"only_active": False}, "specialties"),
    ):
        if key in result:
            cache_key = (
                api_base_url(),
                st.session_state.get("access_token"),
                path,
                json.dumps(params, sort_keys=True, default=_json_default),
            )
            cache[cache_key] = deepcopy(result[key])
    return result["user"]


def change_user_password(conn, user_id, new_password, current_password):
    _request(
        "POST",
        "/auth/change-password",
        data={"current_password": current_password, "new_password": new_password},
    )
    st.session_state.pop("access_token", None)


def cerrar_sesion():
    token = st.session_state.get("access_token")
    try:
        if token:
            _http_session().post(
                api_base_url() + "/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
                timeout=(5, 10),
                allow_redirects=False,
            )
    except requests.RequestException:
        # Si el servidor no responde, la sesión remota caducará por su plazo normal.
        pass
    finally:
        session = st.session_state.get("_api_http_session")
        if session is not None:
            session.close()
        st.session_state.clear()
    st.rerun()


def get_stats(conn):
    """Obtiene los contadores del panel en una sola consulta."""
    result = _request("GET", "/stats")
    return result["waiting"], result["active"], result["discharged"]


def get_especialidades(conn, only_active=True):
    rows = _request("GET", "/catalog/specialties", params={"only_active": False})
    return [row for row in rows if row[2]] if only_active else rows


def get_nombres_especialidades(conn, only_active=True):
    return [row[0] for row in get_especialidades(conn, only_active)]


def specialty_requires_subspecialty(conn, specialty_name):
    return next(
        (
            bool(row[1])
            for row in get_especialidades(conn, False)
            if row[0] == specialty_name
        ),
        False,
    )


def get_areas_por_especialidad(conn, specialty_name, only_active=True):
    return _request(
        "GET",
        "/catalog/areas",
        params={"specialty_name": specialty_name, "only_active": only_active},
    )


def get_nombres_areas_por_especialidad(conn, specialty_name, only_active=True):
    return [
        row[0] for row in get_areas_por_especialidad(conn, specialty_name, only_active)
    ]


def preview_next_patient(
    conn,
    specialty_filter,
    subspecialty_filter,
    slot_type_filter=None,
    time_preference_filter=None,
    transport_mode_filter=None,
):
    """Consulta el primer candidato con los mismos filtros y orden que la asignación."""
    return _request(
        "GET",
        "/requests/preview",
        params={
            "specialty_filter": specialty_filter,
            "subspecialty_filter": subspecialty_filter,
            "slot_type_filter": slot_type_filter,
            "time_preference_filter": time_preference_filter,
            "transport_mode_filter": transport_mode_filter,
        },
    )


def add_waiting_patient_multiple(
    conn,
    patient_id,
    priority_level,
    requests,
    request_date_iso,
    eligible,
    actor,
    slot_type,
    time_preference,
    transport_mode,
    preferred_hour,
    coordination_rule,
    ai_consent_accepted=None,
):
    """Guarda el consentimiento y una solicitud por tratamiento en una misma transacción."""
    return _request(
        "POST",
        "/requests",
        data={
            "patient_id": patient_id,
            "priority_level": priority_level,
            "requests": requests,
            "request_date": str(request_date_iso)[:10],
            "eligible": eligible,
            "slot_type": slot_type,
            "time_preference": time_preference,
            "transport_mode": transport_mode,
            "preferred_hour": preferred_hour,
            "coordination_rule": coordination_rule,
            "ai_consent_accepted": ai_consent_accepted,
        },
    )


def assign_next_patient(
    conn,
    assigned_by,
    assigned_clinician_dni,
    assigned_clinician_name,
    assigned_clinician_profession,
    specialty_filter,
    subspecialty_filter,
    attendance_days,
    slot_type_filter=None,
    time_preference_filter=None,
    transport_mode_filter=None,
):
    """Bloquea y asigna el primer candidato compatible con los filtros, por prioridad y antigüedad."""
    return _request(
        "POST",
        "/treatments/assign",
        data={
            "specialty_filter": specialty_filter,
            "subspecialty_filter": subspecialty_filter,
            "attendance_days": attendance_days,
            "slot_type_filter": slot_type_filter,
            "time_preference_filter": time_preference_filter,
            "transport_mode_filter": transport_mode_filter,
        },
    )


def discharge_patient(conn, rehab_active_id, reason, comment, actor):
    """Da de alta el tratamiento activo y registra el motivo y el autor de la acción."""
    return _request(
        "POST",
        f"/treatments/{rehab_active_id}/discharge",
        data={"reason": reason, "comment": comment},
    )["ok"]


def add_treatment_session(
    conn,
    rehab_active_id,
    patient_id,
    specialty,
    subspecialty,
    session_date_value,
    session_time_value,
    status,
    absence_reason,
    out_of_schedule_reason,
    recorded_by,
    clinical_note="",
    pain_eva=None,
    functional_status="",
    goal_status="",
    incidents="",
):
    """Guarda la sesión y los datos de evolución asociados al tratamiento."""
    return _request(
        "POST",
        f"/treatments/{rehab_active_id}/sessions",
        data={
            "session_date_value": session_date_value,
            "session_time_value": session_time_value,
            "status": status,
            "absence_reason": absence_reason,
            "out_of_schedule_reason": out_of_schedule_reason,
            "clinical_note": clinical_note,
            "pain_eva": pain_eva,
            "functional_status": functional_status,
            "goal_status": goal_status,
            "incidents": incidents,
        },
    )


def _service_table(path):
    result = _request("GET", path)
    return result["columns"], result["rows"]


def get_treatment_sessions(conn, rehab_active_id):
    return _service_table(f"/treatments/{rehab_active_id}/sessions")


def get_session_summary(conn, rehab_active_id):
    return _request("GET", f"/treatments/{rehab_active_id}/session-summary")


def get_clinical_followup_summary(conn, rehab_active_id):
    """Calcula asistencia y evolución a partir de las sesiones registradas."""
    return _request("GET", f"/treatments/{rehab_active_id}/followup")["summary"]


def generate_clinical_followup_report(conn, rehab_active_id):
    return _request("GET", f"/treatments/{rehab_active_id}/followup")["report"]


def get_patient_pain_series(conn, rehab_active_id):
    return _service_table(f"/treatments/{rehab_active_id}/pain-series")


def get_patient_status_distribution(conn, rehab_active_id):
    return _service_table(f"/treatments/{rehab_active_id}/status-distribution")


def get_dashboard_specialty_summary(conn):
    return _service_table("/dashboard/specialties")


def get_dashboard_session_summary(conn):
    return _service_table("/dashboard/sessions")


def get_dashboard_adherence_by_specialty(conn):
    return _service_table("/dashboard/adherence")


def get_patient_ai_consent(conn, patient_id):
    """Consulta la decisión vigente del paciente; la ausencia no equivale a aceptación."""
    return _request("GET", f"/patients/{patient_id}/ai-consent")["accepted"]


def set_patient_ai_consent(conn, patient_id, accepted, actor):
    """Guarda la decisión del paciente y deja constancia de quién la registró."""
    return _request(
        "PUT", f"/patients/{patient_id}/ai-consent", data={"accepted": accepted}
    )


def generate_ai_clinical_summary(
    conn, rehab_active_id, actor, *, synthetic_data_confirmed=False
):
    """Comprueba el consentimiento antes de enviar los informes al modelo local."""
    result = _request(
        "POST",
        f"/treatments/{rehab_active_id}/ai-summary",
        data={"synthetic_data_confirmed": synthetic_data_confirmed},
        timeout=240,
    )
    st.session_state[f"ai_metadata_{rehab_active_id}"] = result.get("metadata", {})
    return result["summary"], result["model"]


def get_all_users(conn):
    return _request("GET", "/admin/users")


def create_user(conn, username, full_name, dni, profession, role):
    """Registra una cuenta y devuelve si se ha creado sin duplicar usuario ni DNI."""
    result = _request(
        "POST",
        "/admin/users",
        data={
            "username": username,
            "full_name": full_name,
            "dni": dni,
            "profession": profession,
            "role": role,
        },
    )
    if result["created"]:
        st.session_state["temporary_user_password"] = {
            "username": result["username"],
            "password": result["temporary_password"],
        }
    return result["created"]


def reset_user_password_to_default(conn, user_id):
    result = _request("POST", f"/admin/users/{user_id}/reset-password")
    st.session_state["temporary_user_password"] = {
        "username": result["username"],
        "password": result["temporary_password"],
    }


def add_specialty_config(conn, name, requires_subspecialty):
    return _request(
        "POST",
        "/admin/catalog/specialties",
        data={"name": name, "requires_subspecialty": requires_subspecialty},
    )


def add_subspecialty_config(conn, specialty_name, name):
    return _request(
        "POST",
        "/admin/catalog/areas",
        data={"specialty_name": specialty_name, "name": name},
    )


def set_specialty_active(conn, specialty_name, active):
    return _request(
        "PUT",
        "/admin/catalog/specialties/state",
        data={"specialty_name": specialty_name, "active": active},
    )


def set_subspecialty_active(conn, specialty_name, name, active):
    return _request(
        "PUT",
        "/admin/catalog/areas/state",
        data={"specialty_name": specialty_name, "name": name, "active": active},
    )


def delete_waitlist_entry(conn, waitlist_id, actor):
    result = _request("DELETE", f"/admin/requests/{waitlist_id}")
    return result["ok"], result["message"]


def delete_active_treatment(conn, rehab_active_id, actor):
    result = _request("DELETE", f"/admin/treatments/{rehab_active_id}")
    return result["ok"], result["message"]


def iso_utc_from_date(value):
    return datetime.combine(value, time.min).replace(tzinfo=UTC).isoformat()


def now_iso():
    return datetime.now(UTC).isoformat()


def get_professions(conn=None, only_active=True):
    return _request("GET", "/catalog/professions", params={"only_active": only_active})


def add_profession_config(conn, name):
    return _request("POST", "/admin/catalog/professions", data={"name": name})


def set_profession_active(conn, name, active):
    return _request(
        "PUT", "/admin/catalog/professions/state", data={"name": name, "active": active}
    )


def get_clinical_visits(conn=None, patient_id=None, clinician_dni=None):
    result = _request(
        "GET",
        "/admin/visits",
        params={"patient_id": patient_id, "clinician_dni": clinician_dni},
    )
    return result["columns"], result["rows"]
