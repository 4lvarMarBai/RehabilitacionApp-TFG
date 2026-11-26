"""Comprueba la paginación HTTP con 1.105 solicitudes en PostgreSQL temporal."""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo))
    from dotenv import load_dotenv
    import psycopg
    from fastapi.testclient import TestClient
    from api.main import app
    from api.db import get_conn
    from api.security import current_user
    from servidor.database import get_database_url

    load_dotenv(repo / 'configuracion/.env.api')
    user = dict(id=1, dni='00000001R', role='ADMIN',
                profession='Administrador', must_change_password=False)
    checks = 0

    def check(condition, label):
        nonlocal checks
        if not condition:
            raise AssertionError(label)
        checks += 1

    with psycopg.connect(get_database_url(), autocommit=True, connect_timeout=15) as conn:
        with conn.transaction(force_rollback=True):
            # Solo se crea esta tabla temporal; no se insertan solicitudes en la app.
            conn.execute('SET LOCAL search_path TO pg_temp')
            conn.execute('''CREATE TEMP TABLE waitlist (
                id BIGINT PRIMARY KEY, patient_id TEXT, priority_level TEXT,
                specialty TEXT, subspecialty TEXT, prescribed_sessions INTEGER,
                request_date TIMESTAMPTZ, eligible BOOLEAN, status TEXT)''')
            conn.execute('''INSERT INTO waitlist
                SELECT n, LPAD(n::text,6,'0'), 'ordinario',
                    CASE WHEN n%2=0 THEN 'Área A' ELSE 'Área B' END,
                    NULL, 10, TIMESTAMPTZ '2026-01-01 09:00:00+00' + (n%7)*INTERVAL '1 day',
                    n%3<>0, 'EN_ESPERA'
                FROM generate_series(1,1105) n''')
            old = dict(app.dependency_overrides)
            app.dependency_overrides[get_conn] = lambda: conn
            app.dependency_overrides[current_user] = lambda: user
            # Sin context manager: no ejecutar lifespan ni abrir otro pool.
            client = TestClient(app, raise_server_exceptions=True)
            try:
                for filters, where in [({}, 'TRUE'),
                        ({'specialty':'Área A'}, "specialty='Área A'"),
                        ({'eligible_only':True}, 'eligible=TRUE')]:
                    expected = [r[0] for r in conn.execute(
                        f'SELECT id FROM waitlist WHERE {where} ORDER BY request_date,id').fetchall()]
                    for size in (25,50,100):
                        found = []
                        pages = (len(expected)+size-1)//size
                        for page in range(1,pages+1):
                            response = client.get('/tables/waiting', params={
                                **filters,'page':page,'page_size':size})
                            check(response.status_code==200, 'Respuesta HTTP')
                            result = response.json()
                            check(result['total']==len(expected), 'Total del filtro')
                            check(result['total_pages']==pages, 'Número de páginas')
                            check(len(result['rows'])<=size, 'Tamaño de página')
                            found.extend(row[0] for row in result['rows'])
                        check(found==expected, 'Orden, omisiones y duplicados')
                        response = client.get('/tables/waiting',params={
                            **filters,'page':999,'page_size':size})
                        check(response.status_code==200 and response.json()['page']==pages,
                              'Reajuste a la última página')
                for params in ({'page':0},{'page':-1},{'page_size':0},{'page_size':101}):
                    check(client.get('/tables/waiting',params=params).status_code==422,
                          'Parámetros inválidos')
                response=client.get('/tables/waiting',params={'patient_id':'999999','page':999})
                check(response.status_code==200 and response.json()['rows']==[]
                      and response.json()['total']==0 and response.json()['page']==1,
                      'Filtro sin coincidencias')
            finally:
                client.close()
                app.dependency_overrides.clear()
                app.dependency_overrides.update(old)
    print(f'Correcto: {checks} comprobaciones. Tabla temporal y cambios descartados.')
    print('Prueba de paginación y SQL; la identidad se simula, no se prueba el inicio de sesión.')


if __name__ == '__main__':
    main()
