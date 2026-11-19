"""Bajas temporales y cambios de responsable sin reiniciar los tratamientos."""

from servidor.database import now_iso


def require_available_clinician(cur, dni):
    """El bloqueo impide que una baja coincida con una nueva asignación."""
    cur.execute("SELECT active, on_leave FROM users WHERE dni = %s FOR SHARE", (dni,))
    row = cur.fetchone()
    if not row or not row[0] or row[1]:
        raise PermissionError("El usuario no está disponible para recibir nuevas asignaciones.")


def set_clinician_leave(conn, user_id, on_leave, actor):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT dni, role, active, on_leave FROM users WHERE id = %s FOR UPDATE", (user_id,))
            row = cur.fetchone()
            if not row or row[1] != "CLINICO" or not row[2]:
                raise ValueError("Selecciona una cuenta activa con rol Clínico.")
            dni, _, _, previous = row
            if previous == on_leave:
                raise ValueError("El clínico ya tiene ese estado de disponibilidad.")
            cur.execute("UPDATE users SET on_leave = %s WHERE id = %s", (on_leave, user_id))
            cur.execute("""
                SELECT COUNT(*) FROM rehab_active
                WHERE assigned_clinician_dni = %s AND status = 'ACTIVO'
            """, (dni,))
            count = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO assignment_log (event, reason, comment, actor, created_at)
                VALUES (%s, 'DISPONIBILIDAD_CLINICO', %s, %s, %s)
            """, ("BAJA_CLINICO" if on_leave else "REINCORPORACION_CLINICO",
                  f"DNI del clínico: {dni}; tratamientos activos: {count}", actor, now_iso()))
    return {"on_leave": on_leave, "active_treatments": count}


def reassign_treatment(conn, rehab_id, expected_dni, target_user_id, actor):
    with conn.transaction():
        with conn.cursor() as cur:
            # Un orden fijo evita bloqueos cruzados entre dos reasignaciones.
            cur.execute("""
                SELECT id, dni, full_name, profession, role, active, on_leave, must_change_password
                FROM users WHERE dni = %s OR id = %s ORDER BY id FOR UPDATE
            """, (expected_dni, target_user_id))
            people = cur.fetchall()
            source = next((row for row in people if row[1] == expected_dni), None)
            target = next((row for row in people if row[0] == target_user_id), None)
            if not source or source[4] != 'CLINICO' or not source[6]:
                raise ValueError("El clínico de origen ya no está de baja. Actualiza el listado.")
            if (not target or target[0] == source[0] or target[4] != 'CLINICO'
                    or not target[5] or target[6] or target[7]):
                raise ValueError("Selecciona otro clínico activo, disponible y con su contraseña actualizada.")
            if target[3] != source[3]:
                raise ValueError("El sustituto debe tener la misma profesión que el clínico de origen.")
            cur.execute("""
                SELECT patient_id, specialty, subspecialty, assigned_clinician_dni
                FROM rehab_active WHERE id = %s AND status = 'ACTIVO' FOR UPDATE
            """, (rehab_id,))
            row = cur.fetchone()
            if not row or row[3] != expected_dni:
                raise ValueError("El tratamiento ha cambiado o ya no está activo. Actualiza el listado.")
            patient_id, specialty, area, _ = row
            cur.execute("""
                UPDATE rehab_active
                SET assigned_clinician_dni = %s, assigned_clinician_name = %s,
                    assigned_clinician_profession = %s
                WHERE id = %s
            """, (target[1], target[2], target[3], rehab_id))
            cur.execute("""
                INSERT INTO assignment_log
                    (event, rehab_active_id, patient_id, specialty, subspecialty,
                     reason, comment, actor, created_at)
                VALUES ('REASIGNACION_TRATAMIENTO', %s, %s, %s, %s,
                        'BAJA_TEMPORAL_CLINICO', %s, %s, %s)
            """, (rehab_id, patient_id, specialty, area,
                  f"Clínico anterior: {source[1]}; nuevo clínico: {target[1]}", actor, now_iso()))
    return {"patient_id": patient_id, "assigned_clinician_name": target[2]}
