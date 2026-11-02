"""Sesiones, permisos y límites de intentos de inicio de sesión."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.db import get_conn


bearer = HTTPBearer(auto_error=False)
SESSION_MINUTES = 30


def init_api_auth(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS api_sessions_expiry_idx ON api_sessions(expires_at)"
        )
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_login_limits (
                bucket TEXT PRIMARY KEY,
                window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                attempts INTEGER NOT NULL DEFAULT 1
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS api_login_window_idx ON api_login_limits(window_started_at)"
        )


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(conn, user_id: int):
    """Entrega un token nuevo y guarda únicamente su hash para poder revocarlo."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=SESSION_MINUTES)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM api_sessions WHERE expires_at <= NOW()")
        cur.execute(
            "INSERT INTO api_sessions(token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (token_hash(token), user_id, expires_at),
        )
    return token, expires_at


def limit_login(conn, request: Request, username: str):
    """Contadores atómicos compartidos por todos los procesos del servidor."""
    client_ip = request.client.host if request.client else "unknown"
    buckets = (
        ("ip:" + token_hash(client_ip), 100),
        ("user:" + token_hash(username.lower()), 20),
    )
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM api_login_limits WHERE window_started_at < NOW() - INTERVAL '1 day'"
        )
        for bucket, maximum in buckets:
            cur.execute(
                """
                INSERT INTO api_login_limits(bucket) VALUES (%s)
                ON CONFLICT (bucket) DO UPDATE SET
                    attempts = CASE
                        WHEN api_login_limits.window_started_at < NOW() - INTERVAL '15 minutes' THEN 1
                        ELSE api_login_limits.attempts + 1
                    END,
                    window_started_at = CASE
                        WHEN api_login_limits.window_started_at < NOW() - INTERVAL '15 minutes' THEN NOW()
                        ELSE api_login_limits.window_started_at
                    END
                RETURNING attempts
            """,
                (bucket,),
            )
            if cur.fetchone()[0] > maximum:
                raise HTTPException(
                    429,
                    "Demasiados intentos. Espera antes de volver a intentarlo.",
                    headers={"Retry-After": "900"},
                )


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    conn=Depends(get_conn),
):
    """Comprueba que el token siga vigente y que el usuario permanezca activo."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            401, "Inicia sesión.", headers={"WWW-Authenticate": "Bearer"}
        )
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.username, u.full_name, u.dni, u.profession,
                   u.role, u.must_change_password
            FROM api_sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > NOW() AND u.active = TRUE
        """,
            (token_hash(credentials.credentials),),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            401,
            "La sesión ha caducado o ha sido revocada.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return dict(
        zip(
            (
                "id",
                "username",
                "full_name",
                "dni",
                "profession",
                "role",
                "must_change_password",
            ),
            row,
        )
    )


def ready_user(user=Depends(current_user)):
    """Exige un rol admitido y el cambio de contraseña cuando sea obligatorio."""
    if user["must_change_password"]:
        raise HTTPException(403, "Debes cambiar la contraseña antes de continuar.")
    if user["role"] not in {"ADMIN", "CLINICO"}:
        raise HTTPException(403, "Rol no autorizado.")
    return user


def admin_user(user=Depends(ready_user)):
    """Restringe las funciones administrativas en el servidor."""
    if user["role"] != "ADMIN":
        raise HTTPException(403, "Esta operación requiere un administrador.")
    return user
