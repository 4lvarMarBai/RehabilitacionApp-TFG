"""Comprobaciones de la API activa, PostgreSQL y HTTPS/Caddy."""
import argparse
import json
from pathlib import Path
import ssl
import sys
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPSHandler, ProxyHandler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--api-url',default='http://127.0.0.1:8000')
    parser.add_argument('--https-url',default='https://localhost')
    parser.add_argument('--ca',type=Path,help='CA pública de la instalación; se comprueba su certificado.')
    args=parser.parse_args()
    repo=args.repo.resolve()
    api=args.api_url.rstrip('/')
    https=args.https_url.rstrip('/')
    if not https.startswith('https://'):
        parser.error('--https-url debe utilizar HTTPS.')
    results=[]

    def check(name, action):
        try:
            action()
        except Exception as exc:
            # Evitar imprimir conexiones, credenciales o datos de pacientes.
            results.append((name,False))
            print(f'FALLO: {name} ({type(exc).__name__}).')
        else:
            results.append((name,True))
            print(f'CORRECTO: {name}.')

    def require(value,message):
        if not value:
            raise AssertionError(message)

    def request(url,method='GET',data=None,context=None):
        handlers=[ProxyHandler({})]
        if context is not None:
            handlers.append(HTTPSHandler(context=context))
        opener=build_opener(*handlers)
        req=Request(url,data=data,method=method,
                    headers={'Content-Type':'application/json'} if data is not None else {})
        try:
            with opener.open(req,timeout=15) as response:
                return response.status,response.read(65536),response.headers
        except HTTPError as response:
            return response.code,b'',response.headers

    def health():
        status,body,_=request(api+'/health')
        require(status==200 and json.loads(body).get('status')=='ok','La API no responde correctamente.')

    def authentication():
        for path in ('/stats','/admin/users'):
            status,_,_=request(api+path)
            require(status==401,'La ruta protegida no rechaza el acceso anónimo.')
        status,_,_=request(api+'/treatments/1/ai-summary','POST',
                          b'{"synthetic_data_confirmed":true}')
        require(status==401,'La generación de IA no rechaza el acceso anónimo.')

    def postgres():
        sys.path.insert(0,str(repo))
        from dotenv import load_dotenv
        import psycopg
        from servidor.database import get_database_url
        load_dotenv(repo/'configuracion/.env.api')
        with psycopg.connect(get_database_url(),autocommit=True,connect_timeout=15) as conn:
            require(conn.execute('SELECT 1').fetchone()==(1,),'PostgreSQL no responde.')
            for table in ('users','waitlist','rehab_active','treatment_sessions',
                          'assignment_log','patient_ai_consent','api_sessions'):
                require(conn.execute('SELECT to_regclass(%s)',(table,)).fetchone()[0] is not None,
                        'Falta una tabla necesaria.')
            # Comprobar las columnas sin obtener registros clínicos.
            conn.execute('SELECT initial_note,initial_note_author FROM waitlist LIMIT 0')
            conn.execute('''SELECT clinical_note,pain_eva,knee_flexion_deg,
                knee_extension_deficit_deg,tug_seconds,tug_conditions,koos_jr_raw
                FROM treatment_sessions LIMIT 0''')
            conn.execute('CREATE TEMP TABLE prueba_tfg_transaccion (value INTEGER)')
            with conn.transaction(force_rollback=True):
                conn.execute('INSERT INTO prueba_tfg_transaccion VALUES (1)')
                require(conn.execute('SELECT COUNT(*) FROM prueba_tfg_transaccion').fetchone()[0]==1,
                        'No se ha guardado la fila temporal.')
            require(conn.execute('SELECT COUNT(*) FROM prueba_tfg_transaccion').fetchone()[0]==0,
                    'El rollback no ha deshecho la inserción.')

    def caddy():
        ca=args.ca or repo/'datos/https/caddy/pki/authorities/local/root.crt'
        context=ssl.create_default_context(cafile=str(ca))
        status,_,headers=request(https,context=context)
        require(status==200,'La interfaz no responde a través de HTTPS.')
        for key,value in (('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),
                          ('Referrer-Policy','no-referrer')):
            require(headers.get(key,'').lower()==value.lower(),'Falta una cabecera de seguridad.')
        require('no-store' in headers.get('Cache-Control',''),'Falta la protección de caché.')
        status,body,_=request(https+'/_stcore/health',context=context)
        require(status==200 and body.strip().lower()==b'ok',
                'Streamlit no responde a través del proxy HTTPS.')

    check('API: respuesta de /health',health)
    check('API e IA: rechazo de accesos sin iniciar sesión',authentication)
    check('PostgreSQL: conexión, tablas, columnas y rollback temporal',postgres)
    check('HTTPS/Caddy: certificado, interfaz, cabeceras y proxy hacia Streamlit',caddy)
    print(f'Resultado: {sum(ok for _,ok in results)}/{len(results)} bloques correctos.')
    print('No se han generado resúmenes ni modificado registros permanentes de pacientes.')
    return 0 if all(ok for _,ok in results) else 1


if __name__=='__main__':
    raise SystemExit(main())
