import streamlit as st

st.set_page_config(
    page_title="Gestión de Rehabilitación",
    page_icon="🏥",
    layout="wide"
)

st.title("🏥 Gestión de Rehabilitación")

st.write(
    "Aplicación para la gestión y seguimiento "
    "de pacientes del servicio de rehabilitación."
)

st.sidebar.header("Menú")

opcion = st.sidebar.radio(
    "Selecciona una opción:",
    [
        "Inicio",
        "Pacientes",
        "Tratamientos",
        "Seguimiento"
    ]
)

if opcion == "Inicio":

    st.header("Panel principal")

    st.write(
        "Bienvenido a la aplicación de gestión "
        "del servicio de rehabilitación."
    )

elif opcion == "Pacientes":

    st.header("👥 Pacientes")

    st.info(
        "El módulo de gestión de pacientes "
        "se incorporará durante el desarrollo."
    )

elif opcion == "Tratamientos":

    st.header("⚕️ Tratamientos")

    st.info(
        "El módulo de tratamientos "
        "se incorporará durante el desarrollo."
    )

elif opcion == "Seguimiento":

    st.header("📈 Seguimiento")

    st.info(
        "El módulo de seguimiento "
        "se incorporará durante el desarrollo."
    )