# app.py
# Prototipo de gestión de pacientes en rehabilitación.
# Versión inicial con la lógica dentro de un único archivo.

import sqlite3
from datetime import date, datetime
from pathlib import Path
import hashlib
import hmac
import secrets
import os

import pandas as pd
import streamlit as st


# ============================================================
# 1. CONFIGURACIÓN Y CATÁLOGOS
# ============================================================

st.set_page_config(
    page_title="Gestión de Rehabilitación",
    page_icon="🏥",
    layout="wide",
)

DB_PATH = Path(__file__).with_name("rehabilitacion.db")

PRIORIDADES = ["urgente", "preferente", "ordinario"]
TIPOS_HUECO = ["SIMPLE", "DOBLE"]
TURNOS = ["MAÑANA", "TARDE"]
TRANSPORTES = ["NORMAL", "AMBULANCIA"]
HORAS_AMBULANCIA = ["09:00", "12:00"]

REGLAS_COORDINACION = [
    "NINGUNA",
    "MISMO_DIA",
    "DIAS_ALTERNOS",
]

PATRONES_ASISTENCIA = {
    "LXV": ["Lunes", "Miércoles", "Viernes"],
    "MJ": ["Martes", "Jueves"],
    "LABORABLES": [
        "Lunes",
        "Martes",
        "Miércoles",
        "Jueves",
        "Viernes",
    ],
}

ESTADOS_SESION = [
    "REALIZADA",
    "REVISION",
    "FALTA_JUSTIFICADA",
    "FALTA_NO_JUSTIFICADA",
]

MOTIVOS_ALTA = [
    "FIN_TRATAMIENTO",
    "NO_ASISTE",
    "DERIVADO",
    "OTRO",
]

ESPECIALIDADES_INICIALES = {
    "Fisioterapia": ["Electroterapia", "Cinesiterapia"],
    "Terapia ocupacional": ["General"],
    "Logopedia": ["General"],
    "Rehabilitación neurológica": ["General"],
}

USUARIO_ADMIN = "host"
PASSWORD_TEMPORAL = "123456789"
PASSWORD_HOST = os.environ.get("PASSWORD_HOST", "").strip()

# ============================================================
# 2. BASE DE DATOS
# ============================================================

def conectar_db():
    """Abre una conexión a la base de datos local."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar_db(conn):
    """Crea las tablas si todavía no existen."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS especialidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            activa INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            especialidad_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1,
            UNIQUE(especialidad_id, nombre),
            FOREIGN KEY(especialidad_id)
                REFERENCES especialidades(id)
        );

        CREATE TABLE IF NOT EXISTS solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nhc TEXT NOT NULL,
            prioridad TEXT NOT NULL,
            especialidad TEXT NOT NULL,
            area TEXT,
            sesiones_previstas INTEGER,
            fecha_solicitud TEXT NOT NULL,
            elegible INTEGER NOT NULL DEFAULT 1,
            tipo_hueco TEXT NOT NULL,
            turno TEXT NOT NULL,
            transporte TEXT NOT NULL,
            hora_ambulancia TEXT,
            regla_coordinacion TEXT NOT NULL DEFAULT 'NINGUNA',
            estado TEXT NOT NULL DEFAULT 'EN_ESPERA',
            creado_en TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tratamientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitud_id INTEGER NOT NULL,
            nhc TEXT NOT NULL,
            especialidad TEXT NOT NULL,
            area TEXT,
            prioridad TEXT NOT NULL,
            sesiones_previstas INTEGER,
            dias_asistencia TEXT NOT NULL,
            fecha_inicio TEXT NOT NULL,
            tipo_hueco TEXT,
            turno TEXT,
            transporte TEXT,
            hora_ambulancia TEXT,
            regla_coordinacion TEXT,
            profesional TEXT,
            estado TEXT NOT NULL DEFAULT 'ACTIVO',
            motivo_alta TEXT,
            comentario_alta TEXT,
            fecha_alta TEXT,
            FOREIGN KEY(solicitud_id)
                REFERENCES solicitudes(id)
        );

        CREATE TABLE IF NOT EXISTS sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tratamiento_id INTEGER NOT NULL,
            nhc TEXT NOT NULL,
            especialidad TEXT NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT,
            estado TEXT NOT NULL,
            motivo_ausencia TEXT,
            motivo_fuera_horario TEXT,
            nota_clinica TEXT,
            eva INTEGER,
            estado_funcional TEXT,
            estado_objetivo TEXT,
            incidencias TEXT,
            registrado_en TEXT NOT NULL,
            FOREIGN KEY(tratamiento_id)
                REFERENCES tratamientos(id)
        );

        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento TEXT NOT NULL,
            nhc TEXT,
            detalle TEXT,
            actor TEXT NOT NULL,
            fecha TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            nombre_completo TEXT NOT NULL,
            dni TEXT NOT NULL UNIQUE,
            profesion TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('ADMIN', 'CLINICO')),
            activo INTEGER NOT NULL DEFAULT 1,
            debe_cambiar_password INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL
        );
        """
    )

    columnas_usuarios = {
        fila["name"]
        for fila in conn.execute("PRAGMA table_info(usuarios)").fetchall()
    }
    if "debe_cambiar_password" not in columnas_usuarios:
        conn.execute(
            "ALTER TABLE usuarios ADD COLUMN debe_cambiar_password INTEGER NOT NULL DEFAULT 1"
        )
        conn.commit()

    for especialidad, areas in ESPECIALIDADES_INICIALES.items():
        columnas_usuarios = {
            fila["name"]
            for fila in conn.execute("PRAGMA table_info(usuarios)").fetchall()
        }

        if "debe_cambiar_password" not in columnas_usuarios:
            conn.execute(
                """
                ALTER TABLE usuarios
                ADD COLUMN debe_cambiar_password INTEGER NOT NULL DEFAULT 1
                """
            )
            conn.commit()
        conn.execute(
            "INSERT OR IGNORE INTO especialidades(nombre) VALUES (?)",
            (especialidad,),
        )

        for area in areas:
            conn.execute(
                """
                INSERT OR IGNORE INTO areas(especialidad_id, nombre)
                SELECT id, ?
                FROM especialidades
                WHERE nombre = ?
                """,
                (area, especialidad),
            )

    conn.commit()


conn = conectar_db()
inicializar_db(conn)

if "usuario_actual" not in st.session_state:
    st.session_state["usuario_actual"] = None

if st.session_state["usuario_actual"] is None:
    st.title("Acceso al sistema")

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Iniciar sesión"):
        usuario = autenticar_usuario(username, password)

        if usuario:
            st.session_state["usuario_actual"] = usuario
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")

    if not conn.execute(
        "SELECT 1 FROM usuarios LIMIT 1"
    ).fetchone():
        st.info(
            "Todavía no hay usuarios. Configura ADMIN_INITIAL_PASSWORD "
            "con una contraseña de al menos 12 caracteres y reinicia la app."
        )

    st.stop()


# ============================================================
# 3. FUNCIONES COMUNES
# ============================================================
ITERACIONES_PBKDF2 = 600_000


def hash_password(password):
    """Genera un hash de contraseña con sal aleatoria."""
    salt = secrets.token_bytes(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERACIONES_PBKDF2,
    )

    return (
        f"pbkdf2_sha256${ITERACIONES_PBKDF2}"
        f"${salt.hex()}${derived_key.hex()}"
    )


def verificar_password(password, password_hash):
    """Comprueba la contraseña frente al hash guardado."""
    try:
        algoritmo, iteraciones_texto, salt_hex, hash_guardado = (
            password_hash.split("$", maxsplit=3)
        )

        if algoritmo != "pbkdf2_sha256":
            return False

        hash_calculado = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iteraciones_texto),
        ).hex()

        return hmac.compare_digest(hash_calculado, hash_guardado)

    except (ValueError, TypeError):
        return False


def crear_usuario(
    username,
    nombre_completo,
    dni,
    profesion,
    password,
    role="CLINICO",
):
    """Crea un usuario en la base SQLite actual."""
    username = username.strip().lower()
    nombre_completo = nombre_completo.strip()
    dni = dni.strip().upper()

    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")

    if role not in ("ADMIN", "CLINICO"):
        raise ValueError("El rol debe ser ADMIN o CLINICO.")

    conn.execute(
        """
        INSERT INTO usuarios (
            username,
            nombre_completo,
            dni,
            profesion,
            password_hash,
            role,
            activo,
            debe_cambiar_password,
            creado_en
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?)
        """,
        (
            username,
            nombre_completo,
            dni,
            profesion,
            hash_password(password),
            role,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()

def asegurar_admin_host():
    """Crea host una sola vez usando una contrasena configurada externamente."""
    fila = conn.execute(
        "SELECT role, activo FROM usuarios WHERE username = ?",
        (USUARIO_ADMIN,),
    ).fetchone()

    if fila:
        if fila["role"] != "ADMIN" or not fila["activo"]:
            raise RuntimeError(
                "La cuenta host existe, pero no est? activa con rol ADMIN."
            )
        return

    password_inicial = os.environ.get("HOST_ADMIN_PASSWORD", "").strip()
    if len(password_inicial) < 16:
        raise RuntimeError(
            "Define HOST_ADMIN_PASSWORD en el entorno con al menos "
            "16 caracteres antes del primer inicio."
        )

    crear_usuario(
        username=USUARIO_ADMIN,
        nombre_completo="Administrador del sistema",
        dni="HOST-ADMIN",
        profesion="Administrador",
        password=password_inicial,
        role="ADMIN",
    )


def autenticar_usuario(username, password):
    """Devuelve el usuario si las credenciales son válidas."""
    fila = conn.execute(
        """
        SELECT id, username, nombre_completo, dni, profesion,
               role, password_hash, activo, debe_cambiar_password
        FROM usuarios
        WHERE username = ?
        LIMIT 1
        """,
        (username.strip().lower(),),
    ).fetchone()

    if fila is None or not fila["activo"]:
        return None

    if not verificar_password(password, fila["password_hash"]):
        return None

    return {
        "id": fila["id"],
        "username": fila["username"],
        "nombre_completo": fila["nombre_completo"],
        "dni": fila["dni"],
        "profesion": fila["profesion"],
        "role": fila["role"],
        "debe_cambiar_password": bool(fila["debe_cambiar_password"]),
    }

def exigir_admin():
    usuario = st.session_state.get("usuario_actual")

    if not usuario or usuario.get("role") != "ADMIN":
        st.error("Esta acción requiere permisos de administrador.")
        st.stop()

def pagina_administracion():
    exigir_admin()
    st.title("Administración de usuarios")
    st.caption(
        "Las cuentas nuevas reciben una contraseña temporal aleatoria y "
        "deben cambiarla al iniciar sesión."
    )

    with st.form("formulario_nuevo_usuario"):
        username_nuevo = st.text_input("Nombre de usuario").strip().lower()
        nombre_nuevo = st.text_input("Nombre completo").strip()
        dni_nuevo = st.text_input("DNI").strip().upper()
        profesion_nueva = st.text_input("Profesión").strip()
        rol_nuevo = st.selectbox("Rol", ["CLINICO", "ADMIN"])
        crear_nuevo = st.form_submit_button("Crear usuario")

    if crear_nuevo:
        exigir_admin()
        if not all((username_nuevo, nombre_nuevo, dni_nuevo, profesion_nueva)):
            st.error("Completa todos los campos.")
        else:
            password_temporal_nueva = secrets.token_urlsafe(18)
            try:
                crear_usuario(
                    username=username_nuevo,
                    nombre_completo=nombre_nuevo,
                    dni=dni_nuevo,
                    profesion=profesion_nueva,
                    password=password_temporal_nueva,
                    role=rol_nuevo,
                )
            except sqlite3.IntegrityError:
                st.error("Ese nombre de usuario o DNI ya está registrado.")
            else:
                st.success(
                    f"Usuario {username_nuevo} creado. "
                    f"Contraseña temporal (muéstrala al usuario ahora): "
                    f"{password_temporal_nueva}"
                )

    filas_usuarios = conn.execute(
        """
        SELECT username, nombre_completo, dni, profesion, role, activo
        FROM usuarios
        ORDER BY username
        """
    ).fetchall()
    st.dataframe(
        [dict(fila) for fila in filas_usuarios],
        use_container_width=True,
        hide_index=True,
    )

def consultar(sql, params=()):
    """Ejecuta una consulta y devuelve sus resultados."""
    return conn.execute(sql, params).fetchall()


def ejecutar(sql, params=()):
    """Ejecuta una modificación y guarda los cambios."""
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor


def registrar_evento(evento, nhc=None, detalle="", actor="usuario"):
    """Registra una acción relevante en la auditoría."""

    ejecutar(
        """
        INSERT INTO auditoria(evento, nhc, detalle, actor, fecha)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            evento,
            nhc,
            detalle,
            actor,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def nombres_especialidades():
    filas = consultar(
        """
        SELECT nombre
        FROM especialidades
        WHERE activa = 1
        ORDER BY nombre
        """
    )
    return [fila["nombre"] for fila in filas]


def nombres_areas(especialidad):
    filas = consultar(
        """
        SELECT a.nombre
        FROM areas a
        JOIN especialidades e
            ON e.id = a.especialidad_id
        WHERE e.nombre = ?
          AND a.activa = 1
        ORDER BY a.nombre
        """,
        (especialidad,),
    )
    return [fila["nombre"] for fila in filas]


def nhc_valido(nhc):
    """Comprueba que el NHC contiene exactamente seis dígitos."""
    return nhc.isdigit() and len(nhc) == 6


def fecha_a_texto(fecha):
    return fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha)


def dias_espera(fecha_texto):
    try:
        fecha = date.fromisoformat(str(fecha_texto)[:10])
        return max((date.today() - fecha).days, 0)
    except (ValueError, TypeError):
        return 0


def regla_antiguedad(prioridad, dias):
    """Describe la regla de antigüedad que podría aplicarse."""

    if prioridad == "preferente" and dias > 60:
        return "Preferente con más de 2 meses"

    if prioridad == "ordinario" and dias > 183:
        return "Ordinario con más de 6 meses"

    if prioridad == "ordinario" and dias >= 90:
        return "Ordinario con 3 meses o más"

    return "Prioridad clínica"


def clave_prioridad(fila):
    """Ordena las solicitudes pendientes según prioridad y antigüedad."""

    dias = dias_espera(fila["fecha_solicitud"])
    prioridad = fila["prioridad"]

    if prioridad == "preferente" and dias > 60:
        grupo = 4
    elif prioridad == "ordinario" and dias > 183:
        grupo = 4
    elif prioridad == "ordinario" and dias >= 90:
        grupo = 3
    else:
        grupo = {
            "urgente": 3,
            "preferente": 2,
            "ordinario": 1,
        }.get(prioridad, 0)

    return (-grupo, -dias, fila["id"])


def registrar_solicitud(
    nhc,
    prioridad,
    especialidad,
    area,
    sesiones,
    fecha_solicitud,
    elegible,
    tipo_hueco,
    turno,
    transporte,
    hora_ambulancia,
    regla_coordinacion,
):
    """Guarda una nueva solicitud."""

    ejecutar(
        """
        INSERT INTO solicitudes (
            nhc,
            prioridad,
            especialidad,
            area,
            sesiones_previstas,
            fecha_solicitud,
            elegible,
            tipo_hueco,
            turno,
            transporte,
            hora_ambulancia,
            regla_coordinacion,
            estado,
            creado_en
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'EN_ESPERA', ?)
        """,
        (
            nhc,
            prioridad,
            especialidad,
            area,
            sesiones,
            fecha_a_texto(fecha_solicitud),
            int(elegible),
            tipo_hueco,
            turno,
            transporte,
            hora_ambulancia,
            regla_coordinacion,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    registrar_evento(
        "CREAR_SOLICITUD",
        nhc,
        f"{especialidad}; área={area or 'No aplica'}; prioridad={prioridad}",
    )


def solicitudes_pendientes():
    filas = consultar(
        """
        SELECT *
        FROM solicitudes
        WHERE estado = 'EN_ESPERA'
        """
    )
    return sorted(filas, key=clave_prioridad)


def tratamientos_activos():
    return consultar(
        """
        SELECT *
        FROM tratamientos
        WHERE estado = 'ACTIVO'
        ORDER BY id DESC
        """
    )


def sesiones_de_tratamiento(tratamiento_id):
    return consultar(
        """
        SELECT *
        FROM sesiones
        WHERE tratamiento_id = ?
        ORDER BY fecha, hora, id
        """,
        (tratamiento_id,),
    )


def porcentaje_asistencia(tratamiento_id):
    sesiones = sesiones_de_tratamiento(tratamiento_id)

    if not sesiones:
        return 100.0

    asistidas = sum(
        1
        for sesion in sesiones
        if sesion["estado"] in ("REALIZADA", "REVISION")
    )

    return round(asistidas / len(sesiones) * 100, 1)


def resumen_tratamiento(tratamiento_id):
    sesiones = sesiones_de_tratamiento(tratamiento_id)
    sesiones_eva = [
        sesion for sesion in sesiones
        if sesion["eva"] is not None
    ]

    inicial = sesiones_eva[0]["eva"] if sesiones_eva else None
    actual = sesiones_eva[-1]["eva"] if sesiones_eva else None

    if inicial is None or actual is None:
        tendencia = "Sin datos suficientes"
    elif actual < inicial:
        tendencia = "Mejoría del dolor"
    elif actual > inicial:
        tendencia = "Empeoramiento del dolor"
    else:
        tendencia = "Sin cambios en el dolor"

    return {
        "sesiones": len(sesiones),
        "asistencia": porcentaje_asistencia(tratamiento_id),
        "eva_inicial": inicial,
        "eva_actual": actual,
        "tendencia": tendencia,
        "ultima": sesiones[-1] if sesiones else None,
    }


# ============================================================
# 4. PANEL DE CONTROL
# ============================================================

def pagina_inicio():
    st.title("🏥 Gestión de Rehabilitación")
    st.caption(
        "Aplicación para gestionar solicitudes y realizar "
        "el seguimiento de pacientes en rehabilitación."
    )

    pendientes = len(solicitudes_pendientes())
    activos = len(tratamientos_activos())
    total_sesiones = consultar(
        "SELECT COUNT(*) AS n FROM sesiones"
    )[0]["n"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Solicitudes en espera", pendientes)
    col2.metric("Tratamientos activos", activos)
    col3.metric("Sesiones registradas", total_sesiones)

    st.divider()
    st.subheader("Pacientes pendientes")

    filas = solicitudes_pendientes()[:8]

    if not filas:
        st.info("No hay solicitudes pendientes.")
        return

    datos = []

    for fila in filas:
        dias = dias_espera(fila["fecha_solicitud"])

        datos.append({
            "NHC": fila["nhc"],
            "Prioridad": fila["prioridad"],
            "Especialidad": fila["especialidad"],
            "Área": fila["area"] or "—",
            "Días de espera": dias,
            "Regla orientativa": regla_antiguedad(
                fila["prioridad"], dias
            ),
        })

    st.dataframe(
        pd.DataFrame(datos),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# 5. REGISTRO DE SOLICITUDES
# ============================================================

def pagina_nueva_solicitud():
    st.header("📝 Registro de nueva solicitud de rehabilitación")

    col1, col2, col3, col4 = st.columns([1.2, 1, 1.3, 1])

    with col1:
        nhc = st.text_input(
            "NHC del paciente",
            placeholder="Ej.: 123456",
        ).strip()

    with col2:
        prioridad = st.selectbox("Prioridad", PRIORIDADES)

    with col3:
        fecha_solicitud = st.date_input(
            "Fecha de solicitud",
            value=date.today(),
        )

    with col4:
        elegible = st.checkbox("Elegible", value=True)

    especialidades = nombres_especialidades()
    seleccionadas = st.multiselect(
        "Especialidades",
        especialidades,
    )

    st.subheader("Configuración del tratamiento")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        tipo_hueco = st.selectbox("Tipo de hueco", TIPOS_HUECO)

    with col2:
        turno = st.selectbox("Turno", TURNOS)

    with col3:
        transporte = st.selectbox("Transporte", TRANSPORTES)

    with col4:
        if transporte == "AMBULANCIA":
            hora_ambulancia = st.selectbox(
                "Hora de ambulancia",
                HORAS_AMBULANCIA,
            )
        else:
            hora_ambulancia = None
            st.caption("Hora fija: no aplica")

    regla_coordinacion = "NINGUNA"

    if (
        "Fisioterapia" in seleccionadas
        and "Terapia ocupacional" in seleccionadas
    ):
        regla_coordinacion = st.selectbox(
            "Coordinación Fisioterapia + Terapia ocupacional",
            REGLAS_COORDINACION,
            index=1,
        )
        st.caption(
            "MISMO_DIA: comparten días. "
            "DIAS_ALTERNOS: no coinciden."
        )

    sesiones_por_especialidad = {}
    areas_por_especialidad = {}
    sesiones_por_area = {}

    st.subheader("Sesiones y áreas")

    for especialidad in seleccionadas:
        st.markdown(f"**{especialidad}**")

        areas = nombres_areas(especialidad)

        if areas:
            elegidas = st.multiselect(
                f"Áreas de {especialidad}",
                areas,
                key=f"areas_{especialidad}",
            )

            areas_por_especialidad[especialidad] = elegidas

            for area in elegidas:
                sesiones_por_area[(especialidad, area)] = st.number_input(
                    f"Sesiones previstas — {area}",
                    min_value=1,
                    max_value=100,
                    value=10,
                    key=f"sesiones_{especialidad}_{area}",
                )
        else:
            sesiones_por_especialidad[especialidad] = st.number_input(
                f"Sesiones previstas — {especialidad}",
                min_value=1,
                max_value=100,
                value=10,
                key=f"sesiones_{especialidad}",
            )

    st.caption(
        "Se creará una solicitud por especialidad. "
        "Si una especialidad tiene áreas configuradas, "
        "se creará una solicitud por cada área seleccionada."
    )

    if st.button(
        "Guardar solicitud",
        type="primary",
        use_container_width=True,
    ):
        errores = []

        if not nhc:
            errores.append("Debe introducir el NHC.")
        elif not nhc_valido(nhc):
            errores.append(
                "El NHC debe tener exactamente 6 números."
            )

        if not seleccionadas:
            errores.append(
                "Debe seleccionar al menos una especialidad."
            )

        if not elegible:
            errores.append(
                "La solicitud debe marcarse como elegible."
            )

        for especialidad in seleccionadas:
            if (
                nombres_areas(especialidad)
                and not areas_por_especialidad.get(especialidad)
            ):
                errores.append(
                    f"Debe seleccionar un área para {especialidad}."
                )

        if errores:
            for error in errores:
                st.error(error)
            return

        creadas = 0

        for especialidad in seleccionadas:
            areas = areas_por_especialidad.get(especialidad, [])

            if areas:
                for area in areas:
                    registrar_solicitud(
                        nhc,
                        prioridad,
                        especialidad,
                        area,
                        int(sesiones_por_area[(especialidad, area)]),
                        fecha_solicitud,
                        elegible,
                        tipo_hueco,
                        turno,
                        transporte,
                        hora_ambulancia,
                        regla_coordinacion,
                    )
                    creadas += 1
            else:
                registrar_solicitud(
                    nhc,
                    prioridad,
                    especialidad,
                    None,
                    int(sesiones_por_especialidad[especialidad]),
                    fecha_solicitud,
                    elegible,
                    tipo_hueco,
                    turno,
                    transporte,
                    hora_ambulancia,
                    regla_coordinacion,
                )
                creadas += 1

        st.success(f"Se han registrado {creadas} solicitud(es).")


# ============================================================
# 6. LISTA DE ESPERA Y ASIGNACIÓN
# ============================================================

def asignar_solicitud(solicitud_id, patron, profesional):
    solicitud = consultar(
        "SELECT * FROM solicitudes WHERE id = ?",
        (solicitud_id,),
    )

    if not solicitud:
        return False, "No se ha encontrado la solicitud."

    solicitud = solicitud[0]

    if solicitud["estado"] != "EN_ESPERA":
        return False, "La solicitud ya no está pendiente."

    if solicitud["elegible"] != 1:
        return False, "La solicitud no está marcada como elegible."

    dias = PATRONES_ASISTENCIA[patron]

    if (
        solicitud["regla_coordinacion"] == "DIAS_ALTERNOS"
        and len(dias) == 5
    ):
        return (
            False,
            "La regla DIAS_ALTERNOS no es compatible "
            "con todos los días laborables.",
        )

    ejecutar(
        """
        INSERT INTO tratamientos (
            solicitud_id,
            nhc,
            especialidad,
            area,
            prioridad,
            sesiones_previstas,
            dias_asistencia,
            fecha_inicio,
            tipo_hueco,
            turno,
            transporte,
            hora_ambulancia,
            regla_coordinacion,
            profesional,
            estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO')
        """,
        (
            solicitud["id"],
            solicitud["nhc"],
            solicitud["especialidad"],
            solicitud["area"],
            solicitud["prioridad"],
            solicitud["sesiones_previstas"],
            ",".join(dias),
            date.today().isoformat(),
            solicitud["tipo_hueco"],
            solicitud["turno"],
            solicitud["transporte"],
            solicitud["hora_ambulancia"],
            solicitud["regla_coordinacion"],
            profesional,
        ),
    )

    ejecutar(
        "UPDATE solicitudes SET estado = 'ASIGNADA' WHERE id = ?",
        (solicitud_id,),
    )

    registrar_evento(
        "ASIGNAR_TRATAMIENTO",
        solicitud["nhc"],
        f"Solicitud {solicitud_id}; profesional={profesional}; "
        f"patrón={patron}",
    )

    return True, "Tratamiento asignado correctamente."


def pagina_lista_espera():
    st.header("📋 Lista de espera")

    col1, col2, col3 = st.columns(3)

    with col1:
        filtro_prioridad = st.selectbox(
            "Prioridad",
            ["Todas"] + PRIORIDADES,
        )

    with col2:
        filtro_especialidad = st.selectbox(
            "Especialidad",
            ["Todas"] + nombres_especialidades(),
        )

    with col3:
        solo_elegibles = st.checkbox(
            "Solo elegibles",
            value=True,
        )

    filas = solicitudes_pendientes()

    if filtro_prioridad != "Todas":
        filas = [
            f for f in filas
            if f["prioridad"] == filtro_prioridad
        ]

    if filtro_especialidad != "Todas":
        filas = [
            f for f in filas
            if f["especialidad"] == filtro_especialidad
        ]

    if solo_elegibles:
        filas = [f for f in filas if f["elegible"] == 1]

    st.write(f"Solicitudes encontradas: **{len(filas)}**")

    profesional = st.text_input(
        "Profesional que realiza la asignación",
        value="",
    ).strip()

    patron = st.selectbox(
        "Frecuencia del tratamiento",
        list(PATRONES_ASISTENCIA),
        format_func=lambda x: {
            "LXV": "Lunes, miércoles y viernes",
            "MJ": "Martes y jueves",
            "LABORABLES": "Todos los días laborables",
        }[x],
    )

    if not filas:
        st.info("No hay solicitudes con los filtros seleccionados.")
        return

    for fila in filas:
        dias = dias_espera(fila["fecha_solicitud"])

        with st.container(border=True):
            st.write(
                f"**NHC {fila['nhc']}** · {fila['prioridad']} · "
                f"{fila['especialidad']} · {fila['area'] or 'Sin área'}"
            )

            st.caption(
                f"Solicitud: {fila['fecha_solicitud']} · "
                f"Espera: {dias} días · "
                f"Regla orientativa: "
                f"{regla_antiguedad(fila['prioridad'], dias)}"
            )

            if st.button(
                "Asignar tratamiento",
                key=f"asignar_{fila['id']}",
            ):
                if not profesional:
                    st.error(
                        "Indique el profesional responsable antes de asignar."
                    )
                else:
                    ok, mensaje = asignar_solicitud(
                        fila["id"],
                        patron,
                        profesional,
                    )

                    if ok:
                        st.success(mensaje)
                        st.rerun()
                    else:
                        st.error(mensaje)


# ============================================================
# 7. REGISTRO DE SESIONES
# ============================================================

def registrar_sesion(
    tratamiento,
    fecha,
    hora,
    estado,
    motivo_ausencia,
    motivo_fuera_horario,
    nota,
    eva,
    funcional,
    objetivo,
    incidencias,
):
    ejecutar(
        """
        INSERT INTO sesiones (
            tratamiento_id,
            nhc,
            especialidad,
            fecha,
            hora,
            estado,
            motivo_ausencia,
            motivo_fuera_horario,
            nota_clinica,
            eva,
            estado_funcional,
            estado_objetivo,
            incidencias,
            registrado_en
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tratamiento["id"],
            tratamiento["nhc"],
            tratamiento["especialidad"],
            fecha.isoformat(),
            hora,
            estado,
            motivo_ausencia,
            motivo_fuera_horario,
            nota,
            eva,
            funcional,
            objetivo,
            incidencias,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    registrar_evento(
        "REGISTRAR_SESION",
        tratamiento["nhc"],
        f"Tratamiento {tratamiento['id']}; "
        f"estado={estado}; EVA={eva}",
    )


def formulario_sesion(tratamiento):
    st.markdown("#### Registro de sesión")

    fecha = st.date_input(
        "Fecha de sesión",
        value=date.today(),
        key=f"fecha_sesion_{tratamiento['id']}",
    )

    hora = st.time_input(
        "Hora",
        key=f"hora_sesion_{tratamiento['id']}",
    )

    estado = st.selectbox(
        "Estado",
        ESTADOS_SESION,
        key=f"estado_sesion_{tratamiento['id']}",
    )

    eva = st.slider(
        "Dolor (EVA 0–10)",
        0,
        10,
        0,
        key=f"eva_sesion_{tratamiento['id']}",
    )

    funcional = st.selectbox(
        "Capacidad funcional",
        [
            "No registrada",
            "Limitada",
            "Sin cambios",
            "Mejorada",
        ],
        key=f"funcional_{tratamiento['id']}",
    )

    objetivo = st.selectbox(
        "Estado del objetivo",
        ["NO_INICIADO", "PARCIAL", "CUMPLIDO", "EMPEORA"],
        key=f"objetivo_{tratamiento['id']}",
    )

    motivo_ausencia = ""

    if estado in (
        "FALTA_JUSTIFICADA",
        "FALTA_NO_JUSTIFICADA",
    ):
        motivo_ausencia = st.text_input(
            "Motivo de la ausencia",
            key=f"ausencia_{tratamiento['id']}",
        )

    motivo_fuera_horario = st.text_input(
        "Motivo si la sesión se realiza fuera de los días programados",
        key=f"fuera_horario_{tratamiento['id']}",
    )

    nota = st.text_area(
        "Nota clínica",
        key=f"nota_{tratamiento['id']}",
    )

    incidencias = st.text_area(
        "Incidencias",
        key=f"incidencias_{tratamiento['id']}",
    )

    if st.button(
        "Guardar sesión",
        key=f"guardar_sesion_{tratamiento['id']}",
        type="primary",
    ):
        if (
            estado in ("FALTA_JUSTIFICADA", "FALTA_NO_JUSTIFICADA")
            and not motivo_ausencia.strip()
        ):
            st.error("Debe indicar el motivo de la ausencia.")
            return

        dias_programados = [
            d.strip()
            for d in tratamiento["dias_asistencia"].split(",")
            if d.strip()
        ]

        nombres_dias = [
            "Lunes",
            "Martes",
            "Miércoles",
            "Jueves",
            "Viernes",
            "Sábado",
            "Domingo",
        ]

        nombre_dia = nombres_dias[fecha.weekday()]

        if (
            dias_programados
            and nombre_dia not in dias_programados
            and not motivo_fuera_horario.strip()
        ):
            st.error(
                "La fecha está fuera de los días programados. "
                "Indique el motivo."
            )
            return

        registrar_sesion(
            tratamiento,
            fecha,
            hora.strftime("%H:%M"),
            estado,
            motivo_ausencia,
            motivo_fuera_horario,
            nota,
            int(eva),
            funcional,
            objetivo,
            incidencias,
        )

        st.success("Sesión registrada.")
        st.rerun()


# ============================================================
# 8. ALTAS Y TRATAMIENTOS ACTIVOS
# ============================================================

def finalizar_tratamiento(tratamiento, motivo, comentario):
    estado_final = (
        "FINALIZADO"
        if motivo == "FIN_TRATAMIENTO"
        else motivo
    )

    ejecutar(
        """
        UPDATE tratamientos
        SET estado = ?,
            motivo_alta = ?,
            comentario_alta = ?,
            fecha_alta = ?
        WHERE id = ?
        """,
        (
            estado_final,
            motivo,
            comentario,
            date.today().isoformat(),
            tratamiento["id"],
        ),
    )

    registrar_evento(
        "FINALIZAR_TRATAMIENTO",
        tratamiento["nhc"],
        f"Motivo={motivo}; comentario={comentario}",
    )


def pagina_tratamientos():
    st.header("⚕️ Tratamientos activos")

    filas = tratamientos_activos()

    if not filas:
        st.info("No hay tratamientos activos.")
        return

    filtro = st.selectbox(
        "Filtrar especialidad",
        ["Todas"] + nombres_especialidades(),
    )

    if filtro != "Todas":
        filas = [
            f for f in filas
            if f["especialidad"] == filtro
        ]

    for tratamiento in filas:
        sesiones = sesiones_de_tratamiento(tratamiento["id"])

        with st.container(border=True):
            st.write(
                f"**NHC {tratamiento['nhc']}** · "
                f"{tratamiento['especialidad']} · "
                f"{tratamiento['area'] or 'Sin área'}"
            )

            st.caption(
                f"Inicio: {tratamiento['fecha_inicio']} · "
                f"Turno: {tratamiento['turno']} · "
                f"Transporte: {tratamiento['transporte']} · "
                f"Profesional: {tratamiento['profesional']}"
            )

            st.write(
                f"Sesiones registradas: {len(sesiones)} / "
                f"{tratamiento['sesiones_previstas'] or 'Sin objetivo definido'}"
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button(
                    "Registrar sesión",
                    key=f"abrir_sesion_{tratamiento['id']}",
                ):
                    st.session_state[
                        f"form_sesion_{tratamiento['id']}"
                    ] = True

            with col2:
                if st.button(
                    "Dar de alta",
                    key=f"abrir_alta_{tratamiento['id']}",
                ):
                    st.session_state[
                        f"form_alta_{tratamiento['id']}"
                    ] = True

            if st.session_state.get(
                f"form_sesion_{tratamiento['id']}", False
            ):
                formulario_sesion(tratamiento)

            if st.session_state.get(
                f"form_alta_{tratamiento['id']}", False
            ):
                motivo = st.selectbox(
                    "Motivo del alta",
                    MOTIVOS_ALTA,
                    key=f"motivo_alta_{tratamiento['id']}",
                )

                comentario = st.text_area(
                    "Comentario clínico",
                    key=f"comentario_alta_{tratamiento['id']}",
                )

                if st.button(
                    "Confirmar alta",
                    key=f"confirmar_alta_{tratamiento['id']}",
                ):
                    if motivo == "OTRO" and not comentario.strip():
                        st.error(
                            "Debe añadir un comentario cuando "
                            "el motivo sea OTRO."
                        )
                    else:
                        finalizar_tratamiento(
                            tratamiento,
                            motivo,
                            comentario.strip(),
                        )
                        st.success("Alta registrada.")
                        st.rerun()


# ============================================================
# 9. SEGUIMIENTO CLÍNICO
# ============================================================

def pagina_seguimiento():
    st.header("📈 Seguimiento clínico")

    filas = consultar(
        "SELECT * FROM tratamientos ORDER BY id DESC"
    )

    if not filas:
        st.info("No hay tratamientos para consultar.")
        return

    opciones = {
        f"NHC {f['nhc']} · {f['especialidad']} · "
        f"tratamiento {f['id']}": f["id"]
        for f in filas
    }

    seleccion = st.selectbox(
        "Seleccione tratamiento",
        list(opciones),
    )

    tratamiento_id = opciones[seleccion]

    tratamiento = consultar(
        "SELECT * FROM tratamientos WHERE id = ?",
        (tratamiento_id,),
    )[0]

    resumen = resumen_tratamiento(tratamiento_id)

    col1, col2, col3 = st.columns(3)

    col1.metric("Sesiones", resumen["sesiones"])
    col2.metric("Asistencia", f"{resumen['asistencia']}%")
    col3.metric("Evolución del dolor", resumen["tendencia"])

    col1, col2 = st.columns(2)

    with col1:
        valor = resumen["eva_inicial"]
        st.write(
            f"EVA inicial: **{valor if valor is not None else 'Sin datos'}**"
        )

    with col2:
        valor = resumen["eva_actual"]
        st.write(
            f"EVA actual: **{valor if valor is not None else 'Sin datos'}**"
        )

    sesiones = sesiones_de_tratamiento(tratamiento_id)

    if sesiones:
        datos = [
            {
                "Fecha": s["fecha"],
                "Hora": s["hora"],
                "Estado": s["estado"],
                "EVA": s["eva"],
                "Funcional": s["estado_funcional"],
                "Objetivo": s["estado_objetivo"],
                "Nota clínica": s["nota_clinica"],
                "Incidencias": s["incidencias"],
            }
            for s in sesiones
        ]

        st.dataframe(
            pd.DataFrame(datos),
            use_container_width=True,
            hide_index=True,
        )

        valores_eva = [
            (s["fecha"], s["eva"])
            for s in sesiones
            if s["eva"] is not None
        ]

        if valores_eva:
            grafica = pd.DataFrame(
                valores_eva,
                columns=["Fecha", "EVA"],
            ).set_index("Fecha")

            st.line_chart(grafica)
    else:
        st.info(
            "No hay sesiones registradas para este tratamiento."
        )

    st.subheader("Resumen estructurado")

    st.write(f"- NHC: {tratamiento['nhc']}")
    st.write(f"- Especialidad: {tratamiento['especialidad']}")
    st.write(f"- Estado del tratamiento: {tratamiento['estado']}")
    st.write(f"- Asistencia registrada: {resumen['asistencia']}%")
    st.write(f"- Evolución del dolor: {resumen['tendencia']}")

    st.caption(
        "Este resumen es descriptivo y no sustituye "
        "la valoración del profesional sanitario."
    )


# ============================================================
# 10. DASHBOARD CLÍNICO
# ============================================================

def pagina_dashboard():
    st.header("📊 Dashboard clínico")

    total_solicitudes = consultar(
        "SELECT COUNT(*) AS n FROM solicitudes"
    )[0]["n"]

    pendientes = consultar(
        """
        SELECT COUNT(*) AS n
        FROM solicitudes
        WHERE estado = 'EN_ESPERA'
        """
    )[0]["n"]

    activos = consultar(
        """
        SELECT COUNT(*) AS n
        FROM tratamientos
        WHERE estado = 'ACTIVO'
        """
    )[0]["n"]

    sesiones = consultar(
        "SELECT COUNT(*) AS n FROM sesiones"
    )[0]["n"]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Solicitudes totales", total_solicitudes)
    col2.metric("En espera", pendientes)
    col3.metric("Tratamientos activos", activos)
    col4.metric("Sesiones registradas", sesiones)

    filas = consultar(
        """
        SELECT prioridad, COUNT(*) AS total
        FROM solicitudes
        GROUP BY prioridad
        """
    )

    if filas:
        st.subheader("Solicitudes por prioridad")

        df = pd.DataFrame([
            {
                "Prioridad": fila["prioridad"],
                "Total": fila["total"],
            }
            for fila in filas
        ]).set_index("Prioridad")

        st.bar_chart(df)

    filas = consultar(
        """
        SELECT especialidad, COUNT(*) AS total
        FROM tratamientos
        GROUP BY especialidad
        """
    )

    if filas:
        st.subheader("Tratamientos por especialidad")

        df = pd.DataFrame([
            {
                "Especialidad": fila["especialidad"],
                "Total": fila["total"],
            }
            for fila in filas
        ]).set_index("Especialidad")

        st.bar_chart(df)


# ============================================================
# 11. AUDITORÍA
# ============================================================

def pagina_auditoria():
    st.header("🧾 Registro de actividad")

    st.caption(
        "Registro inicial de acciones relevantes "
        "realizadas desde el prototipo."
    )

    filas = consultar(
        """
        SELECT *
        FROM auditoria
        ORDER BY id DESC
        LIMIT 300
        """
    )

    if not filas:
        st.info("Todavía no hay eventos registrados.")
        return

    datos = [
        {
            "Fecha": fila["fecha"],
            "Evento": fila["evento"],
            "NHC": fila["nhc"],
            "Detalle": fila["detalle"],
            "Actor": fila["actor"],
        }
        for fila in filas
    ]

    st.dataframe(
        pd.DataFrame(datos),
        use_container_width=True,
        hide_index=True,
    )

    try:
        asegurar_admin_host()
    except RuntimeError as error:
        st.error(str(error))
        st.stop()

    if "usuario_actual" not in st.session_state:
        st.session_state["usuario_actual"] = None

    if st.session_state["usuario_actual"] is None:
        st.title("Acceso al sistema")
        username = st.text_input("Usuario")
        password = st.text_input("Contrasena", type="password")

        if st.button("Iniciar sesi?n"):
            usuario = autenticar_usuario(username, password)
            if usuario:
                st.session_state["usuario_actual"] = usuario
                st.rerun()
            else:
                st.error("Usuario o contrasena incorrectos.")

        st.stop()

    usuario_actual = st.session_state["usuario_actual"]
    if usuario_actual["debe_cambiar_password"]:
        st.title("Cambia tu contrasena")
        nueva_password = st.text_input(
            "Nueva contrasena", type="password", key="nueva_password"
        )
        repetir_password = st.text_input(
            "Repite la nueva contrasena", type="password", key="repetir_password"
        )

        if st.button("Guardar nueva contrasena"):
            if len(nueva_password) < 12:
                st.error("La contrasena debe tener al menos 12 caracteres.")
            elif nueva_password != repetir_password:
                st.error("Las contrasenas no coinciden.")
            else:
                conn.execute(
                    """
                    UPDATE usuarios
                    SET password_hash = ?, debe_cambiar_password = 0
                    WHERE id = ?
                    """,
                    (hash_password(nueva_password), usuario_actual["id"]),
                )
                conn.commit()
                st.session_state["usuario_actual"]["debe_cambiar_password"] = False
                st.success("Contrasena actualizada.")
                st.rerun()

        st.stop()

    # 12. MENÚ Y NAVEGACIÓN
    # ============================================================

    st.sidebar.title("🏥 Rehabilitación")

    opciones_paginas = [
        "📊 Panel de control",
        "📝 Nueva solicitud",
        "📋 Lista de espera",
        "⚕️ Tratamientos activos",
        "📈 Seguimiento clínico",
        "📉 Dashboard clínico",
        "🧾 Auditoría clínica",
    ]
    if st.session_state["usuario_actual"].get("role") == "ADMIN":
        opciones_paginas.append("Administracion")


    if "usuario_actual" not in st.session_state:
        st.session_state["usuario_actual"] = None

    total_usuarios = conn.execute(
        "SELECT COUNT(*) AS total FROM usuarios"
    ).fetchone()["total"]

    # Si todavía no hay usuarios, permite crear el primer administrador.
    if total_usuarios == 0:
        st.title("Configuración inicial")

        st.info(
            f"El primer administrador elegirá su nombre de usuario. "
            f"La contraseña temporal será: {PASSWORD_TEMPORAL}"
        )

        with st.form("formulario_primer_admin"):
            username_admin = st.text_input("Nombre de usuario")
            nombre_admin = st.text_input("Nombre completo")
            dni_admin = st.text_input("DNI")
            profesion_admin = st.text_input(
                "Profesión",
                value="Administrador",
            )

            crear_admin = st.form_submit_button(
                "Crear administrador"
            )

        if crear_admin:
            if not username_admin.strip():
                st.error("Escribe un nombre de usuario.")
            elif not nombre_admin.strip():
                st.error("Escribe el nombre completo.")
            elif not dni_admin.strip():
                st.error("Escribe el DNI.")
            elif not profesion_admin.strip():
                st.error("Escribe la profesión.")
            else:
                try:
                    crear_usuario(
                        username=username_admin,
                        nombre_completo=nombre_admin,
                        dni=dni_admin,
                        profesion=profesion_admin,
                        password=PASSWORD_TEMPORAL,
                        role="ADMIN",
                    )
                    st.success(
                        "Administrador creado. Inicia sesión con el nombre "
                        "que has elegido y la contraseña temporal."
                    )
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ese nombre de usuario o DNI ya está registrado.")

        st.stop()

    # Formulario de acceso para los usuarios existentes.
    if st.session_state["usuario_actual"] is None:
        st.title("Acceso al sistema")

        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Iniciar sesión"):
            usuario = autenticar_usuario(username, password)

            if usuario:
                st.session_state["usuario_actual"] = usuario
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")

        st.stop()

    # Obliga al usuario a cambiar la contraseña temporal.
    usuario_actual = st.session_state["usuario_actual"]

    if usuario_actual["debe_cambiar_password"]:
        st.title("Cambia tu contraseña")

        nueva_password = st.text_input(
            "Nueva contraseña",
            type="password",
            key="nueva_password",
        )
        repetir_password = st.text_input(
            "Repite la nueva contraseña",
            type="password",
            key="repetir_password",
        )

        if st.button("Guardar nueva contraseña"):
            if len(nueva_password) < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
            elif nueva_password == PASSWORD_TEMPORAL:
                st.error("Elige una contraseña distinta de la temporal.")
            elif nueva_password != repetir_password:
                st.error("Las contraseñas no coinciden.")
            else:
                conn.execute(
                    """
                    UPDATE usuarios
                    SET password_hash = ?,
                        debe_cambiar_password = 0
                    WHERE id = ?
                    """,
                    (
                        hash_password(nueva_password),
                        usuario_actual["id"],
                    ),
                )
                conn.commit()

                st.session_state["usuario_actual"][
                    "debe_cambiar_password"
                ] = False

                st.success("Contraseña actualizada.")
                st.rerun()

        st.stop()

try:
    asegurar_admin_host()
except RuntimeError as error:
    st.error(str(error))
    st.stop()

# ============================================================
# 12. MENÚ Y NAVEGACIÓN
# ============================================================

st.sidebar.title("🏥 Rehabilitación")

pagina = st.sidebar.radio(
    "Menú",
    [
        "📊 Panel de control",
        "📝 Nueva solicitud",
        "📋 Lista de espera",
        "⚕️ Tratamientos activos",
        "📈 Seguimiento clínico",
        "📉 Dashboard clínico",
        "🧾 Auditoría clínica",
    ],
)
if st.session_state["usuario_actual"].get("role") == "ADMIN":
    pagina.append("Administracion")

usuario_actual = st.session_state["usuario_actual"]

st.sidebar.markdown(
    f"**Usuario:** {usuario_actual['nombre_completo']}"
)
st.sidebar.markdown(f"**Rol:** {usuario_actual['role']}")

if st.sidebar.button("Cerrar sesión"):
    st.session_state["usuario_actual"] = None
    st.rerun()

st.sidebar.divider()

st.sidebar.caption(
    "Versión de desarrollo: estructura monolítica inicial."
)

if pagina == "📊 Panel de control":
    pagina_inicio()

elif pagina == "📝 Nueva solicitud":
    pagina_nueva_solicitud()

elif pagina == "📋 Lista de espera":
    pagina_lista_espera()

elif pagina == "⚕️ Tratamientos activos":
    pagina_tratamientos()

elif pagina == "📈 Seguimiento clínico":
    pagina_seguimiento()

elif pagina == "📉 Dashboard clínico":
    pagina_dashboard()

elif pagina == "🧾 Auditoría clínica":
    pagina_auditoria()