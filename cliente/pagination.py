"""Controles compartidos para recorrer los listados sin descargarlos completos."""

import json

import streamlit as st

from cliente.api_client import get_table_page


def _move_page(state_key, difference):
    st.session_state[state_key] = max(
        1, st.session_state.get(state_key, 1) + difference
    )


def paginated_table(conn, name, key, **filters):
    """Mantiene cada listado independiente y vuelve al inicio al cambiar sus filtros."""
    size = st.selectbox(
        "Registros por página", [25, 50, 100], index=1, key=f"{key}_size"
    )
    state_key = f"{key}_page"
    fingerprint = json.dumps([name, filters, size], sort_keys=True, default=str)
    if st.session_state.get(f"{key}_filters") != fingerprint:
        st.session_state[state_key] = 1
        st.session_state[f"{key}_filters"] = fingerprint
    result = get_table_page(
        conn, name, page=st.session_state.get(state_key, 1), page_size=size, **filters
    )
    st.session_state[state_key] = result["page"]
    previous, label, following = st.columns([1, 2, 1])
    previous.button(
        "Anterior",
        key=f"{key}_previous",
        disabled=result["page"] <= 1,
        on_click=_move_page,
        args=(state_key, -1),
    )
    label.caption(
        f"Página {result['page']} de {result['total_pages']} · {result['total']} registros"
    )
    following.button(
        "Siguiente",
        key=f"{key}_next",
        disabled=result["page"] >= result["total_pages"],
        on_click=_move_page,
        args=(state_key, 1),
    )
    return result["columns"], result["rows"]
