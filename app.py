# app.py
# Prototipo de gestión de pacientes en rehabilitación.
# Versión inicial con la lógica dentro de un único archivo.

import sqlite3
from datetime import date, datetime
from pathlib import Path

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
        """
    )

    for especialidad, areas in ESPECIALIDADES_INICIALES.items():
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


# ============================================================
# 3. FUNCIONES COMUNES
# ============================================================

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