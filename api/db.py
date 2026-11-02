"""Pool de PostgreSQL y préstamo de una conexión por petición."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from psycopg_pool import ConnectionPool

from servidor.database import get_database_url
from servidor.auth import init_professions_db, init_visit_log_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = ConnectionPool(
        conninfo=get_database_url(),
        min_size=1,
        max_size=5,
        timeout=20,
        kwargs={"autocommit": True},
        open=False,
    )
    try:
        pool.open(wait=True, timeout=30)
        with pool.connection() as conn:
            with conn.transaction():
                init_professions_db(conn)
                init_visit_log_db(conn)
        app.state.pool = pool
        yield
    finally:
        pool.close()


def get_conn(request: Request):
    """Una conexión por petición, devuelta al pool al finalizar."""
    with request.app.state.pool.connection(timeout=20) as conn:
        yield conn
