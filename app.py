import streamlit as st
from datetime import date, datetime


# ============================================================
# CONFIGURACIÓN
# ============================================================

st.set_page_config(
    page_title="Gestión de Rehabilitación",
    page_icon="🏥",
    layout="wide"
)


# ============================================================
# OPCIONES DEL SISTEMA
# ============================================================

PRIORIDADES = [
    "GRAVE",
    "PRIORITARIO",
    "NORMAL"
]

ESPECIALIDADES = [
    "Fisioterapia",
    "Terapia ocupacional",
    "Logopedia",
    "Rehabilitación neurológica"
]

TIPOS_HUECO = [
    "INDISTINTO",
    "MAÑANA",
    "TARDE"
]

TURNOS = [
    "MAÑANA",
    "TARDE",
    "INDIFERENTE"
]

TRANSPORTES = [
    "NINGUNO",
    "AMBULANCIA",
    "TRANSPORTE PROPIO"
]

HORAS_AMBULANCIA = [
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "16:00",
    "17:00"
]

REGLAS_COORDINACION = [
    "NINGUNA",
    "MISMO_DIA",
    "DIAS_ALTERNOS"
]

AREAS = {
    "Rehabilitación neurológica": [
        "Neurología",
        "Daño cerebral",
        "Lesión medular"
    ]
}


# ============================================================
# INICIALIZACIÓN DE DATOS
# ============================================================

def inicializar_datos():

    if "solicitudes" not in st.session_state:
        st.session_state.solicitudes = []

    if "tratamientos" not in st.session_state:
        st.session_state.tratamientos = []

    if "seguimientos" not in st.session_state:
        st.session_state.seguimientos = []

    if "contador_solicitud" not in st.session_state:
        st.session_state.contador_solicitud = 1


inicializar_datos()


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def validar_nhc(nhc):

    return nhc.isdigit() and len(nhc) == 6


def calcular_dias_espera(fecha):

    if isinstance(fecha, str):
        fecha = datetime.strptime(
            fecha,
            "%Y-%m-%d"
        ).date()

    return (date.today() - fecha).days


def valor_prioridad(prioridad):

    valores = {
        "GRAVE": 3,
        "PRIORITARIO": 2,
        "NORMAL": 1
    }

    return valores.get(
        prioridad,
        0
    )


def hay_fisio_y_terapia(especialidades):

    return (
        "Fisioterapia" in especialidades
        and
        "Terapia ocupacional" in especialidades
    )


def obtener_area_especialidad(especialidad):

    return AREAS.get(
        especialidad,
        []
    )


def obtener_solicitudes_activas():

    return [
        solicitud
        for solicitud in st.session_state.solicitudes
        if solicitud["estado"] == "EN_ESPERA"
    ]


def ordenar_lista_espera(solicitudes):

    return sorted(
        solicitudes,
        key=lambda solicitud: (
            valor_prioridad(
                solicitud["prioridad"]
            ),
            solicitud["dias_espera"]
        ),
        reverse=True
    )


def buscar_solicitud_por_nhc(nhc):

    for solicitud in st.session_state.solicitudes:

        if solicitud["nhc"] == nhc:
            return solicitud

    return None


# ============================================================
# CABECERA
# ============================================================

st.title("🏥 Gestión de Rehabilitación")

st.write(
    "Aplicación para la gestión y seguimiento "
    "de pacientes del servicio de rehabilitación."
)


# ============================================================
# MENÚ
# ============================================================

st.sidebar.title("Menú")

pagina = st.sidebar.radio(
    "Selecciona una opción",
    [
        "Inicio",
        "📝 Nueva solicitud",
        "📋 Lista de espera",
        "⚕️ Tratamientos",
        "📈 Seguimiento"
    ]
)


# ============================================================
# INICIO
# ============================================================

if pagina == "Inicio":

    st.header("Panel principal")

    solicitudes = st.session_state.solicitudes
    tratamientos = st.session_state.tratamientos
    seguimientos = st.session_state.seguimientos

    solicitudes_activas = [
        solicitud
        for solicitud in solicitudes
        if solicitud["estado"] == "EN_ESPERA"
    ]

    tratamientos_activos = [
        tratamiento
        for tratamiento in tratamientos
        if tratamiento["estado"] == "ACTIVO"
    ]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Solicitudes",
            len(solicitudes)
        )

    with col2:
        st.metric(
            "Lista de espera",
            len(solicitudes_activas)
        )

    with col3:
        st.metric(
            "Tratamientos activos",
            len(tratamientos_activos)
        )

    with col4:
        st.metric(
            "Seguimientos",
            len(seguimientos)
        )

    st.divider()

    st.subheader("Situación de la lista de espera")

    if solicitudes_activas:

        graves = len([
            solicitud
            for solicitud in solicitudes_activas
            if solicitud["prioridad"] == "GRAVE"
        ])

        prioritarios = len([
            solicitud
            for solicitud in solicitudes_activas
            if solicitud["prioridad"] == "PRIORITARIO"
        ])

        normales = len([
            solicitud
            for solicitud in solicitudes_activas
            if solicitud["prioridad"] == "NORMAL"
        ])

        col1, col2, col3 = st.columns(3)

        with col1:
            st.error(
                f"🔴 Graves: {graves}"
            )

        with col2:
            st.warning(
                f"🟠 Prioritarios: {prioritarios}"
            )

        with col3:
            st.success(
                f"🟢 Normales: {normales}"
            )

    else:

        st.info(
            "No hay solicitudes actualmente "
            "en lista de espera."
        )


# ============================================================
# NUEVA SOLICITUD
# ============================================================

elif pagina == "📝 Nueva solicitud":

    st.subheader(
        "Registro de nueva solicitud de rehabilitación"
    )

    # --------------------------------------------------------
    # DATOS BÁSICOS DE LA SOLICITUD
    # --------------------------------------------------------

    c1, c2, c3, c4 = st.columns(
        [1.2, 1, 1.3, 1.1]
    )

    with c1:

        nhc = st.text_input(
            "NHC del paciente",
            placeholder="Ej: 123456",
            key="req_nhc"
        ).strip()

    with c2:

        prioridad = st.selectbox(
            "Prioridad",
            PRIORIDADES,
            key="req_prioridad"
        )

    with c3:

        fecha_solicitud = st.date_input(
            "Fecha de solicitud",
            value=date.today(),
            key="req_fecha"
        )

    with c4:

        elegible = st.checkbox(
            "Elegible",
            value=True,
            key="req_elegible"
        )

    # --------------------------------------------------------
    # ESPECIALIDADES
    # --------------------------------------------------------

    especialidades = st.multiselect(
        "Especialidades",
        ESPECIALIDADES,
        key="req_especialidades"
    )

    # --------------------------------------------------------
    # CONFIGURACIÓN DEL TRATAMIENTO
    # --------------------------------------------------------

    st.markdown(
        "### Configuración del tratamiento"
    )

    cfg1, cfg2, cfg3, cfg4 = st.columns(4)

    with cfg1:

        tipo_hueco = st.selectbox(
            "Tipo de hueco",
            TIPOS_HUECO,
            key="req_tipo_hueco"
        )

    with cfg2:

        turno = st.selectbox(
            "Turno",
            TURNOS,
            key="req_turno"
        )

    with cfg3:

        transporte = st.selectbox(
            "Transporte",
            TRANSPORTES,
            key="req_transporte"
        )

    with cfg4:

        hora_ambulancia = None

        if transporte == "AMBULANCIA":

            hora_ambulancia = st.selectbox(
                "Hora ambulancia",
                HORAS_AMBULANCIA,
                key="req_hora_ambulancia"
            )

        else:

            st.caption(
                "Hora fija: no aplica"
            )

    # --------------------------------------------------------
    # COORDINACIÓN
    # --------------------------------------------------------

    regla_coordinacion = "NINGUNA"

    if hay_fisio_y_terapia(
        especialidades
    ):

        regla_coordinacion = st.selectbox(
            "Coordinación Fisio + Terapia ocupacional",
            REGLAS_COORDINACION,
            index=1,
            key="req_coordinacion"
        )

        st.caption(
            "MISMO_DIA: ambos tratamientos "
            "comparten días. "
            "DIAS_ALTERNOS: no pueden coincidir."
        )

    # --------------------------------------------------------
    # SESIONES POR ESPECIALIDAD
    # --------------------------------------------------------

    sesiones_especialidad = {}

    if especialidades:

        st.markdown(
            "### Número de sesiones orientativas "
            "por especialidad"
        )

        for especialidad in especialidades:

            if especialidad not in AREAS:

                sesiones = st.text_input(
                    f"Sesiones orientativas para "
                    f"{especialidad}",
                    placeholder="Ej: 10",
                    key=f"sesiones_{especialidad}"
                )

                sesiones_especialidad[
                    especialidad
                ] = sesiones.strip()

    # --------------------------------------------------------
    # ÁREAS / SUBESPECIALIDADES
    # --------------------------------------------------------

    areas_especialidad = {}
    sesiones_area = {}

    for especialidad in especialidades:

        areas_disponibles = (
            obtener_area_especialidad(
                especialidad
            )
        )

        if areas_disponibles:

            st.markdown(
                f"### Áreas de {especialidad}"
            )

            areas_seleccionadas = st.multiselect(
                f"Áreas de {especialidad}",
                areas_disponibles,
                key=f"areas_{especialidad}"
            )

            areas_especialidad[
                especialidad
            ] = areas_seleccionadas

            if areas_seleccionadas:

                st.markdown(
                    "Número de sesiones orientativas "
                    "por área"
                )

                for area in areas_seleccionadas:

                    sesiones = st.text_input(
                        f"Sesiones para "
                        f"{especialidad} · {area}",
                        placeholder="Ej: 10",
                        key=f"sesiones_{especialidad}_{area}"
                    )

                    sesiones_area[
                        (especialidad, area)
                    ] = sesiones.strip()

    st.caption(
        "Se creará una solicitud independiente "
        "por cada especialidad seleccionada. "
        "Si una especialidad requiere área, "
        "se utilizará el área seleccionada."
    )

    # --------------------------------------------------------
    # GUARDAR SOLICITUD
    # --------------------------------------------------------

    if st.button(
        "Guardar solicitud",
        type="primary"
    ):

        if not nhc:

            st.error(
                "Introduce el NHC del paciente."
            )

        elif not validar_nhc(nhc):

            st.error(
                "El NHC debe tener exactamente "
                "6 números."
            )

        elif not especialidades:

            st.error(
                "Selecciona al menos una especialidad."
            )

        elif not elegible:

            st.error(
                "El paciente debe ser elegible "
                "para registrar la solicitud."
            )

        else:

            solicitud_existente = (
                buscar_solicitud_por_nhc(nhc)
            )

            if solicitud_existente:

                st.warning(
                    "Ya existe una solicitud activa "
                    "para este NHC."
                )

            else:

                dias_espera = calcular_dias_espera(
                    fecha_solicitud
                )

                nueva_solicitud = {
                    "id": st.session_state.contador_solicitud,
                    "nhc": nhc,
                    "prioridad": prioridad,
                    "fecha_solicitud":
                        fecha_solicitud,
                    "elegible": elegible,
                    "especialidades":
                        especialidades,
                    "tipo_hueco":
                        tipo_hueco,
                    "turno":
                        turno,
                    "transporte":
                        transporte,
                    "hora_ambulancia":
                        hora_ambulancia,
                    "regla_coordinacion":
                        regla_coordinacion,
                    "sesiones_especialidad":
                        sesiones_especialidad,
                    "areas_especialidad":
                        areas_especialidad,
                    "sesiones_area":
                        sesiones_area,
                    "dias_espera":
                        dias_espera,
                    "estado":
                        "EN_ESPERA"
                }

                st.session_state.solicitudes.append(
                    nueva_solicitud
                )

                st.session_state.contador_solicitud += 1

                st.success(
                    f"Solicitud registrada para "
                    f"el NHC {nhc}."
                )


# ============================================================
# LISTA DE ESPERA
# ============================================================

elif pagina == "📋 Lista de espera":

    st.subheader(
        "Lista de espera de rehabilitación"
    )

    solicitudes = (
        obtener_solicitudes_activas()
    )

    if not solicitudes:

        st.info(
            "No hay pacientes en lista de espera."
        )

    else:

        solicitudes = ordenar_lista_espera(
            solicitudes
        )

        st.write(
            "Solicitudes ordenadas según "
            "prioridad y tiempo de espera."
        )

        for posicion, solicitud in enumerate(
            solicitudes,
            start=1
        ):

            col1, col2, col3, col4 = st.columns(
                [0.5, 2, 2, 2]
            )

            with col1:

                st.write(
                    f"**{posicion}**"
                )

            with col2:

                st.write(
                    f'**NHC:** '
                    f'{solicitud["nhc"]}'
                )

            with col3:

                st.write(
                    f'**Prioridad:** '
                    f'{solicitud["prioridad"]}'
                )

            with col4:

                st.write(
                    f'**Espera:** '
                    f'{solicitud["dias_espera"]} días'
                )

            st.caption(
                "Especialidades: "
                + ", ".join(
                    solicitud["especialidades"]
                )
            )

            st.divider()

        # ----------------------------------------------------
        # ASIGNACIÓN BÁSICA
        # ----------------------------------------------------

        st.subheader(
            "Asignación"
        )

        if st.button(
            "Asignar siguiente",
            type="primary"
        ):

            siguiente = solicitudes[0]

            st.success(
                f'Asignado NHC: '
                f'{siguiente["nhc"]} '
                f'({siguiente["prioridad"]})'
            )

            st.info(
                f'Especialidades: '
                f'{", ".join(siguiente["especialidades"])}'
                f'\n\n'
                f'Espera: '
                f'{siguiente["dias_espera"]} días'
            )


# ============================================================
# TRATAMIENTOS
# ============================================================

elif pagina == "⚕️ Tratamientos":

    st.subheader(
        "Gestión de tratamientos"
    )

    solicitudes = st.session_state.solicitudes

    if not solicitudes:

        st.info(
            "No hay pacientes registrados."
        )

    else:

        opciones = {
            f'{s["nhc"]} · '
            f'{", ".join(s["especialidades"])}':
            s["nhc"]
            for s in solicitudes
        }

        seleccion = st.selectbox(
            "NHC del paciente",
            list(opciones.keys())
        )

        nhc_seleccionado = opciones[
            seleccion
        ]

        solicitud = buscar_solicitud_por_nhc(
            nhc_seleccionado
        )

        if solicitud:

            st.write(
                f'**NHC:** {solicitud["nhc"]}'
            )

            st.write(
                f'**Prioridad:** '
                f'{solicitud["prioridad"]}'
            )

            st.write(
                f'**Especialidades:** '
                f'{", ".join(solicitud["especialidades"])}'
            )

            st.divider()

            st.subheader(
                "Información del tratamiento"
            )

            fecha_inicio = st.date_input(
                "Fecha de inicio",
                value=date.today()
            )

            profesional = st.text_input(
                "Profesional responsable"
            )

            observaciones = st.text_area(
                "Observaciones"
            )

            if st.button(
                "Iniciar tratamiento",
                type="primary"
            ):

                tratamiento = {
                    "id": len(
                        st.session_state.tratamientos
                    ) + 1,
                    "nhc":
                        nhc_seleccionado,
                    "especialidades":
                        solicitud["especialidades"],
                    "fecha_inicio":
                        fecha_inicio,
                    "profesional":
                        profesional,
                    "observaciones":
                        observaciones,
                    "estado":
                        "ACTIVO"
                }

                st.session_state.tratamientos.append(
                    tratamiento
                )

                solicitud["estado"] = "ACTIVO"

                st.success(
                    "Tratamiento iniciado correctamente."
                )

    st.divider()

    st.subheader(
        "Tratamientos activos"
    )

    tratamientos_activos = [
        tratamiento
        for tratamiento
        in st.session_state.tratamientos
        if tratamiento["estado"] == "ACTIVO"
    ]

    if not tratamientos_activos:

        st.info(
            "No hay tratamientos activos."
        )

    else:

        for tratamiento in tratamientos_activos:

            with st.expander(
                f'NHC {tratamiento["nhc"]} · '
                f'{", ".join(tratamiento["especialidades"])}'
            ):

                st.write(
                    f'**Inicio:** '
                    f'{tratamiento["fecha_inicio"]}'
                )

                st.write(
                    f'**Profesional:** '
                    f'{tratamiento["profesional"]}'
                )

                st.write(
                    f'**Estado:** '
                    f'{tratamiento["estado"]}'
                )

                if tratamiento["observaciones"]:

                    st.write(
                        f'**Observaciones:** '
                        f'{tratamiento["observaciones"]}'
                    )


# ============================================================
# SEGUIMIENTO
# ============================================================

elif pagina == "📈 Seguimiento":

    st.subheader(
        "Seguimiento clínico del paciente"
    )

    tratamientos_activos = [
        tratamiento
        for tratamiento
        in st.session_state.tratamientos
        if tratamiento["estado"] == "ACTIVO"
    ]

    if not tratamientos_activos:

        st.info(
            "No hay tratamientos activos "
            "para seguimiento."
        )

    else:

        opciones = {
            f'{tratamiento["nhc"]} · '
            f'{", ".join(tratamiento["especialidades"])}':
            tratamiento["nhc"]
            for tratamiento
            in tratamientos_activos
        }

        seleccion = st.selectbox(
            "Selecciona paciente",
            list(opciones.keys())
        )

        nhc = opciones[seleccion]

        st.markdown(
            "### Nueva valoración"
        )

        col1, col2 = st.columns(2)

        with col1:

            dolor = st.slider(
                "Dolor (EVA)",
                min_value=0,
                max_value=10,
                value=5
            )

        with col2:

            estado_funcional = st.selectbox(
                "Estado funcional",
                [
                    "Mejorado",
                    "Estable",
                    "Limitado",
                    "Empeorado"
                ]
            )

        movilidad = st.selectbox(
            "Movilidad",
            [
                "Normal",
                "Levemente limitada",
                "Limitada",
                "Muy limitada"
            ]
        )

        observaciones = st.text_area(
            "Observaciones clínicas"
        )

        if st.button(
            "Guardar seguimiento",
            type="primary"
        ):

            seguimiento = {
                "id": len(
                    st.session_state.seguimientos
                ) + 1,
                "nhc": nhc,
                "fecha": date.today(),
                "dolor": dolor,
                "estado_funcional":
                    estado_funcional,
                "movilidad":
                    movilidad,
                "observaciones":
                    observaciones
            }

            st.session_state.seguimientos.append(
                seguimiento
            )

            st.success(
                "Seguimiento registrado correctamente."
            )

        st.divider()

        st.markdown(
            "### Historial del paciente"
        )

        historial = [
            seguimiento
            for seguimiento
            in st.session_state.seguimientos
            if seguimiento["nhc"] == nhc
        ]

        if not historial:

            st.info(
                "Todavía no hay registros "
                "de seguimiento."
            )

        else:

            for seguimiento in reversed(
                historial
            ):

                with st.expander(
                    str(seguimiento["fecha"])
                ):

                    col1, col2, col3 = st.columns(3)

                    with col1:

                        st.metric(
                            "Dolor",
                            f'{seguimiento["dolor"]}/10'
                        )

                    with col2:

                        st.write(
                            "**Movilidad**"
                        )

                        st.write(
                            seguimiento["movilidad"]
                        )

                    with col3:

                        st.write(
                            "**Estado funcional**"
                        )

                        st.write(
                            seguimiento[
                                "estado_funcional"
                            ]
                        )

                    if seguimiento[
                        "observaciones"
                    ]:

                        st.write(
                            f'**Observaciones:** '
                            f'{seguimiento["observaciones"]}'
                        )