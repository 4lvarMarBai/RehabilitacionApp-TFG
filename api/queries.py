"""Consultas cerradas del servidor. El cliente nunca envía SQL."""

from fastapi import HTTPException

from servidor.ai_policy import ai_use_mode, clinical_consent_version
from servidor.database import fetch_all
from api.pagination import paginate_query


ADMIN_TABLES = {"admin_waitlist", "admin_active", "user_dni", "areas", "specialties", "professions"}


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

    if name == "session_history":
        if rehab_active_id is None:
            raise HTTPException(422, "Falta el tratamiento.")
        return read_rows(conn, """
            SELECT id, rehab_active_id, patient_id, specialty, subspecialty,
                   session_date, session_time, status, absence_reason,
                   out_of_schedule_reason, recorded_by, created_at,
                   clinical_note, pain_eva, functional_status, goal_status, incidents
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
        patient_filter = " AND patient_id = %s" if patient_id else ""
        params = (patient_id, limit) if patient_id else (limit,)
        return read_rows(
            conn,
            f"SELECT {active_columns[name]} FROM rehab_active WHERE status = 'ACTIVO'{patient_filter} ORDER BY id DESC LIMIT %s",
            params,
        )

    if name == "discharged":
        return read_rows(
            conn,
            """
            SELECT id, patient_id, specialty, subspecialty, prescribed_sessions,
                   start_date, discharged_at, discharge_reason, discharge_comment
            FROM rehab_active WHERE status = 'ALTA'
            ORDER BY discharged_at DESC, id DESC LIMIT %s
        """,
            (limit,),
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

    if name == "audit":
        conditions, params = [], []
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
                   al.wait_days, al.rule_applied, al.reason, al.comment,
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
