"""Usuarios, comprobación de contraseñas y preparación de los catálogos de acceso."""

import hashlib
import hmac
import os
import re
import secrets
from servidor.database import fetch_all, execute_sql


PROFESIONES_DISPONIBLES = [
    "Fisioterapeuta",
    "Terapeuta ocupacional",
    "Logopeda",
    "Médico rehabilitador",
    "Administrador",
]

PASSWORD_TEMPORAL_POR_DEFECTO = "123456789"

PBKDF2_ITERATIONS = 600_000
PASSWORD_HASH_PREFIX = "pbkdf2_sha256$"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    ).hex()

    return f"{PASSWORD_HASH_PREFIX}{PBKDF2_ITERATIONS}${salt.hex()}${password_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(PASSWORD_HASH_PREFIX):
        try:
            _, iterations, salt_hex, expected_hash = stored_hash.split("$")
            calculated_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(salt_hex),
                int(iterations),
            ).hex()
        except (ValueError, TypeError):
            return False

        return hmac.compare_digest(calculated_hash, expected_hash)

    # Compatibilidad con los hashes antiguos
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, stored_hash)


def init_auth_db(conn):
    execute_sql(
        conn,
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            dni TEXT NOT NULL UNIQUE,
            profession TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('ADMIN', 'CLINICO')),
            must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """,
    )

    execute_sql(
        conn,
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS profession TEXT;
    """,
    )

    execute_sql(
        conn,
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;
    """,
    )

    init_professions_db(conn)
    init_visit_log_db(conn)


def init_professions_db(conn):
    execute_sql(
        conn,
        "CREATE TABLE IF NOT EXISTS professions_config (name TEXT PRIMARY KEY, active BOOLEAN NOT NULL DEFAULT TRUE)",
    )
    for profession in PROFESIONES_DISPONIBLES:
        execute_sql(
            conn,
            "INSERT INTO professions_config (name) VALUES (%s) ON CONFLICT DO NOTHING",
            (profession,),
        )
    execute_sql(
        conn,
        "INSERT INTO professions_config (name) SELECT DISTINCT BTRIM(profession) FROM users WHERE profession IS NOT NULL AND BTRIM(profession) <> '' ON CONFLICT DO NOTHING",
    )


def create_user(
    conn, username: str, full_name: str, dni: str, profession: str, role: str
):
    """Registra una cuenta y devuelve si se ha creado sin duplicar usuario ni DNI."""
    password_hash = hash_password(PASSWORD_TEMPORAL_POR_DEFECTO)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (
                username,
                full_name,
                dni,
                profession,
                password_hash,
                role,
                must_change_password,
                active
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE)
            ON CONFLICT DO NOTHING
            RETURNING id
        """,
            (
                username,
                full_name,
                dni,
                profession,
                password_hash,
                role,
            ),
        )

        return cur.fetchone() is not None


def ensure_admin_user(conn):
    """Crea el administrador inicial si no existe; nunca cambia una cuenta existente."""
    _, rows = fetch_all(
        conn,
        "SELECT id FROM users WHERE username = %s",
        ("admin",),
    )

    if rows:
        return

    initial_password = os.getenv("ADMIN_INITIAL_PASSWORD", "").strip()

    if len(initial_password) < 12:
        raise RuntimeError(
            "Configura ADMIN_INITIAL_PASSWORD con al menos "
            "12 caracteres antes de crear el administrador inicial."
        )

    execute_sql(
        conn,
        """
        INSERT INTO users (
            username,
            full_name,
            dni,
            profession,
            password_hash,
            role,
            must_change_password,
            active
        )
        VALUES (%s, %s, %s, %s, %s, %s, TRUE, TRUE)
    """,
        (
            "admin",
            "Administrador del sistema",
            "00000000T",
            "Administrador",
            hash_password(initial_password),
            "ADMIN",
        ),
    )


def authenticate_user(conn, username: str, password: str):
    """Comprueba la contraseña y actualiza el hash antiguo solo tras un acceso válido."""
    username = username.strip()
    if re.fullmatch(r"[0-9]{8}[A-Za-z]", username):
        username = username.upper()

    _, rows = fetch_all(
        conn,
        """
        SELECT id, username, full_name, dni, profession, password_hash, role, must_change_password, active
        FROM users
        WHERE username = %s
        LIMIT 1
    """,
        (username,),
    )

    if not rows:
        return None

    (
        user_id,
        db_username,
        full_name,
        dni,
        profession,
        password_hash,
        role,
        must_change_password,
        active,
    ) = rows[0]

    if not active:
        return None

    if not verify_password(password, password_hash):
        return None

    if not password_hash.startswith(PASSWORD_HASH_PREFIX):
        execute_sql(
            conn,
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(password), user_id),
        )

    return {
        "id": user_id,
        "username": db_username,
        "full_name": full_name,
        "dni": dni,
        "profession": profession,
        "role": role,
        "must_change_password": must_change_password,
    }


def change_user_password(conn, user_id: int, new_password: str):
    new_hash = hash_password(new_password)

    execute_sql(
        conn,
        """
        UPDATE users
        SET password_hash = %s,
            must_change_password = FALSE
        WHERE id = %s
    """,
        (new_hash, user_id),
    )


def reset_user_password_to_default(conn, user_id: int):
    default_hash = hash_password(PASSWORD_TEMPORAL_POR_DEFECTO)

    execute_sql(
        conn,
        """
        UPDATE users
        SET password_hash = %s,
            must_change_password = TRUE
        WHERE id = %s
    """,
        (default_hash, user_id),
    )


def get_all_users(conn):
    _, rows = fetch_all(
        conn,
        """
        SELECT id, username, full_name, dni, profession, role, must_change_password, active, created_at
        FROM users
        ORDER BY username ASC
    """,
    )
    return rows


def init_visit_log_db(conn):
    execute_sql(
        conn,
        """
        CREATE TABLE IF NOT EXISTS clinical_visit_log (
            clinician_dni TEXT NOT NULL,
            patient_id TEXT NOT NULL,
            visit_date DATE NOT NULL,
            PRIMARY KEY (clinician_dni, patient_id, visit_date)
        )
    """,
    )
    execute_sql(
        conn,
        "CREATE INDEX IF NOT EXISTS idx_clinical_visits_date ON clinical_visit_log (visit_date DESC)",
    )
