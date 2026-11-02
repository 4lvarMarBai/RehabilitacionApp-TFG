"""Consultas cerradas del servidor. El cliente nunca envía SQL."""

from fastapi import HTTPException

from servidor.database import fetch_all


ADMIN_TABLES = {"admin_waitlist", "admin_active", "user_dni", "areas"}


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
):
    """Aplica filtros a los listados permitidos y comprueba los permisos administrativos."""
    if name in ADMIN_TABLES and user["role"] != "ADMIN":
        raise HTTPException(403, "Esta consulta requiere un administrador.")

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
        if eligible_only:
            conditions.append("eligible = TRUE")
        return fetch_all(
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
        return fetch_all(
            conn,
            f"SELECT {active_columns[name]} FROM rehab_active WHERE status = 'ACTIVO'{patient_filter} ORDER BY id DESC LIMIT %s",
            params,
        )

    if name == "discharged":
        return fetch_all(
            conn,
            """
            SELECT id, patient_id, specialty, subspecialty, prescribed_sessions,
                   start_date, discharged_at, discharge_reason, discharge_comment
            FROM rehab_active WHERE status = 'ALTA'
            ORDER BY discharged_at DESC LIMIT %s
        """,
            (limit,),
        )

    if name == "admin_waitlist":
        return fetch_all(
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
        return fetch_all(conn, "SELECT id FROM users WHERE dni = %s LIMIT 1", (dni,))

    if name == "areas":
        return fetch_all(
            conn,
            "SELECT specialty_name, name, active FROM subspecialties_config ORDER BY specialty_name, name LIMIT %s",
            (limit,),
        )

    if name == "calendar":
        if rehab_active_id is None or year is None or month is None:
            raise HTTPException(422, "Faltan los datos del calendario.")
        return fetch_all(
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
        if ai_consent in ("accepted", "rejected"):
            conditions.append(
                "EXISTS (SELECT 1 FROM patient_ai_consent AS consent WHERE consent.patient_id = al.patient_id AND consent.accepted = %s)"
            )
            params.append(ai_consent == "accepted")
        elif ai_consent == "missing":
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM patient_ai_consent AS consent WHERE consent.patient_id = al.patient_id)"
            )
        if eligible_only:
            conditions.append("COALESCE(w.eligible, FALSE) = TRUE")
        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        return fetch_all(
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
            {where_sql} ORDER BY al.id DESC LIMIT %s
        """,
            (*params, limit),
        )

    raise HTTPException(404, "Consulta no disponible.")
