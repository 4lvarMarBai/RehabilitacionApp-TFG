"""Acceso asistencial y registro de consultas sin copiar notas clínicas."""

from fastapi import HTTPException
from servidor.database import fetch_all


def init_access_log(conn):
    with conn.cursor() as cur:
        # Las bajas del personal no pertenecen a una historia clínica concreta.
        cur.execute("ALTER TABLE assignment_log ALTER COLUMN patient_id DROP NOT NULL")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS security_access_log (
                id BIGSERIAL PRIMARY KEY,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                rehab_active_id BIGINT,
                patient_id TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_security_access_date ON security_access_log(created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_security_access_patient ON security_access_log(patient_id, created_at DESC)")


def log_access(conn, user, action, outcome, rehab_id=None, patient_id=None):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO security_access_log(actor, action, outcome, rehab_active_id, patient_id)
            VALUES (%s, %s, %s, %s, %s)
        """, ((user or {}).get("dni", "no_identificado"), action, outcome, rehab_id, patient_id))


def require_care_role(user):
    if user.get("role") not in {"CLINICO", "MEDICO"}:
        raise HTTPException(403, "Esta operación requiere un perfil asistencial.")


def clinical_scope(user, alias=""):
    """Los nombres de columna son internos; el DNI siempre se parametriza."""
    require_care_role(user)
    if user["role"] == "MEDICO":
        return "TRUE", ()
    return f"{alias}assigned_clinician_dni = %s", (user["dni"],)


def authorized_treatment(conn, rehab_id, user, *, active=False):
    scope, params = clinical_scope(user)
    _, rows = fetch_all(conn, f"""
        SELECT id, patient_id FROM rehab_active
        WHERE id = %s AND ({scope})
    """, (rehab_id, *params))
    if not rows:
        raise HTTPException(403, "No tienes acceso a este tratamiento o ya no está disponible.")
    patient_id = rows[0][1]
    log_access(conn, user, "LECTURA_TRATAMIENTO", "PERMITIDO", rehab_id, patient_id)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO clinical_visit_log(clinician_dni, patient_id, visit_date)
            VALUES (%s, %s, (NOW() AT TIME ZONE 'Europe/Madrid')::date)
            ON CONFLICT DO NOTHING
        """, (user["dni"], patient_id))
    return patient_id
