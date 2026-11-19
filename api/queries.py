"""Consultas cerradas del servidor. El cliente nunca envía SQL."""

from fastapi import HTTPException

from servidor.ai_policy import ai_use_mode, clinical_consent_version
from servidor.database import fetch_all
from api.pagination import paginate_query
from api.access import clinical_scope, authorized_treatment


ADMIN_TABLES = {"admin_waitlist", "admin_active", "user_dni", "areas", "specialties", "professions", "reassignment_pending", "available_clinicians", "security_events"}


def read_table(
    conn,
    name: str,
    user: dict,
    *,
    specialty=None,
    subspecialty=None,
    priority=None,
    eligible_only=False,
    dni=None,
    rehab_active_id=None,
    year=None,
    month=None,
    limit=1000,
    patient_id=None,
    event=None,
    ai_consent=None,
    page=None,
    page_size=50,
):
    """Aplica filtros a los listados permitidos y comprueba los permisos administrativos."""
    if user.get("role") not in {"ADMIN", "CLINICO", "MEDICO"}:
        raise HTTPException(403, "Rol no autorizado.")
    if name in ADMIN_TABLES and user["role"] != "ADMIN":
        raise HTTPException(403, "Esta consulta requiere un administrador.")

    def read_rows(connection, query, params=()):
        if page is None:
            return fetch_all(connection, query, params)
        if name in {"user_dni", "calendar"}:
            raise HTTPException(422, "Esta consulta no admite paginación.")
        # Todas estas consultas terminan en un ORDER BY fijo y LIMIT parametrizado.
        base, order = query.rsplit("ORDER BY", 1)
        order = order.strip().removesuffix("LIMIT %s").strip()
        return paginate_query(connection, base, params[:-1], order_by=order,
                              page=page, page_size=page_size)

    if name == "reassignment_pending":
        patient_filter = " AND ra.patient_id = %s" if patient_id else ""
        params = (patient_id, limit) if patient_id else (limit,)
        return read_rows(conn, f"""
            SELECT ra.id, ra.patient_id, ra.specialty, ra.subspecialty,
                   ra.assigned_clinician_dni, ra.assigned_clinician_name,
                   ra.slot_type, ra.time_preference, ra.transport_mode,
                   ra.preferred_hour, ra.attendance_days
            FROM rehab_active ra JOIN users u ON u.dni = ra.assigned_clinician_dni
            WHERE ra.status = 'ACTIVO' AND u.role = 'CLINICO' AND u.on_leave = TRUE
            {patient_filter}
            ORDER BY id ASC LIMIT %s
        """, params)

    if name == "available_clinicians":
        if rehab_active_id is None:
            raise HTTPException(422, "Selecciona el tratamiento que quieres reasignar.")
        return read_rows(conn, """
            SELECT target.id, target.dni, target.full_name, target.profession
            FROM users target
            JOIN rehab_active ra ON ra.id = %s AND ra.status = 'ACTIVO'
            JOIN users source ON source.dni = ra.assigned_clinician_dni
            WHERE source.on_leave = TRUE AND source.role = 'CLINICO'
              AND target.profession = source.profession AND target.role = 'CLINICO'
              AND target.active = TRUE AND target.on_leave = FALSE
              AND target.must_change_password = FALSE AND target.id <> source.id
            ORDER BY full_name ASC, id ASC LIMIT %s
        """, (rehab_active_id, limit))

    if name == "session_history":
        if rehab_active_id is None:
            raise HTTPException(422, "Falta el tratamiento.")
        authorized_treatment(conn, rehab_active_id, user)
        return read_rows(conn, """
            SELECT id, rehab_active_id, patient_id, specialty, subspecialty,
                   session_date, session_time, status, absence_reason,
                   out_of_schedule_reason, recorded_by, created_at,
                   clinical_note, pain_eva, functional_status, goal_status, incidents,
                   knee_flexion_deg, knee_extension_deficit_deg, tug_seconds,
                   tug_conditions, koos_jr_raw, knee_goal_metric, knee_goal_target
            FROM treatment_sessions WHERE rehab_active_id = %s
            ORDER BY session_date DESC, session_time DESC NULLS LAST, id DESC LIMIT %s
        """, (rehab_active_id, limit))

    if name == "waiting":
        conditions, params = ["status = 'EN_ESPERA'"], []
        for column, value in (
            ("specialty", specialty),
            ("subspecialty", subspecialty),
            ("priority_level", priority),
        ):
            if value and value != "Todas":
                conditions.append(f"{column} = %s")
                params.append(value)
        if patient_id:
            conditions.append("patient_id = %s")
            params.append(patient_id)
        if eligible_only:
            conditions.append("eligible = TRUE")
        return read_rows(
            conn,
            f"""
            SELECT id, patient_id, priority_level, specialty, subspecialty,
                   prescribed_sessions, request_date,
                   FLOOR(EXTRACT(EPOCH FROM (NOW() - request_date)) / 86400)::INTEGER AS wait_days,
                   eligible
            FROM waitlist WHERE {" AND ".join(conditions)}
            ORDER BY request_date ASC, id ASC LIMIT %s
        """,
            (*params, limit),
        )

    active_columns = {
        "active_basic": "id, patient_id, specialty, subspecialty, start_date",
        "active_details": "id, patient_id, specialty, subspecialty, prescribed_sessions, start_date, assigned_by, assigned_at",
        "active_for_sessions": (
            "id, patient_id, specialty, subspecialty, prescribed_sessions, attendance_days, "
            "slot_type, time_preference, transport_mode, preferred_hour, coordination_rule, start_date"
        ),
        "admin_active": "id, patient_id, specialty, subspecialty, start_date",
    }
    if name in active_columns:
        scope, scope_params = ("TRUE", ()) if name == "admin_active" else clinical_scope(user)
        patient_filter = " AND patient_id = %s" if patient_id else ""
        params = (*scope_params, patient_id, limit) if patient_id else (*scope_params, limit)
        return read_rows(
            conn,
            f"SELECT {active_columns[name]} FROM rehab_active WHERE status = 'ACTIVO' AND ({scope}){patient_filter} ORDER BY id DESC LIMIT %s",
            params,
        )

    if name == "discharged":
        scope, scope_params = clinical_scope(user)
        return read_rows(
            conn,
            f"""
            SELECT id, patient_id, specialty, subspecialty, prescribed_sessions,
                   start_date, discharged_at, discharge_reason, discharge_comment
            FROM rehab_active WHERE status = 'ALTA' AND ({scope})
            ORDER BY discharged_at DESC, id DESC LIMIT %s
        """,
            (*scope_params, limit),
        )

    if name == "admin_waitlist":
        return read_rows(
            conn,
            """
            SELECT id, patient_id, specialty, subspecialty, priority_level, request_date
            FROM waitlist WHERE status = 'EN_ESPERA' ORDER BY id DESC LIMIT %s
        """,
            (limit,),
        )

    if name == "user_dni":
        if not dni:
            raise HTTPException(422, "Falta el DNI.")
        return read_rows(conn, "SELECT id FROM users WHERE dni = %s LIMIT 1", (dni,))

    if name == "areas":
        return read_rows(
            conn,
            "SELECT specialty_name, name, active FROM subspecialties_config ORDER BY specialty_name, name LIMIT %s",
            (limit,),
        )

    if name == "specialties":
        return read_rows(
            conn,
            "SELECT name, requires_subspecialty, active FROM specialties_config ORDER BY name ASC LIMIT %s",
            (limit,),
        )

    if name == "professions":
        return read_rows(
            conn,
            "SELECT name, active FROM professions_config ORDER BY name ASC LIMIT %s",
            (limit,),
        )

    if name == "calendar":
        if rehab_active_id is None or year is None or month is None:
            raise HTTPException(422, "Faltan los datos del calendario.")
        authorized_treatment(conn, rehab_active_id, user)
        return read_rows(
            conn,
            """
            SELECT session_date, status FROM treatment_sessions
            WHERE rehab_active_id = %s
              AND EXTRACT(YEAR FROM session_date) = %s
              AND EXTRACT(MONTH FROM session_date) = %s
            ORDER BY session_date ASC
        """,
            (rehab_active_id, year, month),
        )

    if name == "security_events":
        conditions, params = [], []
        if patient_id:
            conditions.append("patient_id = %s")
            params.append(patient_id)
        if dni:
            conditions.append("actor = %s")
            params.append(dni)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return read_rows(conn, f"""
            SELECT id, actor, action, outcome, rehab_active_id, patient_id, created_at
            FROM security_access_log{where} ORDER BY id DESC LIMIT %s
        """, (*params, limit))

    if name == "audit":
        conditions, params = [], []
        comment_column = "al.comment"
        reason_column = "al.reason"
        if user["role"] == "CLINICO":
            conditions.append("EXISTS (SELECT 1 FROM rehab_active own WHERE own.assigned_clinician_dni = %s AND (own.id = al.rehab_active_id OR own.source_waitlist_id = al.waitlist_id))")
            params.append(user["dni"])
        elif user["role"] == "ADMIN":
            comment_column = "NULL::text AS comment"
            reason_column = "NULL::text AS reason"
            conditions.append("al.event NOT IN ('REGISTRO_SESION', 'ELIMINACION_SESION')")
        for column, value in (
            ("al.specialty", specialty),
            ("al.subspecialty", subspecialty),
            ("al.chosen_priority_level", priority),
        ):
            if value and value != "Todas":
                conditions.append(f"{column} = %s")
                params.append(value)
        if patient_id:
            conditions.append("al.patient_id = %s")
            params.append(patient_id)
        if event:
            conditions.append("al.event = %s")
            params.append(event)
        mode = ai_use_mode()
        consent_version = clinical_consent_version() if mode == "clinical" else (
            "software-v1" if mode == "demo" else None
        )
        if ai_consent in ("accepted", "rejected"):
            conditions.append(
                "EXISTS (SELECT 1 FROM patient_ai_consent AS consent "
                "WHERE consent.patient_id = al.patient_id AND consent.consent_version = %s "
                "AND consent.accepted = %s)"
            )
            params.extend((consent_version, ai_consent == "accepted"))
        elif ai_consent == "missing":
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM patient_ai_consent AS consent "
                "WHERE consent.patient_id = al.patient_id AND consent.consent_version = %s)"
            )
            params.append(consent_version)
        if eligible_only:
            conditions.append("COALESCE(w.eligible, FALSE) = TRUE")
        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        return read_rows(
            conn,
            f"""
            SELECT al.id, al.event, al.patient_id, al.specialty, al.subspecialty,
                   al.waitlist_id, al.rehab_active_id, al.chosen_priority_level,
                   al.wait_days, al.rule_applied, {reason_column}, {comment_column},
                   al.actor, al.created_at, w.eligible,
                   CASE WHEN al.event = 'ALTA_TRATAMIENTO' THEN (
                       SELECT COUNT(*) FROM treatment_sessions AS ts
                       WHERE ts.rehab_active_id = al.rehab_active_id
                         AND ts.status = 'REALIZADA'
                         AND ts.created_at <= al.created_at
                   ) END AS completed_sessions,
                   CASE WHEN al.event = 'ALTA_TRATAMIENTO' THEN (
                       SELECT COUNT(*) FROM treatment_sessions AS ts
                       WHERE ts.rehab_active_id = al.rehab_active_id
                         AND ts.status = 'REVISION'
                         AND ts.created_at <= al.created_at
                   ) END AS review_sessions
            FROM assignment_log AS al
            LEFT JOIN rehab_active AS ra ON al.rehab_active_id = ra.id
            LEFT JOIN waitlist AS w ON COALESCE(al.waitlist_id, ra.source_waitlist_id) = w.id
            {where_sql} ORDER BY id DESC LIMIT %s
        """,
            (*params, limit),
        )

    raise HTTPException(404, "Consulta no disponible.")
