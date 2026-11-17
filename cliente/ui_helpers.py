"""Presentación de estados, fechas y calendarios de las sesiones."""

import calendar
from collections import defaultdict
import streamlit as st
from cliente.api_client import get_table
from comun.medidas_rodilla import (
    INSTRUCCIONES_KOOS_JR, MEDIDAS, MEDIDAS_OBJETIVO, puntuacion_koos_jr,
)


def mostrar_informe_texto(etiqueta, texto, *, altura):
    """Vincula el contenido visible al informe actual, incluso al cambiar de tratamiento."""
    st.text_area(etiqueta, value=texto, height=altura, disabled=True)


def campos_seguimiento_rodilla(rehab_id):
    """Recoge las medidas que el profesional haya tomado en esta sesión."""
    if st.session_state.pop(f"knee_clear_{rehab_id}", False):
        for campo in ("on", "flexion", "extension", "tug", "tug_conditions", "koos", "goal_metric"):
            st.session_state.pop(f"knee_{campo}_{rehab_id}", None)
        for medida in MEDIDAS_OBJETIVO:
            st.session_state.pop(f"knee_goal_target_{rehab_id}_{medida}", None)

    with st.expander("Medidas y objetivo de rodilla"):
        st.caption("Usa este bloque para seguir la misma rodilla a lo largo del tratamiento.")
        if not st.checkbox("Registrar medidas u objetivo de rodilla", key=f"knee_on_{rehab_id}"):
            return {}

        c1, c2 = st.columns(2)
        flexion = c1.number_input(
            "Flexión (°)", 0.0, 180.0, value=None, step=1.0, key=f"knee_flexion_{rehab_id}",
        )
        deficit = c2.number_input(
            "Déficit de extensión (°)", 0.0, 180.0, value=None, step=1.0,
            help="Registra 0 si llega a la extensión completa y un valor positivo si faltan grados.",
            key=f"knee_extension_{rehab_id}",
        )
        tug = c1.number_input(
            "Timed Up and Go (s)", min_value=0.01, value=None, step=0.1,
            key=f"knee_tug_{rehab_id}",
        )
        condiciones = None
        if tug is not None:
            condiciones = c2.text_input(
                "Condiciones del TUG", max_chars=100,
                placeholder="Ej. Sin ayuda, o bastón",
                help="Usa la misma descripción para pruebas comparables.",
                key=f"knee_tug_conditions_{rehab_id}",
            ).strip() or None

        koos = st.number_input(
            "KOOS, JR · suma de los siete ítems (0–28)", 0, 28, value=None, step=1,
            help="Introduce la suma del cuestionario completo solo en las sesiones en que se haya aplicado.",
            key=f"knee_koos_{rehab_id}",
        )
        st.caption(f"[Instrucciones de puntuación del KOOS, JR]({INSTRUCCIONES_KOOS_JR})")
        if koos is not None:
            st.caption(f"Puntuación convertida: {puntuacion_koos_jr(koos):.3f} / 100")

        meta_medida = st.selectbox(
            "Fijar o actualizar el objetivo de movilidad",
            MEDIDAS_OBJETIVO, index=None, placeholder="Mantener el objetivo actual",
            format_func=lambda clave: MEDIDAS[clave][0], key=f"knee_goal_metric_{rehab_id}",
        )
        meta = None
        if meta_medida is not None:
            etiqueta = "Flexión mínima (°)" if meta_medida == "knee_flexion_deg" else "Déficit máximo (°)"
            meta = st.number_input(
                etiqueta, 0.0, 180.0, value=None, step=1.0,
                key=f"knee_goal_target_{rehab_id}_{meta_medida}",
            )
        return {
            "knee_flexion_deg": flexion,
            "knee_extension_deficit_deg": deficit,
            "tug_seconds": tug,
            "tug_conditions": condiciones,
            "koos_jr_raw": koos,
            "knee_goal_metric": meta_medida,
            "knee_goal_target": meta,
        }


def mostrar_evolucion_rodilla(seguimiento):
    if not seguimiento or not (
        any(seguimiento["series"].values()) or seguimiento["objetivo"]
    ):
        return
    st.markdown("#### Evolución de rodilla")
    if seguimiento["objetivo"]:
        st.write(seguimiento["objetivo_descripcion"])

    series = [(medida, puntos) for medida, puntos in seguimiento["series"].items() if puntos]
    if not series:
        return
    import altair as alt

    for (medida, puntos), columna in zip(series, st.columns(2) * 2):
        nombre, unidad = MEDIDAS[medida]
        with columna:
            st.markdown(f"**{nombre} ({unidad})**")
            datos_grafica = [
                {
                    "Fecha": punto["fecha"],
                    "Valor": punto["valor"],
                    **({"Condiciones": punto["condiciones"].casefold()} if medida == "tug_seconds" else {}),
                }
                for punto in puntos
            ]
            es_tug = medida == "tug_seconds"
            detalle = ["Fecha:T", "Valor:Q"]
            if es_tug:
                detalle.append("Condiciones:N")
            grafica = alt.Chart(alt.InlineData(values=datos_grafica)).mark_line(point=True).encode(
                x=alt.X("Fecha:T", title="Fecha de sesión"),
                y=alt.Y("Valor:Q", title=unidad),
                tooltip=detalle,
            )
            if es_tug:
                grafica = grafica.encode(color="Condiciones:N")
            st.altair_chart(grafica.properties(height=225), width="stretch")


def priority_badge(p: str) -> str:
    if p == "personal SACYL":
        return "🟣 personal SACYL"
    if p == "urgente":
        return "🔴 urgente"
    if p == "preferente":
        return "🟠 preferente"
    return "🟢 ordinario"


def specialty_label(specialty: str, subspecialty: str | None) -> str:
    if subspecialty:
        return f"{specialty} · {subspecialty}"
    return specialty


def estado_sesion_label(status: str) -> str:
    if status == "REALIZADA":
        return "Realizada"
    if status == "REVISION":
        return "Revisión"
    if status == "FALTA_JUSTIFICADA":
        return "Falta justificada"
    if status == "FALTA_NO_JUSTIFICADA":
        return "Falta no justificada"
    return status


def dia_semana_espanol(fecha):
    dias = {
        0: "Lunes",
        1: "Martes",
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo",
    }
    return dias[fecha.weekday()]


def parse_attendance_days(attendance_days_text: str) -> list[str]:
    if not attendance_days_text:
        return []
    return [d.strip() for d in attendance_days_text.split(",") if d.strip()]


def render_mini_calendar(conn, rehab_active_id: int, year: int, month: int):
    _, rows = get_table(
        conn, "calendar", rehab_active_id=rehab_active_id, year=year, month=month
    )

    sesiones_por_dia = defaultdict(list)
    for session_date, status in rows:
        sesiones_por_dia[session_date.day].append(status)

    colores = {
        "REALIZADA": "#4CAF50",
        "REVISION": "#2196F3",
        "FALTA_JUSTIFICADA": "#FFC107",
        "FALTA_NO_JUSTIFICADA": "#F44336",
    }

    cal = calendar.Calendar(firstweekday=0)
    semanas = cal.monthdayscalendar(year, month)
    nombres_dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    html = """
    <style>
    .mini-calendario {
        width: 100%;
        max-width: 520px;
        border-collapse: collapse;
        margin-top: 0.5rem;
        font-size: 0.9rem;
    }
    .mini-calendario th, .mini-calendario td {
        border: 1px solid #ddd;
        width: 14.2%;
        height: 72px;
        vertical-align: top;
        padding: 4px;
        background: white;
    }
    .mini-cal-dia {
        font-weight: 700;
        margin-bottom: 4px;
    }
    .mini-cal-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin: 2px 3px 0 0;
    }
    .mini-cal-vacio {
        background: #f7f7f7;
    }
    .leyenda {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin: 0.5rem 0 0.8rem 0;
        font-size: 0.9rem;
    }
    .leyenda-item {
        display: flex;
        align-items: center;
        gap: 6px;
    }
    </style>
    """

    html += '<div class="leyenda">'
    html += f'<div class="leyenda-item"><span class="mini-cal-dot" style="background:{colores["REALIZADA"]};"></span>Realizada</div>'
    html += f'<div class="leyenda-item"><span class="mini-cal-dot" style="background:{colores["REVISION"]};"></span>Revisión</div>'
    html += f'<div class="leyenda-item"><span class="mini-cal-dot" style="background:{colores["FALTA_JUSTIFICADA"]};"></span>Falta justificada</div>'
    html += f'<div class="leyenda-item"><span class="mini-cal-dot" style="background:{colores["FALTA_NO_JUSTIFICADA"]};"></span>Falta no justificada</div>'
    html += "</div>"

    html += '<table class="mini-calendario">'
    html += "<tr>" + "".join(f"<th>{d}</th>" for d in nombres_dias) + "</tr>"

    for semana in semanas:
        html += "<tr>"
        for dia in semana:
            if dia == 0:
                html += '<td class="mini-cal-vacio"></td>'
            else:
                html += f'<td><div class="mini-cal-dia">{dia}</div>'
                estados = sesiones_por_dia.get(dia, [])
                for estado in estados:
                    color = colores.get(estado, "#999999")
                    html += f'<span class="mini-cal-dot" style="background:{color};" title="{estado_sesion_label(estado)}"></span>'
                html += "</td>"
        html += "</tr>"

    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)


def audit_event_label(event):
    return {
        "CREACION_SOLICITUD": "Solicita tratamiento",
        "ASIGNACION_AUTOMATICA": "Comienza el tratamiento",
        "ALTA_TRATAMIENTO": "Alta del tratamiento",
        "REGISTRO_SESION": "Registro de sesión",
        "MODIFICACION_SESION": "Modificación de sesión",
        "ELIMINACION_SESION": "Eliminación de sesión",
        "ELIMINACION_ADMIN_LISTA_ESPERA": "Eliminación administrativa de solicitud",
        "ELIMINACION_ADMIN_TRATAMIENTO": "Eliminación administrativa de tratamiento",
        "DESACTIVACION_ADMIN_TRATAMIENTO": "Desactivación administrativa de tratamiento",
        "CONSENTIMIENTO_IA": "Decisión sobre el uso de IA",
        "GENERACION_RESUMEN_IA": "Generación de resumen con IA",
    }.get(event, (event or "Evento sin identificar").replace("_", " ").capitalize())
