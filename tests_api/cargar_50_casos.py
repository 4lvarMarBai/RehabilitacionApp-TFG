"""Carga exclusivamente los casos ficticios."""
import argparse
from datetime import date, datetime, time, UTC
import hashlib
import json
from pathlib import Path
import sys


ACTOR = 'CARGA_FICTICIA_50_CASOS_228_NOTAS'


def read_cases(path):
    cases = json.loads(path.read_text(encoding='utf-8'))
    if len(cases) != 50 or sum(len(c['source']) for c in cases) != 228:
        raise ValueError('Se esperan 50 casos y 228 notas de origen.')
    for case in cases:
        for note in case['source']:
            date.fromisoformat(note['date'])
            if not isinstance(note['clinical_note'],str) or not note['clinical_note'].strip():
                raise ValueError('Una nota está vacía o no tiene formato válido.')
    return cases


def load_cases(conn, cases, clinician_dni, specialty, area):
    """El llamante agrupa la importación en una transacción."""
    from servidor import services as svc
    fingerprint = hashlib.sha256(json.dumps(cases,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    marker = ACTOR + ':' + fingerprint[:12]
    conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(marker,))
    if conn.execute('SELECT 1 FROM assignment_log WHERE actor=%s LIMIT 1',(marker,)).fetchone():
        raise ValueError('Este conjunto ya se ha cargado; no se duplica.')
    clinician = conn.execute('''SELECT dni,full_name,profession FROM users
        WHERE dni=%s AND role='CLINICO' AND active AND NOT on_leave
          AND NOT must_change_password''',(clinician_dni,)).fetchone()
    if not clinician:
        raise ValueError('Debe indicar un clínico activo, sin baja y con el primer acceso completado.')
    spec = conn.execute('SELECT requires_subspecialty FROM specialties_config WHERE name=%s AND active',
                        (specialty,)).fetchone()
    if not spec:
        raise ValueError('La especialidad no existe o está desactivada.')
    if spec[0] and not area:
        raise ValueError('Esta especialidad requiere un área.')
    if area and not conn.execute('''SELECT 1 FROM subspecialties_config
        WHERE specialty_name=%s AND name=%s AND active''',(specialty,area)).fetchone():
        raise ValueError('El área no existe o está desactivada para esta especialidad.')
    used = {r[0] for r in conn.execute('''SELECT patient_id FROM waitlist
        UNION SELECT patient_id FROM rehab_active
        UNION SELECT patient_id FROM patient_ai_consent''').fetchall()}
    nhcs=[]
    for number in range(900000,1000000):
        nhc=f'{number:06d}'
        if nhc not in used:
            nhcs.append(nhc)
            if len(nhcs)==len(cases):
                break
    if len(nhcs)!=len(cases):
        raise ValueError('No hay suficientes NHC libres en el intervalo ficticio elegido.')
    records=[]
    for nhc,case in zip(nhcs,cases):
        notes=sorted(case['source'],key=lambda item:item['date'])
        first=date.fromisoformat(notes[0]['date'])
        first_at=datetime.combine(first,time(9),UTC)
        annotation='CASO FICTICIO para revisión manual. Caso: '+case['case']
        wid=conn.execute('''INSERT INTO waitlist
            (patient_id,priority_level,specialty,subspecialty,prescribed_sessions,
             initial_note,initial_note_author,slot_type,time_preference,transport_mode,
             coordination_rule,request_date,created_at,status,eligible)
            VALUES (%s,'ordinario',%s,%s,%s,%s,%s,'SIMPLE','MAÑANA','NORMAL',
                    'NINGUNA',%s,NOW(),'ASIGNADO',TRUE) RETURNING id''',
            (nhc,specialty,area,len(notes),annotation,marker,first_at)).fetchone()[0]
        rid=conn.execute('''INSERT INTO rehab_active
            (patient_id,specialty,subspecialty,prescribed_sessions,slot_type,time_preference,
             transport_mode,coordination_rule,attendance_days,start_date,source_waitlist_id,
             assigned_by,assigned_at,assigned_clinician_dni,assigned_clinician_name,
             assigned_clinician_profession,status)
            VALUES (%s,%s,%s,%s,'SIMPLE','MAÑANA','NORMAL','NINGUNA',
                    'Lunes,Martes,Miércoles,Jueves,Viernes',%s,%s,%s,NOW(),%s,%s,%s,'ACTIVO')
            RETURNING id''',(nhc,specialty,area,len(notes),first_at,wid,marker,*clinician)).fetchone()[0]
        for event in ('CREACION_SOLICITUD','ASIGNACION'):
            conn.execute('''INSERT INTO assignment_log
                (event,waitlist_id,rehab_active_id,patient_id,specialty,subspecialty,
                 reason,comment,actor,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,'CARGA_FICTICIA',%s,%s,NOW())''',
                (event,wid,rid,nhc,specialty,area,annotation,marker))
        for note in notes:
            svc.add_treatment_session(conn,rid,nhc,specialty,area,
                date.fromisoformat(note['date']),time(9),'REALIZADA','',
                'Carga histórica ficticia para revisión manual.',marker,
                note['clinical_note'],note.get('pain_eva'),note.get('functional_status',''),
                note.get('goal_status',''),note.get('incidents',''))
        records.append(dict(nhc=nhc,tratamiento=rid,caso=case['case'],notas=len(notes)))
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--datos',type=Path,default=Path(__file__).with_name('datos_50_casos.json'))
    parser.add_argument('--clinico-dni')
    parser.add_argument('--especialidad',default='Cinesiterapia')
    parser.add_argument('--area',default='General')
    parser.add_argument('--aplicar',action='store_true',help='Guarda de forma permanente en la base configurada.')
    args=parser.parse_args()
    cases=read_cases(args.datos)
    print('Preparados 50 casos ficticios y 228 notas; no se incluyen resúmenes ni evaluaciones.')
    if not args.aplicar:
        print('Vista previa: no se ha conectado a PostgreSQL ni guardado ningún dato.')
        return
    if not args.clinico_dni:
        parser.error('--aplicar requiere --clinico-dni con un clínico de la instalación de pruebas.')
    sys.path.insert(0,str(args.repo.resolve()))
    from dotenv import load_dotenv
    import psycopg
    from servidor.database import get_database_url
    load_dotenv(args.repo/'configuracion/.env.api')
    with psycopg.connect(get_database_url(),autocommit=True,connect_timeout=15) as conn:
        with conn.transaction():
            records=load_cases(conn,cases,args.clinico_dni.upper(),args.especialidad,args.area or None)
    print('Carga guardada:')
    for row in records:
        print(json.dumps(row,ensure_ascii=False))
    print('No se ha registrado aceptación del uso de IA ni se ha generado ningún borrador.')
    print('Los NHC y tratamientos indicados ya pueden consultarse en la aplicación de pruebas.')


if __name__=='__main__':
    main()
