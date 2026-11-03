"""Pantallas de acceso, solicitudes, tratamientos, seguimiento y administración."""
# app.py

from datetime import date, time


import streamlit as st
import json

from comun.config import (
    PRIORIDADES,
    MESES_ES,
    OPCIONES_ASISTENCIA,
    TIPOS_HUECO,
    TURNOS,
    TRANSPORTES,
    HORAS_AMBULANCIA,
    REGLAS_COORDINACION,
)
from cliente.api_client import (
    get_table,
    get_clinical_visits,
    begin_api_run,
    iso_utc_from_date,
    get_current_session_user,
    cerrar_sesion,
)
from cliente.api_client import (
    get_especialidades,
    get_nombres_especialidades,
    specialty_requires_subspecialty,
    get_nombres_areas_por_especialidad,
    add_specialty_config,
    add_subspecialty_config,
    set_specialty_active,
    set_subspecialty_active,
)
from comun.validators import (
    is_valid_dni,
    is_valid_nhc,
    hay_fisio_y_terapia_ocupacional,
    validar_preferencias_tratamiento,
    validar_hora_sesion,
)
from cliente.api_client import (
    preview_next_patient,
    add_waiting_patient_multiple,
    assign_next_patient,
    discharge_patient,
    add_treatment_session,
    get_treatment_sessions,
    get_session_summary,
    get_stats,
    delete_waitlist_entry,
    delete_active_treatment,
    get_clinical_followup_summary,
    generate_clinical_followup_report,
    get_patient_pain_series,
    get_patient_status_distribution,
    get_dashboard_specialty_summary,
    get_dashboard_session_summary,
    get_dashboard_adherence_by_specialty,
    get_patient_ai_consent,
    set_patient_ai_consent,
    generate_ai_clinical_summary,
)
from cliente.ui_helpers import (
    priority_badge,
    specialty_label,
    estado_sesion_label,
    dia_semana_espanol,
    parse_attendance_days,
    render_mini_calendar,
    audit_event_label,
)
from cliente.api_client import (
    authenticate_user,
    create_user,
    get_all_users,
    change_user_password,
    reset_user_password_to_default,
    get_professions,
    add_profession_config,
    set_profession_active,
    PASSWORD_TEMPORAL_POR_DEFECTO,
)

from cliente.api_client import (
    OllamaError,
)

st.set_page_config(
    page_title="Gestión de Rehabilitación",
    page_icon="🏥",
    layout="wide",
)

begin_api_run()

st.markdown(
    """
<style>
    .kpi-card {
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 14px;
        padding: 14px 16px;
        background: rgba(255,255,255,0.65);
    }
    .muted { color: rgba(0,0,0,0.55); font-size: 0.9rem; }
    .title { font-size: 1.4rem; font-weight: 700; }

    section[data-testid="stSidebar"] {
        background-color: #f4f6f8;
    }

    section[data-testid="stSidebar"] .stRadio > div {
        gap: 0.4rem;
    }

    section[data-testid="stSidebar"] label {
        font-weight: 600;
    }
</style>
""",
    unsafe_allow_html=True,
)

# La interfaz utiliza la API; no abre una conexión directa a PostgreSQL.
conn = None

# Inicio de sesión
if "user" not in st.session_state:
    st.session_state["user"] = None

notice = st.session_state.pop("_api_notice", None)
if notice:
    st.warning(notice)

if st.session_state["user"] is not None:
    st.session_state["user"] = get_current_session_user()

if st.session_state["user"] is None:
    st.markdown("## Acceso al sistema")

    username_login = st.text_input("Usuario", key="login_username")
    password_login = st.text_input(
        "Contraseña",
        type="password",
        key="login_password",
    )

    if st.button("Iniciar sesión", key="login_button"):
        user = authenticate_user(conn, username_login.strip(), password_login)
        if user:
            st.session_state["user"] = user
            st.success("Acceso correcto.")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")

    st.stop()

# Cambio obligatorio de contraseña
if st.session_state["user"].get("must_change_password"):
    st.markdown("## Cambio obligatorio de contraseña")
    st.warning(
        "Es tu primer acceso o el administrador ha restablecido tu contraseña. "
        "Debes actualizarla para continuar."
    )

    nueva_password_1 = st.text_input(
        "Nueva contraseña",
        type="password",
        key="force_new_password_1",
    )
    nueva_password_2 = st.text_input(
        "Repite la nueva contraseña",
        type="password",
        key="force_new_password_2",
    )

    if st.button("Actualizar contraseña", key="force_change_password_button"):
        if not nueva_password_1.strip():
            st.error("Introduce una nueva contraseña.")
        elif len(nueva_password_1.strip()) < 12:
            st.error("La nueva contraseña debe tener al menos 12 caracteres.")
        elif nueva_password_1 != nueva_password_2:
            st.error("Las contraseñas no coinciden.")
        elif nueva_password_1 == PASSWORD_TEMPORAL_POR_DEFECTO:
            st.error(
                "La nueva contraseña no puede ser la contraseña temporal por defecto."
            )
        else:
            change_user_password(
                conn,
                st.session_state["user"]["id"],
                nueva_password_1.strip(),
                current_password=st.session_state.get("login_password", ""),
            )
            st.session_state["user"] = authenticate_user(
                conn,
                st.session_state["user"]["username"],
                nueva_password_1.strip(),
            )
            st.success("Contraseña actualizada correctamente.")
            st.rerun()

    st.stop()

# -------------------- Variables de usuario y catálogos --------------------
usuario_actual = st.session_state["user"]
actor_sidebar = usuario_actual["dni"]
rol_usuario = usuario_actual["role"]
nombre_usuario = usuario_actual["full_name"]
profesion_usuario = usuario_actual["profession"]

especialidades_activas = get_nombres_especialidades(conn, only_active=True)

# -------------------- Sidebar --------------------

st.sidebar.title("🏥 Rehabilitación")

opciones_paginas = [
    "📊 Panel de control",
    "📝 Nueva solicitud",
    "⚕️ Tratamientos activos",
    "📈 Seguimiento clínico",
    "📉 Dashboard clínico",
    "🧾 Auditoría clínica",
]

if rol_usuario == "ADMIN":
    opciones_paginas.append("⚙️ Ajustes")
    opciones_paginas.append("📖 Registro de visitas")

page = st.sidebar.radio("Secciones", opciones_paginas, index=0, key="nav_page")

# Cargar bibliotecas gráficas solo al entrar en las pantallas que las utilizan.
if page in ("📈 Seguimiento clínico", "📉 Dashboard clínico"):
    import pandas as pd
    import matplotlib.pyplot as plt

st.sidebar.markdown("---")

specialty_filter = st.sidebar.selectbox(
    "Filtro por especialidad",
    ["Todas"] + especialidades_activas,
    key="sidebar_specialty_filter",
)

specialty_filter = specialty_filter or "Todas"
subspecialty_filter = "Todas"

if specialty_filter != "Todas" and specialty_requires_subspecialty(
    conn, specialty_filter
):
    areas_sidebar = get_nombres_areas_por_especialidad(
        conn, specialty_filter, only_active=True
    )
    subspecialty_filter = st.sidebar.selectbox(
        f"Área ({specialty_filter})",
        ["Todas"] + areas_sidebar,
        key="sidebar_area_filter",
    )


st.sidebar.markdown(f"**Usuario:** {nombre_usuario}")
st.sidebar.markdown(f"**DNI:** {actor_sidebar}")
st.sidebar.markdown(f"**Profesión:** {profesion_usuario}")
st.sidebar.markdown(f"**Rol:** {rol_usuario}")

assign_slot_filter = st.session_state.get("assign_slot_filter", "Todas")
assign_shift_filter = st.session_state.get("assign_shift_filter", "Todas")
assign_transport_filter = st.session_state.get("assign_transport_filter", "Todas")

# -------------------- Cabecera --------------------


col_titulo, col_cerrar = st.columns(
    [8, 1.5],
    vertical_alignment="center",
)

with col_titulo:
    st.markdown(
        '<div class="title">Sistema de Gestión de Rehabilitación</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="muted">Gestión clínica de solicitudes, tratamientos, auditoría y ajustes de configuración</div>',
        unsafe_allow_html=True,
    )

with col_cerrar:
    if st.button(
        "🚫 Cerrar sesión",
        key="logout_button_sidebar",
        width="stretch",
    ):
        cerrar_sesion()

st.write("")

if page == "📊 Panel de control":
    waiting, active, discharged = get_stats(conn)
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2], gap="large")
    with c1:
        st.markdown(
            f"<div class='kpi-card'><div class='muted'>En espera (elegibles)</div>"
            f"<div style='font-size:28px;font-weight:700'>{waiting}</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div class='kpi-card'><div class='muted'>En tratamiento</div>"
            f"<div style='font-size:28px;font-weight:700'>{active}</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"<div class='kpi-card'><div class='muted'>Finalizados</div>"
            f"<div style='font-size:28px;font-weight:700'>{discharged}</div></div>",
            unsafe_allow_html=True,
        )
    with c4:
        nxt = preview_next_patient(
            conn,
            specialty_filter=specialty_filter,
            subspecialty_filter=subspecialty_filter,
            slot_type_filter=assign_slot_filter,
            time_preference_filter=assign_shift_filter,
            transport_mode_filter=assign_transport_filter,
        )
        if nxt:
            st.markdown("<div class='kpi-card'>", unsafe_allow_html=True)
            st.markdown("**Siguiente candidato (con filtros)**")
            st.write(
                f"NHC: **{nxt['patient_id']}** · {priority_badge(nxt['priority_level'])}"
            )
            st.write(
                f"Unidad: **{specialty_label(nxt['specialty'], nxt['subspecialty'])}**"
            )
            st.write(
                f"Espera: **{nxt['wait_days']} días** · Solicitud: **{nxt['request_date'][:10]}**"
            )
            st.caption(f"Regla aplicada: {nxt['rule_applied']}")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                "<div class='kpi-card'><div class='muted'>Siguiente candidato</div>"
                "<div style='font-size:14px'>No hay pacientes elegibles.</div></div>",
                unsafe_allow_html=True,
            )

    st.write("")

# -------------------- Páginas --------------------
if page == "📊 Panel de control":
    left, right = st.columns([2.2, 1], gap="large")

    with left:
        st.subheader("Listado de pacientes en espera")

        f1, f2, f3 = st.columns([1, 1, 1], gap="medium")
        with f1:
            pr_filter = st.selectbox(
                "Prioridad", ["Todas"] + PRIORIDADES, key="dash_priority"
            )
        with f2:
            elig_filter = st.selectbox(
                "Elegibilidad", ["Solo elegibles", "Todos"], key="dash_elig"
            )
        with f3:
            sp_filter = st.selectbox(
                "Especialidad (tabla)",
                ["Todas"] + especialidades_activas,
                index=(
                    0
                    if specialty_filter == "Todas"
                    else (especialidades_activas.index(specialty_filter) + 1)
                ),
                key="dash_specialty",
            )

        ss_filter_table = "Todas"
        if sp_filter != "Todas" and specialty_requires_subspecialty(conn, sp_filter):
            areas_tabla = get_nombres_areas_por_especialidad(
                conn, sp_filter, only_active=True
            )
            ss_filter_table = st.selectbox(
                f"Área (tabla - {sp_filter})", ["Todas"] + areas_tabla, key="dash_area"
            )
        _, rows = get_table(
            conn,
            "waiting",
            priority=pr_filter,
            eligible_only=(elig_filter == "Solo elegibles"),
            specialty=sp_filter,
            subspecialty=ss_filter_table,
        )

        data = [{"NHC": r[1]} for r in rows]
        st.dataframe(data, width="stretch", hide_index=True)
    with right:
        st.subheader("Acciones clínicas")

        st.caption(
            "Elige la especialidad y el área del tratamiento en los filtros laterales. Se asignará por prioridad y antigüedad entre los pacientes que cumplan todos los filtros."
        )
        assign_shift_filter = st.selectbox(
            "Turno del hueco disponible", ["Todas"] + TURNOS, key="assign_shift_filter"
        )
        assign_slot_filter = st.selectbox(
            "Tipo de hueco disponible",
            ["Todas"] + TIPOS_HUECO,
            key="assign_slot_filter",
        )
        assign_transport_filter = st.selectbox(
            "Transporte del paciente",
            ["Todas"] + TRANSPORTES,
            key="assign_transport_filter",
        )
        attendance_pattern = st.selectbox(
            "Frecuencia del tratamiento",
            ["LXV", "MJ", "LABORABLES"],
            format_func=lambda x: {
                "LXV": "Lunes, Miércoles y Viernes",
                "MJ": "Martes y Jueves",
                "LABORABLES": "Todos los días laborables",
            }[x],
            key="assign_attendance_pattern",
        )

        attendance_days = OPCIONES_ASISTENCIA[attendance_pattern]

        if st.button("Asignar siguiente", width="stretch", key="btn_assign_next"):
            try:
                res = assign_next_patient(
                    conn,
                    assigned_by=actor_sidebar,
                    assigned_clinician_dni=actor_sidebar,
                    assigned_clinician_name=nombre_usuario,
                    assigned_clinician_profession=profesion_usuario,
                    specialty_filter=specialty_filter,
                    subspecialty_filter=subspecialty_filter,
                    attendance_days=attendance_days,
                    slot_type_filter=assign_slot_filter,
                    time_preference_filter=assign_shift_filter,
                    transport_mode_filter=assign_transport_filter,
                )
            except ValueError as e:
                st.error(str(e))
                st.stop()

            if not res:
                st.warning("No hay pacientes elegibles con esos filtros.")
            else:
                st.success(
                    f"Asignado NHC: {res['patient_id']} ({res['priority_level']}) "
                    f"al clínico {res['assigned_clinician_name']}"
                )
                st.info(
                    f"{specialty_label(res['specialty'], res['subspecialty'])} · "
                    f"{res['wait_days']} días de espera · "
                    f"Regla: {res['rule_applied']} · "
                    f"Frecuencia: {attendance_pattern} · "
                    f"Clínico responsable: {res['assigned_clinician_name']} "
                    f"({res['assigned_clinician_profession']})"
                )
                st.rerun()

        st.divider()
        st.caption("Formalización del alta de un tratamiento activo.")
        _, rowsA = get_table(conn, "active_basic")
        if not rowsA:
            st.info("No hay pacientes activos.")
        else:
            options = {
                f"{r[0]} · {r[1]} · {specialty_label(r[2], r[3])} · inicio {str(r[4])[:10]}": r[
                    0
                ]
                for r in rowsA
            }
            pick = st.selectbox(
                "NHC activo", list(options.keys()), key="dash_active_pick"
            )
            reason = st.selectbox(
                "Motivo del alta",
                ["FIN_TRATAMIENTO", "NO_ASISTE", "DERIVADO", "OTRO"],
                key="dash_discharge_reason",
            )
            comment = st.text_area(
                "Comentario clínico",
                placeholder="Escribe observaciones sobre el alta...",
                key="dash_discharge_comment",
            )

            if st.button("Dar alta", width="stretch", key="btn_discharge"):
                if reason == "OTRO" and not comment.strip():
                    st.error(
                        "Debes añadir un comentario clínico cuando el motivo es OTRO."
                    )
                else:
                    ok = discharge_patient(
                        conn,
                        options[pick],
                        reason=reason,
                        comment=comment.strip(),
                        actor=actor_sidebar,
                    )
                    if ok:
                        st.success("Alta registrada.")
                        st.rerun()
                    else:
                        st.error("No se pudo registrar el alta.")

elif page == "📝 Nueva solicitud":
    # Limpiar antes de crear los widgets, tras confirmar el guardado en la API.
    if st.session_state.pop("_reset_new_request", False):
        for field_key in list(st.session_state):
            if field_key.startswith(("req_", "sessions_", "areas_")):
                del st.session_state[field_key]

    st.subheader("Registro de nueva solicitud de rehabilitación")
    saved_notice = st.session_state.pop("_new_request_saved_notice", None)
    if saved_notice:
        st.success(saved_notice)

    c1, c2, c3, c4 = st.columns([1.2, 1, 1.3, 1.1], gap="large")

    with c1:
        patient_id = st.text_input(
            "NHC del paciente", placeholder="Ej: 123456", key="req_patient_id"
        ).strip()

    with c2:
        prioridades_normales = [
            prioridad for prioridad in PRIORIDADES if prioridad != "personal SACYL"
        ]
        prioridad_seleccionada = st.selectbox(
            "Prioridad",
            prioridades_normales,
            key="req_priority",
            disabled=bool(st.session_state.get("req_personal_sacyl", False)),
        )
        solicita_personal_sacyl = st.checkbox(
            "Personal SACYL",
            key="req_personal_sacyl",
        )
        priority_level = (
            "personal SACYL" if solicita_personal_sacyl else prioridad_seleccionada
        )
        if solicita_personal_sacyl:
            st.caption("Se registrará con la máxima prioridad.")

    with c3:
        request_dt = st.date_input(
            "Fecha de solicitud", value=date.today(), key="req_request_date"
        )

    with c4:
        eligible = st.checkbox("Elegible", value=True, key="req_eligible")

    ai_consent_accepted = None

    if is_valid_nhc(patient_id):
        consentimiento_actual = get_patient_ai_consent(conn, patient_id)
        opciones = ["No acepta el uso de IA", "Acepta el uso de IA"]
        indice = None if consentimiento_actual is None else int(consentimiento_actual)

        decision = st.radio(
            "¿El paciente acepta que sus informes se procesen con IA local?",
            opciones,
            index=indice,
            key=f"req_ai_consent_{patient_id}",
        )

        if decision is not None:
            ai_consent_accepted = decision == opciones[1]

        st.caption(
            "Si acepta, Ollama procesará los informes en el servidor de la aplicación; "
            "no se enviarán a un servicio de IA externo."
        )

    selected_specialties = st.multiselect(
        "Especialidades",
        especialidades_activas,
        key="req_specialties_multi",
    )

    st.markdown("### Configuración del tratamiento")

    cfg1, cfg2, cfg3, cfg4 = st.columns([1, 1, 1, 1], gap="medium")

    with cfg1:
        slot_type = st.selectbox("Tipo de hueco", TIPOS_HUECO, key="req_slot_type")

    with cfg2:
        time_preference = st.selectbox("Turno", TURNOS, key="req_time_preference")

    with cfg3:
        transport_mode = st.selectbox(
            "Transporte", TRANSPORTES, key="req_transport_mode"
        )

    preferred_hour = None
    with cfg4:
        if transport_mode == "AMBULANCIA":
            preferred_hour = st.selectbox(
                "Hora ambulancia", HORAS_AMBULANCIA, key="req_preferred_hour"
            )
        else:
            st.caption("Hora fija: no aplica")

    coordination_rule = "NINGUNA"
    if hay_fisio_y_terapia_ocupacional(selected_specialties):
        coordination_rule = st.selectbox(
            "Coordinación Fisio + Terapia ocupacional",
            REGLAS_COORDINACION,
            index=1,
            key="req_coordination_rule",
        )
        st.caption(
            "MISMO_DIA: ambos tratamientos comparten días. DIAS_ALTERNOS: no pueden coincidir."
        )

    sesiones_por_especialidad = {}
    areas_por_especialidad = {}
    sesiones_por_area = {}

    if selected_specialties:
        st.markdown("### Número de sesiones orientativas por especialidad (opcional)")
        for sp in selected_specialties:
            if not specialty_requires_subspecialty(conn, sp):
                sesiones_por_especialidad[sp] = st.text_input(
                    f"Sesiones orientativas para {sp} (opcional)",
                    placeholder="Ej: 10",
                    key=f"sessions_{sp}",
                ).strip()

    for sp in selected_specialties:
        if specialty_requires_subspecialty(conn, sp):
            areas_disponibles = get_nombres_areas_por_especialidad(
                conn, sp, only_active=True
            )
            areas_por_especialidad[sp] = st.multiselect(
                f"Áreas de {sp}", areas_disponibles, key=f"areas_{sp}"
            )
            st.caption(f"Si seleccionas {sp}, debes indicar al menos un área.")

            if areas_por_especialidad[sp]:
                st.markdown(
                    f"### Número de sesiones orientativas por área de {sp} (opcional)"
                )
                for sub in areas_por_especialidad[sp]:
                    sesiones_por_area[(sp, sub)] = st.text_input(
                        f"Sesiones orientativas para {sp} · {sub} (opcional)",
                        placeholder="Ej: 10",
                        key=f"sessions_{sp}_{sub}",
                    ).strip()

    st.caption(
        "Se creará una solicitud independiente por cada especialidad seleccionada. "
        "Si la especialidad requiere área, se creará una por cada área seleccionada."
    )

    if st.button("Guardar solicitud", width="stretch", key="req_submit"):
        if not patient_id:
            st.error("Introduce el NHC del paciente.")
        elif not is_valid_nhc(patient_id):
            st.error("El NHC debe tener exactamente 6 números.")
        elif ai_consent_accepted is None:
            st.error("Selecciona si el paciente acepta o rechaza el uso de IA.")
        elif not selected_specialties:
            st.error("Selecciona al menos una especialidad.")
        else:
            error_preferencias = validar_preferencias_tratamiento(
                slot_type=slot_type,
                time_preference=time_preference,
                transport_mode=transport_mode,
                preferred_hour=preferred_hour,
            )
            if error_preferencias:
                st.error(error_preferencias)
                st.stop()

            for sp, valor in sesiones_por_especialidad.items():
                if valor and not valor.isdigit():
                    st.error(
                        f"Las sesiones de {sp} deben ser un número entero o dejarse en blanco."
                    )
                    st.stop()

            for (sp, sub), valor in sesiones_por_area.items():
                if valor and not valor.isdigit():
                    st.error(
                        f"Las sesiones de {sp} · {sub} deben ser un número entero o dejarse en blanco."
                    )
                    st.stop()

            requests = []

            for sp in selected_specialties:
                if specialty_requires_subspecialty(conn, sp):
                    if not areas_por_especialidad.get(sp):
                        st.error(f"Debes seleccionar al menos un área para {sp}.")
                        st.stop()

                    for sub in areas_por_especialidad[sp]:
                        requests.append(
                            {
                                "specialty": sp,
                                "subspecialty": sub,
                                "prescribed_sessions": int(sesiones_por_area[(sp, sub)])
                                if sesiones_por_area.get((sp, sub))
                                else None,
                            }
                        )
                else:
                    requests.append(
                        {
                            "specialty": sp,
                            "subspecialty": None,
                            "prescribed_sessions": int(sesiones_por_especialidad[sp])
                            if sesiones_por_especialidad.get(sp)
                            else None,
                        }
                    )

            add_waiting_patient_multiple(
                conn,
                patient_id=patient_id,
                priority_level=priority_level,
                requests=requests,
                request_date_iso=iso_utc_from_date(request_dt),
                eligible=eligible,
                actor=actor_sidebar,
                slot_type=slot_type,
                time_preference=time_preference,
                transport_mode=transport_mode,
                preferred_hour=preferred_hour,
                coordination_rule=coordination_rule,
                ai_consent_accepted=ai_consent_accepted,
            )

            st.session_state["_new_request_saved_notice"] = (
                f"Solicitud guardada para NHC {patient_id}. Se han creado {len(requests)} entradas."
            )
            st.session_state["_reset_new_request"] = True
            st.rerun()

elif page == "⚕️ Tratamientos activos":
    st.subheader("Pacientes con tratamiento activo")
    nhc_activos = st.text_input(
        "Buscar paciente por NHC",
        placeholder="Introduce las 6 cifras del NHC",
        max_chars=6,
        key="active_search_nhc",
    ).strip()
    if nhc_activos and not is_valid_nhc(nhc_activos):
        st.info("Introduce las 6 cifras del NHC, incluidos los ceros iniciales.")
    else:
        _, rows = get_table(
            conn,
            "active_details",
            **({"patient_id": nhc_activos} if nhc_activos else {}),
        )
        data = [{"NHC": r[1]} for r in rows]
        if data:
            st.dataframe(data, width="stretch", hide_index=True)
        else:
            st.info(
                "No hay pacientes con tratamiento activo que coincidan con la búsqueda."
            )

    st.divider()
    st.subheader("🗓️ Registro de sesiones")

    nhc_sesiones = st.text_input(
        "Buscar tratamiento por NHC",
        placeholder="Introduce las 6 cifras del NHC",
        max_chars=6,
        key="session_search_nhc",
    ).strip()
    if nhc_sesiones and not is_valid_nhc(nhc_sesiones):
        st.info("Introduce las 6 cifras del NHC, incluidos los ceros iniciales.")
        rowsA = []
    else:
        _, rowsA = get_table(
            conn,
            "active_for_sessions",
            **({"patient_id": nhc_sesiones} if nhc_sesiones else {}),
        )

    if not rowsA:
        st.info(
            "No hay tratamientos activos para ese NHC."
            if nhc_sesiones
            else "No hay pacientes activos para registrar sesiones."
        )
    else:
        options = {
            f"{r[0]} · {r[1]} · {specialty_label(r[2], r[3])} · inicio {str(r[11])[:10]}": {
                "rehab_active_id": r[0],
                "patient_id": r[1],
                "specialty": r[2],
                "subspecialty": r[3],
                "prescribed_sessions": r[4],
                "attendance_days": parse_attendance_days(r[5]),
                "slot_type": r[6],
                "time_preference": r[7],
                "transport_mode": r[8],
                "preferred_hour": r[9],
                "coordination_rule": r[10],
                "start_date": r[11],
            }
            for r in rowsA
        }

        selected_label = st.selectbox(
            "Selecciona NHC en tratamiento",
            list(options.keys()),
            key="session_patient_pick",
        )
        selected_patient = options[selected_label]

        dias_texto = (
            ", ".join(selected_patient["attendance_days"])
            if selected_patient["attendance_days"]
            else "No definidos"
        )
        st.caption(f"Días de asistencia establecidos: {dias_texto}")

        st.caption(
            f"Hueco: {selected_patient['slot_type']} · "
            f"Turno: {selected_patient['time_preference']} · "
            f"Transporte: {selected_patient['transport_mode']}"
            + (
                f" · Hora fija: {selected_patient['preferred_hour']}"
                if selected_patient["preferred_hour"]
                else ""
            )
        )

        if (
            selected_patient.get("coordination_rule")
            and selected_patient["coordination_rule"] != "NINGUNA"
        ):
            st.caption(
                f"Coordinación con otro tratamiento: {selected_patient['coordination_rule']}"
            )

        resumen = get_session_summary(conn, selected_patient["rehab_active_id"])
        realizadas_y_revision = resumen["REALIZADA"] + resumen["REVISION"]

        if selected_patient["prescribed_sessions"] is not None:
            restantes = max(
                selected_patient["prescribed_sessions"] - realizadas_y_revision, 0
            )
        else:
            restantes = None

        r1, r2, r3, r4, r5 = st.columns(5)
        r1.metric(
            "Sesiones orientativas",
            selected_patient["prescribed_sessions"]
            if selected_patient["prescribed_sessions"] is not None
            else "No definidas",
        )
        r2.metric("Realizadas", resumen["REALIZADA"])
        r3.metric("Revisiones", resumen["REVISION"])
        r4.metric("Faltas justificadas", resumen["FALTA_JUSTIFICADA"])
        r5.metric("Faltas no justificadas", resumen["FALTA_NO_JUSTIFICADA"])

        if restantes is None:
            st.caption("Sesiones orientativas pendientes: no definidas")
        else:
            st.caption(f"Sesiones orientativas pendientes: {restantes}")

        c1, c2, c3 = st.columns([1, 1, 1], gap="medium")
        with c1:
            session_date_value = st.date_input(
                "Día del tratamiento", value=date.today(), key="session_date"
            )
        with c2:
            session_time_value = st.time_input(
                "Hora del tratamiento", value=time(9, 0), key="session_time"
            )
        with c3:
            session_status = st.selectbox(
                "Estado de la sesión",
                ["REALIZADA", "REVISION", "FALTA_JUSTIFICADA", "FALTA_NO_JUSTIFICADA"],
                format_func=estado_sesion_label,
                key="session_status",
            )

        absence_reason = ""
        out_of_schedule_reason = ""
        dia_sesion = dia_semana_espanol(session_date_value)
        fuera_de_dias = (
            bool(selected_patient["attendance_days"])
            and dia_sesion not in selected_patient["attendance_days"]
        )

        if fuera_de_dias:
            st.warning(
                f"La fecha seleccionada cae en {dia_sesion}, que no está dentro de los días establecidos del tratamiento."
            )
            out_of_schedule_reason = st.text_area(
                "Motivo por el que se registra fuera de los días establecidos",
                placeholder="Ej: festivo compensado, cambio puntual, reorganización de agenda...",
                key="session_out_of_schedule_reason",
            )

        if session_status in ["FALTA_JUSTIFICADA", "FALTA_NO_JUSTIFICADA"]:
            absence_reason = st.text_area(
                "Motivo de la falta",
                placeholder="Ejemplo: enfermedad, cita médica, no acudió...",
                key="session_absence_reason",
            )
            if session_status == "FALTA_NO_JUSTIFICADA":
                st.warning("Esta falta quedará registrada como NO JUSTIFICADA.")

        error_hora = None
        if session_status in ["REALIZADA", "REVISION"]:
            error_hora = validar_hora_sesion(selected_patient, session_time_value)

        st.markdown("### Registro clínico de la sesión")

        clinical_note = st.text_area(
            "Nota clínica",
            placeholder="Describe evolución, hallazgos, respuesta al tratamiento, tolerancia, etc.",
            key="session_clinical_note",
        )

        col_a, col_b = st.columns(2)

        with col_a:
            pain_eva = st.number_input(
                "Dolor EVA (0-10)",
                min_value=0,
                max_value=10,
                value=0,
                step=1,
                key="session_pain_eva",
            )

        with col_b:
            goal_status = st.selectbox(
                "Estado del objetivo terapéutico",
                ["", "NO_INICIADO", "PARCIAL", "CUMPLIDO", "EMPEORA"],
                key="session_goal_status",
            )

        functional_status = st.text_input(
            "Valoración funcional breve",
            placeholder="Ej: mejora de la marcha, mayor rango articular, sin cambios en equilibrio...",
            key="session_functional_status",
        )

        incidents = st.text_area(
            "Incidencias",
            placeholder="Ej: mala tolerancia, reagudización, fatiga, mareo, sin incidencias...",
            key="session_incidents",
        )

        if st.button("Guardar sesión o falta", width="stretch", key="btn_save_session"):
            if (
                session_status in ["FALTA_JUSTIFICADA", "FALTA_NO_JUSTIFICADA"]
                and not absence_reason.strip()
            ):
                st.error("Debes indicar el motivo de la falta.")
            elif fuera_de_dias and not out_of_schedule_reason.strip():
                st.error(
                    "Debes indicar el motivo por el que se registra fuera de los días establecidos."
                )
            elif error_hora:
                st.error(error_hora)
            else:
                add_treatment_session(
                    conn=conn,
                    rehab_active_id=selected_patient["rehab_active_id"],
                    patient_id=selected_patient["patient_id"],
                    specialty=selected_patient["specialty"],
                    subspecialty=selected_patient["subspecialty"],
                    session_date_value=session_date_value,
                    session_time_value=session_time_value
                    if session_status in ["REALIZADA", "REVISION"]
                    else None,
                    status=session_status,
                    absence_reason=absence_reason.strip(),
                    out_of_schedule_reason=out_of_schedule_reason.strip(),
                    recorded_by=actor_sidebar,
                    clinical_note=clinical_note,
                    pain_eva=pain_eva
                    if session_status in ["REALIZADA", "REVISION"]
                    else None,
                    functional_status=functional_status,
                    goal_status=goal_status,
                    incidents=incidents,
                )

        st.markdown("### Calendario mensual")
        hoy = date.today()
        mes_cal = st.selectbox(
            "Mes",
            list(range(1, 13)),
            index=hoy.month - 1,
            format_func=lambda m: MESES_ES[m],
            key="calendar_month",
        )
        anio_cal = st.number_input(
            "Año",
            min_value=2020,
            max_value=2100,
            value=hoy.year,
            step=1,
            key="calendar_year",
        )

        render_mini_calendar(
            conn, selected_patient["rehab_active_id"], int(anio_cal), int(mes_cal)
        )

        st.markdown("### Historial del NHC seleccionado")
        sess_cols, sess_rows = get_treatment_sessions(
            conn, selected_patient["rehab_active_id"]
        )

        sess_data = []
        for r in sess_rows:
            d = dict(zip(sess_cols, r))
            d["NHC"] = d.pop("patient_id")
            d["specialty"] = specialty_label(d["specialty"], d.get("subspecialty"))
            if hasattr(d["session_date"], "isoformat"):
                d["session_date"] = d["session_date"].isoformat()
            d["session_time"] = (
                str(d["session_time"])[:5] if d.get("session_time") is not None else ""
            )
            d["status"] = estado_sesion_label(d["status"])
            if hasattr(d["created_at"], "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            d["motivo_falta"] = d.pop("absence_reason")
            d["motivo_fuera_dias"] = d.pop("out_of_schedule_reason")
            d["registrado_por"] = d.pop("recorded_by")
            d.pop("subspecialty", None)
            sess_data.append(d)

        if sess_data:
            st.dataframe(sess_data, width="stretch", hide_index=True)
        else:
            st.info("Todavía no hay sesiones registradas para este NHC.")

    st.subheader("Histórico de pacientes con alta")
    _, rows = get_table(conn, "discharged", limit=300)
    data = [{"NHC": r[1]} for r in rows]
    st.dataframe(data, width="stretch", hide_index=True)

elif page == "📈 Seguimiento clínico":
    st.subheader("Seguimiento clínico del paciente")

    nhc_busqueda = st.text_input(
        "Buscar por NHC",
        placeholder="Introduce las 6 cifras del NHC",
        max_chars=6,
        key="followup_search_nhc",
    ).strip()
    if nhc_busqueda and not is_valid_nhc(nhc_busqueda):
        st.info("Introduce las 6 cifras del NHC, incluidos los ceros iniciales.")
        rowsA = []
    else:
        _, rowsA = get_table(
            conn,
            "active_basic",
            **({"patient_id": nhc_busqueda} if nhc_busqueda else {}),
        )

    if not rowsA:
        st.info(
            "No hay tratamientos activos para ese NHC."
            if nhc_busqueda
            else "No hay tratamientos activos para seguimiento."
        )
    else:
        options = {
            f"{r[0]} · {r[1]} · {specialty_label(r[2], r[3])} · inicio {str(r[4])[:10]}": {
                "rehab_active_id": r[0],
                "patient_id": r[1],
                "specialty": r[2],
                "subspecialty": r[3],
                "start_date": r[4],
            }
            for r in rowsA
        }

        selected_label = st.selectbox(
            "Selecciona tratamiento", list(options.keys()), key="followup_patient_pick"
        )

        selected_patient = options[selected_label]

        summary = get_clinical_followup_summary(
            conn, selected_patient["rehab_active_id"]
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Adherencia", f"{summary['adherence_percent']}%")
        c2.metric(
            "Dolor inicial",
            summary["first_pain"] if summary["first_pain"] is not None else "Sin datos",
        )
        c3.metric(
            "Dolor actual",
            summary["last_pain"] if summary["last_pain"] is not None else "Sin datos",
        )
        c4.metric("Tendencia EVA", summary["pain_trend"])

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Sesiones realizadas", summary["realizadas"])
        c6.metric("Revisiones", summary["revisiones"])
        c7.metric("Faltas justificadas", summary["faltas_justificadas"])
        c8.metric("Faltas no justificadas", summary["faltas_no_justificadas"])

        st.markdown("### Alertas clínicas")

        if summary["abandonment_risk"]:
            st.warning("Posible riesgo de abandono terapéutico.")
        else:
            st.success("Sin indicios claros de abandono terapéutico.")

        if summary["stagnation_risk"]:
            st.warning("Posible estancamiento funcional. Revisar plan terapéutico.")
        else:
            st.success("Sin indicios claros de estancamiento funcional.")

        st.markdown("### Última situación clínica")

        st.write(
            f"**Valoración funcional:** {summary['last_functional_status'] or 'Sin registro'}"
        )
        st.write(
            f"**Estado del objetivo:** {summary['last_goal_status'] or 'Sin registro'}"
        )

        st.markdown("### Informe automático")

        report = generate_clinical_followup_report(
            conn,
            selected_patient["rehab_active_id"],
        )

        st.text_area(
            "Informe generado",
            value=report,
            height=320,
            key="clinical_followup_report",
        )

        patient_id = selected_patient["patient_id"]
        rehab_id = selected_patient["rehab_active_id"]
        consentimiento = get_patient_ai_consent(conn, patient_id)
        # No reutilizar borradores antiguos que carezcan del marcado de demostración.
        metadata_ia = st.session_state.get(f"ai_metadata_{rehab_id}", {})
        if (
            metadata_ia.get("use_mode") != "demo"
            or metadata_ia.get("ai_generated") is not True
        ):
            for campo_ia in (
                "ai_summary",
                "ai_model",
                "ai_metadata",
                "ai_summary_display",
            ):
                st.session_state.pop(f"{campo_ia}_{rehab_id}", None)

        st.markdown("#### Resumen con IA local — demostración del TFG")
        st.caption(
            "La decisión de aceptación se simula con casos ficticios. No se recoge aquí un consentimiento jurídico para tratar datos reales."
        )

        opciones = ["No acepta el uso de IA", "Acepta el uso de IA"]
        indice = None if consentimiento is None else int(consentimiento)

        decision = st.radio(
            "Decisión del paciente sobre el uso de IA",
            opciones,
            index=indice,
            key=f"followup_ai_consent_{rehab_id}",
        )

        if st.button(
            "Guardar decisión de IA",
            key=f"save_ai_consent_{rehab_id}",
        ):
            if decision is None:
                st.error("Selecciona aceptar o rechazar.")
            else:
                set_patient_ai_consent(
                    conn,
                    patient_id,
                    accepted=(decision == opciones[1]),
                    actor=actor_sidebar,
                )
                st.session_state.pop(f"ai_summary_{rehab_id}", None)
                st.session_state.pop(f"ai_metadata_{rehab_id}", None)
                st.session_state.pop(f"ai_summary_display_{rehab_id}", None)
                st.success("Decisión guardada.")
                st.rerun()

        if consentimiento is True:
            st.warning(
                "IA experimental para el TFG: utiliza solo informes ficticios. El resultado puede contener errores, omisiones o sesgos y no está autorizado para atender pacientes reales."
            )
            with st.expander("Antes de utilizar el resumen"):
                st.write(
                    "Comprueba las fuentes, fechas y datos ausentes. El modelo no decide prioridades, altas ni cambios de tratamiento. La aceptación simulada no sustituye una base jurídica ni una autorización del hospital. La ocultación de algunos identificadores no garantiza anonimización."
                )
            synthetic_confirmed = st.checkbox(
                "Confirmo que este caso y sus informes son ficticios y que no usaré el resultado para atender pacientes reales",
                key=f"ai_demo_confirm_{rehab_id}",
            )

            if st.button(
                "Generar resumen con IA local",
                key=f"ai_summary_btn_{rehab_id}",
                disabled=not synthetic_confirmed,
            ):
                try:
                    with st.spinner("Generando resumen local..."):
                        resumen, modelo = generate_ai_clinical_summary(
                            conn,
                            rehab_id,
                            actor=actor_sidebar,
                            synthetic_data_confirmed=synthetic_confirmed,
                        )

                    st.session_state[f"ai_summary_{rehab_id}"] = resumen
                    st.session_state[f"ai_model_{rehab_id}"] = modelo

                except (OllamaError, PermissionError, ValueError) as exc:
                    st.error(str(exc))

            if f"ai_summary_{rehab_id}" in st.session_state:
                st.caption(
                    f"Modelo: {st.session_state.get(f'ai_model_{rehab_id}', 'Ollama')}. "
                    "Contrasta el resultado con los informes originales."
                )
                st.text_area(
                    "Resumen, valoraciones y aspectos para revisar",
                    value=st.session_state[f"ai_summary_{rehab_id}"],
                    height=400,
                    key=f"ai_summary_display_{rehab_id}",
                )
                st.download_button(
                    "Descargar borrador identificado como IA (JSON)",
                    data=json.dumps(
                        {
                            "summary": st.session_state[f"ai_summary_{rehab_id}"],
                            "metadata": st.session_state.get(
                                f"ai_metadata_{rehab_id}", {}
                            ),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    file_name="borrador_ia_demostracion.json",
                    mime="application/json",
                    key=f"ai_download_{rehab_id}",
                )
        else:
            st.info("No consta aceptación; los informes no se procesarán con IA.")

        st.markdown("### Historial clínico de sesiones")

        sess_cols, sess_rows = get_treatment_sessions(
            conn, selected_patient["rehab_active_id"]
        )

        sess_data = []
        for r in sess_rows:
            d = dict(zip(sess_cols, r))
            d["NHC"] = d.pop("patient_id")
            d["specialty"] = specialty_label(d["specialty"], d.get("subspecialty"))
            if hasattr(d["session_date"], "isoformat"):
                d["session_date"] = d["session_date"].isoformat()
            d["session_time"] = (
                str(d["session_time"])[:5] if d.get("session_time") is not None else ""
            )
            d["status"] = estado_sesion_label(d["status"])
            if hasattr(d["created_at"], "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            d["motivo_falta"] = d.pop("absence_reason")
            d["motivo_fuera_dias"] = d.pop("out_of_schedule_reason")
            d["registrado_por"] = d.pop("recorded_by")
            d["nota_clinica"] = d.pop("clinical_note")
            d["eva"] = d.pop("pain_eva")
            d["funcional"] = d.pop("functional_status")
            d["objetivo"] = d.pop("goal_status")
            d["incidencias"] = d.pop("incidents")
            d.pop("subspecialty", None)
            sess_data.append(d)

        if sess_data:
            st.dataframe(sess_data, width="stretch", hide_index=True)
        else:
            st.info("No hay sesiones registradas para este tratamiento.")

elif page == "📉 Dashboard clínico":
    st.subheader("Dashboard clínico")

    dashboard_view = st.radio(
        "Vista del dashboard",
        ["Paciente individual", "Resumen global", "Eventos"],
        horizontal=True,
        key="dashboard_view",
    )

    if dashboard_view == "Paciente individual":
        st.markdown("### Evolución del paciente")

        nhc_busqueda = st.text_input(
            "Buscar por NHC",
            placeholder="Introduce las 6 cifras del NHC",
            max_chars=6,
            key="dashboard_search_nhc",
        ).strip()
        if nhc_busqueda and not is_valid_nhc(nhc_busqueda):
            st.info("Introduce las 6 cifras del NHC, incluidos los ceros iniciales.")
            rowsA = []
        else:
            _, rowsA = get_table(
                conn,
                "active_basic",
                **({"patient_id": nhc_busqueda} if nhc_busqueda else {}),
            )

        if not rowsA:
            st.info(
                "No hay tratamientos activos para ese NHC."
                if nhc_busqueda
                else "No hay tratamientos activos para visualizar."
            )
        else:
            options = {
                f"{r[0]} · {r[1]} · {specialty_label(r[2], r[3])} · inicio {str(r[4])[:10]}": {
                    "rehab_active_id": r[0],
                    "patient_id": r[1],
                    "specialty": r[2],
                    "subspecialty": r[3],
                    "start_date": r[4],
                }
                for r in rowsA
            }

            selected_label = st.selectbox(
                "Selecciona tratamiento",
                list(options.keys()),
                key="dashboard_patient_pick",
            )
            selected_patient = options[selected_label]

            resumen = get_clinical_followup_summary(
                conn, selected_patient["rehab_active_id"]
            )

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Adherencia", f"{resumen['adherence_percent']}%")
            m2.metric("Realizadas", resumen["realizadas"])
            m3.metric("Revisiones", resumen["revisiones"])
            m4.metric("Faltas no justificadas", resumen["faltas_no_justificadas"])

            # -------- Evolución EVA --------
            st.markdown("#### Evolución del dolor (EVA)")
            pain_cols, pain_rows = get_patient_pain_series(
                conn, selected_patient["rehab_active_id"]
            )

            if pain_rows:
                pain_df = pd.DataFrame(pain_rows, columns=pain_cols)
                pain_df["session_date"] = pd.to_datetime(pain_df["session_date"])

                fig, ax = plt.subplots(figsize=(8, 4))
                ax.plot(pain_df["session_date"], pain_df["pain_eva"], marker="o")
                ax.set_xlabel("Fecha")
                ax.set_ylabel("EVA")
                ax.set_title("Evolución EVA")
                ax.grid(True, alpha=0.3)
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("No hay datos EVA suficientes para este tratamiento.")

            # -------- Distribución de estados --------
            st.markdown("#### Distribución de sesiones")
            dist_cols, dist_rows = get_patient_status_distribution(
                conn, selected_patient["rehab_active_id"]
            )

            if dist_rows:
                dist_df = pd.DataFrame(dist_rows, columns=dist_cols)
                dist_df["status"] = dist_df["status"].map(
                    {
                        "REALIZADA": "Realizada",
                        "REVISION": "Revisión",
                        "FALTA_JUSTIFICADA": "Falta justificada",
                        "FALTA_NO_JUSTIFICADA": "Falta no justificada",
                    }
                )

                fig2, ax2 = plt.subplots(figsize=(7, 4))
                ax2.bar(dist_df["status"], dist_df["total"])
                ax2.set_xlabel("Estado")
                ax2.set_ylabel("Número de sesiones")
                ax2.set_title("Distribución de estados de sesión")
                plt.xticks(rotation=20)
                st.pyplot(fig2)
                plt.close(fig2)
            else:
                st.info("No hay sesiones registradas para mostrar la distribución.")

            # -------- Resumen clínico --------
            st.markdown("#### Resumen clínico automático")
            report = generate_clinical_followup_report(
                conn, selected_patient["rehab_active_id"]
            )
            st.text_area(
                "Informe de seguimiento",
                value=report,
                height=260,
                key="dashboard_followup_report",
            )

    elif dashboard_view == "Resumen global":
        st.markdown("### Resumen global del servicio")

        # -------- Especialidades --------
        sp_cols, sp_rows = get_dashboard_specialty_summary(conn)
        if sp_rows:
            sp_df = pd.DataFrame(sp_rows, columns=sp_cols)

            st.markdown("#### Pacientes por especialidad")
            fig3, ax3 = plt.subplots(figsize=(8, 4))
            ax3.bar(sp_df["specialty"], sp_df["activos"])
            ax3.set_xlabel("Especialidad")
            ax3.set_ylabel("Pacientes activos")
            ax3.set_title("Pacientes activos por especialidad")
            plt.xticks(rotation=20)
            st.pyplot(fig3)
            plt.close(fig3)

            st.dataframe(sp_df, width="stretch", hide_index=True)
        else:
            st.info("No hay datos de especialidades para mostrar.")

        # -------- Estados de sesión globales --------
        ss_cols, ss_rows = get_dashboard_session_summary(conn)
        if ss_rows:
            ss_df = pd.DataFrame(ss_rows, columns=ss_cols)
            ss_df["status"] = ss_df["status"].map(
                {
                    "REALIZADA": "Realizada",
                    "REVISION": "Revisión",
                    "FALTA_JUSTIFICADA": "Falta justificada",
                    "FALTA_NO_JUSTIFICADA": "Falta no justificada",
                }
            )

            st.markdown("#### Estados globales de las sesiones")
            fig4, ax4 = plt.subplots(figsize=(8, 4))
            ax4.bar(ss_df["status"], ss_df["total"])
            ax4.set_xlabel("Estado")
            ax4.set_ylabel("Total")
            ax4.set_title("Distribución global de estados de sesión")
            plt.xticks(rotation=20)
            st.pyplot(fig4)
            plt.close(fig4)
        else:
            st.info("No hay sesiones registradas globalmente.")

        # -------- Adherencia por especialidad --------
        ad_cols, ad_rows = get_dashboard_adherence_by_specialty(conn)
        if ad_rows:
            ad_df = pd.DataFrame(ad_rows, columns=ad_cols)

            ad_df["adherencia_pct"] = ad_df.apply(
                lambda row: (
                    round((row["asistidas"] / row["total"]) * 100, 1)
                    if row["total"] > 0
                    else 0
                ),
                axis=1,
            )

            st.markdown("#### Adherencia por especialidad")
            fig5, ax5 = plt.subplots(figsize=(8, 4))
            ax5.bar(ad_df["specialty"], ad_df["adherencia_pct"])
            ax5.set_xlabel("Especialidad")
            ax5.set_ylabel("Adherencia (%)")
            ax5.set_title("Adherencia por especialidad")
            plt.xticks(rotation=20)
            st.pyplot(fig5)
            plt.close(fig5)

            st.dataframe(ad_df, width="stretch", hide_index=True)
        else:
            st.info("No hay datos de adherencia por especialidad.")

    elif dashboard_view == "Eventos":
        st.markdown("### Eventos del paciente")
        evento_nhc = st.text_input(
            "Buscar eventos por NHC", max_chars=6, key="dashboard_events_nhc"
        ).strip()
        eventos_disponibles = {
            "Todos": None,
            "Solicita tratamiento": "CREACION_SOLICITUD",
            "Comienza el tratamiento": "ASIGNACION_AUTOMATICA",
            "Alta del tratamiento": "ALTA_TRATAMIENTO",
            "Decisión de consentimiento de IA": "CONSENTIMIENTO_IA",
            "Generación de resumen con IA": "GENERACION_RESUMEN_IA",
            "Eliminación de solicitud": "ELIMINACION_ADMIN_LISTA_ESPERA",
            "Eliminación de tratamiento": "ELIMINACION_ADMIN_TRATAMIENTO",
            "Registro de sesión": "REGISTRO_SESION",
            "Modificación de sesión": "MODIFICACION_SESION",
            "Eliminación de sesión": "ELIMINACION_SESION",
        }
        motivo_evento = st.selectbox(
            "Motivo / evento", list(eventos_disponibles), key="dashboard_event_filter"
        )
        consentimientos = {
            "Todos": None,
            "Acepta IA": "accepted",
            "Rechaza IA": "rejected",
            "Sin decisión registrada": "missing",
        }
        decision_ia = st.selectbox(
            "Consentimiento de IA",
            list(consentimientos),
            key="dashboard_consent_filter",
        )
        st.caption(
            "Los tres filtros se combinan. El consentimiento refleja la decisión actual del paciente, no necesariamente la que tenía en la fecha del evento."
        )
        if evento_nhc and not is_valid_nhc(evento_nhc):
            st.info("Introduce las 6 cifras del NHC.")
        else:
            _, eventos = get_table(
                conn,
                "audit",
                patient_id=evento_nhc or None,
                event=eventos_disponibles[motivo_evento],
                ai_consent=consentimientos[decision_ia],
                limit=400,
            )
            filas_eventos = [
                {
                    "NHC": fila[2],
                    "Fecha": str(fila[13]),
                    "Motivo / evento": audit_event_label(fila[1]),
                    "Especialidad": fila[3] or "No aplica",
                    "Área": fila[4] or "—",
                    "Sesiones realizadas al alta": fila[15],
                    "Revisiones al alta": fila[16],
                    "Observaciones": fila[11] or "",
                }
                for fila in eventos
            ]
            if filas_eventos:
                st.dataframe(filas_eventos, width="stretch", hide_index=True)
            else:
                st.info("No hay eventos con los filtros seleccionados.")

elif page == "🧾 Auditoría clínica":
    st.subheader("Registro de auditoría clínica")

    busqueda_nhc_audit = st.text_input(
        "Buscar por NHC",
        placeholder="Introduce las 6 cifras del NHC",
        max_chars=6,
        key="audit_search_nhc",
    ).strip()
    opciones_consentimiento_audit = {
        "Todos": None,
        "Acepta el uso de IA": "accepted",
        "Rechaza el uso de IA": "rejected",
        "Sin decisión registrada": "missing",
    }
    consentimiento_audit = st.selectbox(
        "Consentimiento de uso de IA",
        list(opciones_consentimiento_audit),
        key="audit_consent_filter",
    )
    st.caption(
        "El filtro de IA utiliza la decisión actual del paciente. Se combina con el NHC y los demás filtros."
    )

    f1, f2, f3 = st.columns([1, 1, 1], gap="medium")
    with f1:
        audit_pr_filter = st.selectbox(
            "Prioridad", ["Todas"] + PRIORIDADES, key="audit_priority"
        )
    with f2:
        audit_elig_filter = st.selectbox(
            "Elegibilidad", ["Todos", "Solo elegibles"], key="audit_elig"
        )
    with f3:
        audit_sp_filter = st.selectbox(
            "Especialidad",
            ["Todas"] + especialidades_activas,
            index=(
                0
                if specialty_filter == "Todas"
                else (especialidades_activas.index(specialty_filter) + 1)
            ),
            key="audit_specialty",
        )

    audit_ss_filter = "Todas"
    if audit_sp_filter != "Todas" and specialty_requires_subspecialty(
        conn, audit_sp_filter
    ):
        areas_audit = get_nombres_areas_por_especialidad(
            conn, audit_sp_filter, only_active=True
        )
        audit_ss_filter = st.selectbox(
            f"Área ({audit_sp_filter})", ["Todas"] + areas_audit, key="audit_area"
        )

    if busqueda_nhc_audit and not is_valid_nhc(busqueda_nhc_audit):
        st.info("Introduce las 6 cifras del NHC, incluidos los ceros iniciales.")
        rows = []
    else:
        _, rows = get_table(
            conn,
            "audit",
            priority=audit_pr_filter,
            eligible_only=(audit_elig_filter == "Solo elegibles"),
            specialty=audit_sp_filter,
            subspecialty=audit_ss_filter,
            patient_id=busqueda_nhc_audit or None,
            ai_consent=opciones_consentimiento_audit[consentimiento_audit],
            limit=400,
        )

    motivos_alta = {
        "FIN_TRATAMIENTO": "Fin del tratamiento",
        "NO_ASISTE": "No asiste",
        "DERIVADO": "Derivado",
        "OTRO": "Otro",
    }
    data = []
    for fila in rows:
        fecha = fila[13]
        data.append(
            {
                "NHC": fila[2],
                "Fecha": fecha.isoformat(sep=" ", timespec="minutes")
                if hasattr(fecha, "isoformat")
                else str(fecha or "—"),
                "Evento": audit_event_label(fila[1]),
                "Especialidad": fila[3] or "No aplica",
                "Área": fila[4] or "—",
                "Sesiones realizadas al alta": fila[15]
                if fila[1] == "ALTA_TRATAMIENTO"
                else None,
                "Revisiones al alta": fila[16]
                if fila[1] == "ALTA_TRATAMIENTO"
                else None,
                "Motivo": motivos_alta.get(
                    fila[10], (fila[10] or "").replace("_", " ").capitalize()
                ),
                "Observaciones": fila[11] or "",
                "Registrado por": fila[12] or "",
            }
        )
    st.caption(
        "Las sesiones se muestran en el alta de cada tratamiento. Las faltas no cuentan como sesiones realizadas; las revisiones se muestran por separado. La fecha incluye su zona horaria."
    )
    if data:
        st.dataframe(data, width="stretch", hide_index=True)
    else:
        st.info("No hay eventos de auditoría con los filtros seleccionados.")

elif page == "📖 Registro de visitas":
    if rol_usuario != "ADMIN":
        st.error("Solo el administrador puede consultar el registro de visitas.")
        st.stop()
    st.subheader("Registro de visitas a historias clínicas")
    st.caption(
        "Una fila por DNI del clínico, NHC y día de acceso. Las fechas corresponden a Europe/Madrid; no se guarda la hora. Solo se registran consultas individuales de historias, no listados generales."
    )
    filtro_nhc = st.text_input("Filtrar por NHC", max_chars=6, key="visits_nhc").strip()
    filtro_dni = (
        st.text_input("Filtrar por DNI del clínico", max_chars=9, key="visits_dni")
        .strip()
        .upper()
    )
    if filtro_nhc and not is_valid_nhc(filtro_nhc):
        st.info("Introduce las 6 cifras del NHC.")
    else:
        _, visitas = get_clinical_visits(
            conn, patient_id=filtro_nhc or None, clinician_dni=filtro_dni or None
        )
        datos_visitas = [
            {
                "DNI del clínico": fila[0],
                "NHC consultado": fila[1],
                "Fecha": str(fila[2]),
            }
            for fila in visitas
        ]
        if datos_visitas:
            st.dataframe(datos_visitas, width="stretch", hide_index=True)
        else:
            st.info("No hay visitas registradas con esos filtros.")

elif page == "⚙️ Ajustes":
    if rol_usuario != "ADMIN":
        st.error("No tienes permisos para acceder a Ajustes.")
        st.stop()

    st.subheader("⚙️ Ajustes del sistema")

    temporary = st.session_state.get("temporary_user_password")
    if temporary:
        st.warning(
            f"Contraseña temporal de {temporary['username']}. Entrégala por un canal privado."
        )
        st.code(temporary["password"], language=None)
        if st.button("Ocultar contraseña temporal", key="hide_temp_password"):
            st.session_state.pop("temporary_user_password", None)
            st.rerun()

    st.markdown("### Restablecer contraseña de usuario")

    usuarios_reset = get_all_users(conn)
    usuarios_reset_options = {
        f"{u[0]} · {u[1]} · {u[2]} · {u[3]} · {u[4]} · {u[5]}": u[0]
        for u in usuarios_reset
        if u[0] != usuario_actual["id"]
    }

    if usuarios_reset_options:
        selected_user_reset = st.selectbox(
            "Selecciona el usuario al que quieres restablecer la contraseña",
            list(usuarios_reset_options.keys()),
            key="reset_user_select",
        )

        confirm_reset_password = st.checkbox(
            "Confirmo que quiero generar una nueva contraseña temporal",
            key="confirm_reset_password",
        )

        if st.button("Restablecer contraseña", key="reset_password_button"):
            if rol_usuario != "ADMIN":
                st.error("Solo el administrador puede restablecer contraseñas.")
            elif not confirm_reset_password:
                st.error("Debes confirmar el restablecimiento.")
            else:
                reset_user_password_to_default(
                    conn, usuarios_reset_options[selected_user_reset]
                )
                st.success(
                    "Contraseña temporal generada. "
                    "En el próximo acceso se obligará al usuario a cambiarla."
                )
                st.rerun()
    else:
        st.info("No hay usuarios disponibles para restablecer contraseña.")

    st.markdown("### Corrección de errores de registro")

    with st.expander("🚫 Eliminar solicitud de lista de espera"):
        _, waitlist_rows = get_table(conn, "admin_waitlist", limit=300)

        if not waitlist_rows:
            st.info("No hay solicitudes en lista de espera.")
        else:
            waitlist_options = {
                f"{r[0]} · NHC {r[1]} · {specialty_label(r[2], r[3])} · {r[4]} · {str(r[5])[:10]}": r[
                    0
                ]
                for r in waitlist_rows
            }

            selected_waitlist = st.selectbox(
                "Selecciona la solicitud a eliminar",
                list(waitlist_options.keys()),
                key="admin_delete_waitlist_pick",
            )

            confirm_delete_waitlist = st.checkbox(
                "Confirmo que quiero eliminar esta solicitud",
                key="admin_confirm_delete_waitlist",
            )

            if st.button("Eliminar solicitud", key="admin_delete_waitlist_button"):
                if rol_usuario != "ADMIN":
                    st.error("Solo el administrador puede eliminar solicitudes.")
                elif not confirm_delete_waitlist:
                    st.error("Debes confirmar la eliminación.")
                else:
                    ok, msg = delete_waitlist_entry(
                        conn, waitlist_options[selected_waitlist], actor_sidebar
                    )
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with st.expander("⛔ Eliminar tratamiento activo"):
        _, active_rows = get_table(conn, "admin_active", limit=300)

        if not active_rows:
            st.info("No hay tratamientos activos.")
        else:
            active_options = {
                f"{r[0]} · NHC {r[1]} · {specialty_label(r[2], r[3])} · inicio {str(r[4])[:10]}": r[
                    0
                ]
                for r in active_rows
            }

            selected_active = st.selectbox(
                "Selecciona el tratamiento activo a eliminar",
                list(active_options.keys()),
                key="admin_delete_active_pick",
            )

            confirm_delete_active = st.checkbox(
                "Confirmo que quiero eliminar este tratamiento y sus sesiones",
                key="admin_confirm_delete_active",
            )

            if st.button("Eliminar tratamiento", key="admin_delete_active_button"):
                if rol_usuario != "ADMIN":
                    st.error("Solo el administrador puede eliminar tratamientos.")
                elif not confirm_delete_active:
                    st.error("Debes confirmar la eliminación.")
                else:
                    ok, msg = delete_active_treatment(
                        conn, active_options[selected_active], actor_sidebar
                    )
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    st.markdown("### Usuarios del sistema")

    with st.expander("💉 Registrar nuevo usuario"):
        u1, u2 = st.columns(2)
        with u1:
            new_full_name = st.text_input("Nombre completo", key="new_user_full_name")
            new_dni = st.text_input("DNI", key="new_user_dni").strip().upper()
            st.caption("El DNI será el nombre de usuario para iniciar sesión.")
        with u2:
            new_profession = st.selectbox(
                "Profesión",
                [row[0] for row in get_professions(conn)],
                key="new_user_profession",
            )
            new_role = "ADMIN" if new_profession == "Administrador" else "CLINICO"
            st.text_input(
                "Rol",
                value="Administrador" if new_role == "ADMIN" else "Clínico",
                disabled=True,
            )
            st.caption("Se generará una contraseña temporal única al crear el usuario.")

        if st.button("Registrar usuario", key="create_user_button"):
            if rol_usuario != "ADMIN":
                st.error("Solo el administrador puede registrar usuarios.")

            elif not new_full_name.strip():
                st.error("Introduce el nombre completo.")

            elif not is_valid_dni(new_dni):
                st.error("El DNI no es válido.")

            else:
                _, dni_existente = get_table(conn, "user_dni", dni=new_dni)

                if dni_existente:
                    st.error("Ya existe un usuario registrado con ese DNI.")

                else:
                    creado = create_user(
                        conn=conn,
                        username=new_dni,
                        full_name=new_full_name.strip(),
                        dni=new_dni,
                        profession=new_profession,
                        role=new_role,
                    )
                    if creado:
                        st.success("Usuario registrado correctamente.")
                        st.rerun()
                    else:
                        st.error("Ya existe ese nombre de usuario o DNI.")

    st.markdown("### Listado de usuarios")
    usuarios = get_all_users(conn)
    data_users = []
    for u in usuarios:
        data_users.append(
            {
                "id": u[0],
                "usuario": u[1],
                "nombre": u[2],
                "dni": u[3],
                "profesión": u[4],
                "rol": u[5],
                "cambio_clave_pendiente": "Sí" if u[6] else "No",
                "activo": "Sí" if u[7] else "No",
                "creado": str(u[8])[:19],
            }
        )
    st.dataframe(data_users, width="stretch", hide_index=True)

    tab1, tab2, tab3 = st.tabs(["Especialidades", "Áreas", "Listado actual"])

    with tab1:
        st.markdown("### Añadir nueva especialidad")
        n1, n2 = st.columns([2, 1])
        with n1:
            nueva_especialidad = st.text_input(
                "Nombre de la especialidad",
                placeholder="Ej: Rehabilitación vestibular",
                key="cfg_new_specialty",
            ).strip()
        with n2:
            requiere_area = st.checkbox(
                "Requiere área", value=False, key="cfg_requires_subspecialty"
            )

        if st.button("Guardar especialidad", key="cfg_save_specialty", width="stretch"):
            if not nueva_especialidad:
                st.error("Introduce el nombre de la especialidad.")
            else:
                add_specialty_config(conn, nueva_especialidad, requiere_area)
                st.success("Especialidad guardada.")
                st.rerun()

        st.markdown("### Activar o desactivar especialidades")
        especialidades_todas = get_especialidades(conn, only_active=False)
        if especialidades_todas:
            for nombre, req_sub, active in especialidades_todas:
                c1, c2, c3 = st.columns([2.5, 1.2, 1])
                with c1:
                    st.write(f"**{nombre}**")
                with c2:
                    st.write("Con áreas" if req_sub else "Sin áreas")
                with c3:
                    nuevo_estado = st.toggle(
                        "Activa",
                        value=active,
                        key=f"toggle_specialty_{nombre}",
                        label_visibility="collapsed",
                    )
                    if nuevo_estado != active:
                        set_specialty_active(conn, nombre, nuevo_estado)
                        st.rerun()

    with tab2:
        st.markdown("### Añadir nueva área")
        especialidades_con_area = [
            n for n, req, _ in get_especialidades(conn, only_active=False) if req
        ]

        if not especialidades_con_area:
            st.info("No hay especialidades configuradas que requieran áreas.")
        else:
            a1, a2 = st.columns([1.5, 2])
            with a1:
                especialidad_destino = st.selectbox(
                    "Especialidad", especialidades_con_area, key="cfg_area_specialty"
                )
            with a2:
                nueva_area = st.text_input(
                    "Nombre del área",
                    placeholder="Ej: Dolor crónico",
                    key="cfg_new_area",
                ).strip()

            if st.button("Guardar área", key="cfg_save_area", width="stretch"):
                if not nueva_area:
                    st.error("Introduce el nombre del área.")
                else:
                    add_subspecialty_config(conn, especialidad_destino, nueva_area)
                    st.success("Área guardada.")
                    st.rerun()

        st.markdown("### Activar o desactivar áreas")

        _, areas_configuradas = get_table(conn, "areas")

        for especialidad, area, activa in areas_configuradas:
            col_nombre, col_estado = st.columns([3, 1])

            with col_nombre:
                st.write(f"**{especialidad} — {area}**")

            with col_estado:
                nuevo_estado = st.toggle(
                    "Activa",
                    value=activa,
                    key=f"toggle_area_{especialidad}_{area}",
                    label_visibility="collapsed",
                )

                if nuevo_estado != activa:
                    set_subspecialty_active(
                        conn,
                        especialidad,
                        area,
                        nuevo_estado,
                    )
                    st.rerun()

    with tab3:
        st.markdown("### Especialidades")
        rows = get_especialidades(conn, only_active=False)
        data = []
        for nombre, req_sub, active in rows:
            data.append(
                {
                    "especialidad": nombre,
                    "requiere_area": "Sí" if req_sub else "No",
                    "activa": "Sí" if active else "No",
                }
            )
        st.dataframe(data, width="stretch", hide_index=True)

        st.markdown("### Áreas")
        _, rows_areas = get_table(conn, "areas")
        data_areas = []
        for specialty_name, name, active in rows_areas:
            data_areas.append(
                {
                    "especialidad": specialty_name,
                    "área": name,
                    "activa": "Sí" if active else "No",
                }
            )
        st.dataframe(data_areas, width="stretch", hide_index=True)

    st.markdown("### Configuración de profesiones")
    with st.expander("Añadir nueva profesión clínica y gestionar profesiones"):
        nueva_profesion = st.text_input(
            "Nueva profesión clínica", key="cfg_new_profession"
        )
        st.caption(
            "Las nuevas profesiones tendrán rol Clínico. Solo Administrador tendrá rol administrativo."
        )
        if st.button("Añadir profesión clínica", key="cfg_add_profession"):
            if not nueva_profesion.strip():
                st.error("Introduce el nombre de la profesión.")
            else:
                add_profession_config(conn, nueva_profesion)
                st.rerun()
        for nombre_profesion, activa in get_professions(conn, only_active=False):
            nuevo_estado = st.toggle(
                nombre_profesion,
                value=activa,
                key=f"cfg_profession_{nombre_profesion}",
                disabled=nombre_profesion == "Administrador",
            )
            if nuevo_estado != activa:
                set_profession_active(conn, nombre_profesion, nuevo_estado)
                st.rerun()
        st.caption("Desactivar una profesión no modifica los usuarios existentes.")
