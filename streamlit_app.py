import os
import requests
import streamlit as st

API_URL = os.getenv("MICROMEGA_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Micromega Inmobiliaria", layout="wide")
st.title("Micromega Inmobiliaria · V0")
st.caption("Simulador y panel interno. Las propiedades incluidas son ficticias y sólo sirven para probar el flujo.")

chat_tab, props_tab, leads_tab = st.tabs(["Simulador", "Propiedades", "Leads"])

with chat_tab:
    col1, col2 = st.columns([1, 2])
    with col1:
        phone = st.text_input("Teléfono demo", "+5491100000000")
        name = st.text_input("Nombre", "Cliente demo")
    with col2:
        text = st.text_area("Mensaje", "Busco alquilar 2 o 3 ambientes en Caballito hasta 800 mil. Tengo un perro.")
        if st.button("Enviar al motor"):
            r = requests.post(f"{API_URL}/api/simulator/message", json={"phone": phone, "name": name, "text": text}, timeout=20)
            if r.ok:
                data = r.json()
                st.subheader("Respuesta")
                st.write(data.get("reply"))
                st.subheader("Datos estructurados detectados")
                st.json(data.get("profile", {}))
            else:
                st.error(r.text)

with props_tab:
    try:
        rows = requests.get(f"{API_URL}/api/properties", timeout=10).json()
        st.dataframe(rows, use_container_width=True)
    except Exception as exc:
        st.error(f"No se pudo consultar la API: {exc}")

with leads_tab:
    try:
        rows = requests.get(f"{API_URL}/api/admin/leads", timeout=10).json()
        st.dataframe(rows, use_container_width=True)
    except Exception as exc:
        st.error(f"No se pudo consultar la API: {exc}")
