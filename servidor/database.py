"""Conexión a PostgreSQL y creación de tablas e índices de la aplicación."""

import os
from datetime import datetime, UTC, date, time


def get_database_url() -> str:
    """Solo el servidor tiene DATABASE_URL; la API no lee secretos de Streamlit."""
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError(
            "Configura DATABASE_URL en el entorno del servidor o en .env.api."
        )
    return value


def fetch_all(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [desc.name for desc in cur.description]
        rows = cur.fetchall()
    return cols, rows


def execute_sql(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)


def iso_utc_from_date(d: date) -> str:
    return datetime.combine(d, time.min).replace(tzinfo=UTC).isoformat()


def now_iso():
    return datetime.now(UTC).isoformat()


def init_db(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS specialties_config (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            requires_subspecialty BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS subspecialties_config (
            id BIGSERIAL PRIMARY KEY,
            specialty_name TEXT NOT NULL,
            name TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (specialty_name, name)
        );
        """)

        cur.execute("""
            INSERT INTO specialties_config (name, active, requires_subspecialty)
            VALUES
                ('Electroterapia', TRUE, FALSE),
                ('Terapia ocupacional', TRUE, FALSE),
                ('Logopedia', TRUE, FALSE),
                ('Cinesiterapia', TRUE, TRUE)
            ON CONFLICT (name) DO NOTHING;
        """)

        for area in [
            "Linfedema",
            "Suelo pélvico",
            "Infantil",
            "FT respiratorio",
            "RHB cardiaca",
            "RHB neurológica",
            "Columna/raquis",
            "General",
        ]:
            cur.execute(
                """
                INSERT INTO subspecialties_config (specialty_name, name, active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (specialty_name, name) DO NOTHING;
            """,
                ("Cinesiterapia", area),
            )

        cur.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id BIGSERIAL PRIMARY KEY,
            patient_id TEXT NOT NULL,
            priority_level TEXT NOT NULL CHECK(priority_level IN ('personal SACYL', 'urgente','preferente','ordinario')),
            specialty TEXT NOT NULL,
            subspecialty TEXT,
            prescribed_sessions INTEGER,
            slot_type TEXT,
            time_preference TEXT,
            transport_mode TEXT,
            preferred_hour TEXT,
            coordination_rule TEXT,
            request_date TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'EN_ESPERA',
            eligible BOOLEAN NOT NULL DEFAULT TRUE
        );
        """)

        cur.execute("""
            ALTER TABLE waitlist
            DROP CONSTRAINT IF EXISTS waitlist_priority_level_check;
        """)

        cur.execute("""
            ALTER TABLE waitlist
            ADD CONSTRAINT waitlist_priority_level_check
            CHECK (
                priority_level IN (
                    'personal SACYL',
                    'urgente',
                    'preferente',
                    'ordinario'
                )
            );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS rehab_active (
            id BIGSERIAL PRIMARY KEY,
            patient_id TEXT NOT NULL,
            specialty TEXT NOT NULL,
            subspecialty TEXT,
            prescribed_sessions INTEGER,
            slot_type TEXT,
            time_preference TEXT,
            transport_mode TEXT,
            preferred_hour TEXT,
            coordination_rule TEXT,
            attendance_days TEXT,
            start_date TIMESTAMPTZ NOT NULL,
            source_waitlist_id BIGINT NOT NULL,
            assigned_by TEXT NOT NULL,
            assigned_at TIMESTAMPTZ NOT NULL,
            assigned_clinician_dni TEXT,
            assigned_clinician_name TEXT,
            assigned_clinician_profession TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVO',
            discharge_reason TEXT,
            discharge_comment TEXT,
            discharged_at TIMESTAMPTZ,
            FOREIGN KEY(source_waitlist_id) REFERENCES waitlist(id)
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS assignment_log (
            id BIGSERIAL PRIMARY KEY,
            event TEXT NOT NULL,
            waitlist_id BIGINT,
            rehab_active_id BIGINT,
            session_id BIGINT,
            patient_id TEXT NOT NULL,
            specialty TEXT,
            subspecialty TEXT,
            chosen_priority_level TEXT,
            wait_days INTEGER,
            rule_applied TEXT,
            reason TEXT,
            comment TEXT,
            actor TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS treatment_sessions (
            id BIGSERIAL PRIMARY KEY,
            rehab_active_id BIGINT NOT NULL,
            patient_id TEXT NOT NULL,
            specialty TEXT NOT NULL,
            subspecialty TEXT,
            session_date DATE NOT NULL,
            session_time TIME,
            status TEXT NOT NULL,
            absence_reason TEXT,
            out_of_schedule_reason TEXT,
            recorded_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            FOREIGN KEY(rehab_active_id) REFERENCES rehab_active(id)
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS patient_ai_consent (
            patient_id TEXT PRIMARY KEY,
            accepted BOOLEAN NOT NULL,
            decided_at TIMESTAMPTZ NOT NULL,
            decided_by TEXT NOT NULL,
            consent_version TEXT NOT NULL
        );
        """)

        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS discharge_comment TEXT;"
        )
        cur.execute("ALTER TABLE assignment_log ADD COLUMN IF NOT EXISTS comment TEXT;")
        cur.execute(
            "ALTER TABLE assignment_log ADD COLUMN IF NOT EXISTS session_id BIGINT;"
        )
        cur.execute(
            "ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS prescribed_sessions INTEGER;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS prescribed_sessions INTEGER;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS attendance_days TEXT;"
        )
        cur.execute(
            "ALTER TABLE treatment_sessions ADD COLUMN IF NOT EXISTS out_of_schedule_reason TEXT;"
        )

        cur.execute(
            "ALTER TABLE treatment_sessions ADD COLUMN IF NOT EXISTS clinical_note TEXT;"
        )
        cur.execute(
            "ALTER TABLE treatment_sessions ADD COLUMN IF NOT EXISTS pain_eva INTEGER;"
        )
        cur.execute(
            "ALTER TABLE treatment_sessions ADD COLUMN IF NOT EXISTS functional_status TEXT;"
        )
        cur.execute(
            "ALTER TABLE treatment_sessions ADD COLUMN IF NOT EXISTS goal_status TEXT;"
        )
        cur.execute(
            "ALTER TABLE treatment_sessions ADD COLUMN IF NOT EXISTS incidents TEXT;"
        )

        cur.execute("ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS slot_type TEXT;")
        cur.execute(
            "ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS time_preference TEXT;"
        )
        cur.execute(
            "ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS transport_mode TEXT;"
        )
        cur.execute(
            "ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS preferred_hour TEXT;"
        )
        cur.execute(
            "ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS coordination_rule TEXT;"
        )

        cur.execute("ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS slot_type TEXT;")
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS time_preference TEXT;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS transport_mode TEXT;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS preferred_hour TEXT;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS coordination_rule TEXT;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS assigned_clinician_dni TEXT;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS assigned_clinician_name TEXT;"
        )
        cur.execute(
            "ALTER TABLE rehab_active ADD COLUMN IF NOT EXISTS assigned_clinician_profession TEXT;"
        )

        # Índices para filtrar listados y localizar sesiones y referencias.
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_waitlist_pending_filters ON waitlist (specialty, subspecialty, request_date, id) WHERE status = 'EN_ESPERA' AND eligible = TRUE"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_rehab_status_id ON rehab_active (status, id DESC)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_rehab_source_waitlist ON rehab_active (source_waitlist_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_treatment_date ON treatment_sessions (rehab_active_id, session_date, id)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_rehab_patient_active ON rehab_active (patient_id, id DESC) WHERE status = 'ACTIVO'"
        )
