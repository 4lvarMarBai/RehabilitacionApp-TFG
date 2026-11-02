"""Ejecutar una vez en el servidor: python -m api.init_db."""

from pathlib import Path

import psycopg
from dotenv import load_dotenv

from api.security import init_api_auth
from servidor.auth import ensure_admin_user, init_auth_db
from servidor.database import get_database_url, init_db


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / "configuracion" / ".env.api")
    with psycopg.connect(get_database_url(), autocommit=True) as conn:
        with conn.transaction():
            init_db(conn)
            init_auth_db(conn)
            init_api_auth(conn)
            ensure_admin_user(conn)
    print("Tablas preparadas. No se han insertado pacientes de prueba.")


if __name__ == "__main__":
    main()
