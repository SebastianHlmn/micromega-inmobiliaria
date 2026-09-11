import os
import requests
import streamlit as st

API_URL = os.getenv("MICROMEGA_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Micromega Inmobiliaria", layout="wide")
st.title("Micromega Inmobiliaria · V0")
st.caption("Simulador y panel interno. Las propiedades incluidas son ficticias y sólo sirven para probar el flujo.")

chat_tab, wa_tab, props_tab, leads_tab = st.tabs(["Simulador", "WhatsApp", "Propiedades", "Leads"])

with chat_tab:
    col1, col2 = st.columns([1, 2])
    with col1:
        phone = st.text_input("Teléfono demo", "+5491100000000")
        name = st.text_input("Nombre", "Cliente demo")
    with col2:
        text = st.text_area("Mensaje", "Busco alquilar 2 o 3 ambientes en Caballito hasta 800 mil. Tengo un perro.")
        if st.button("Enviar al motor"):
            r = requests.post(f"{API_URL}/api/simulator/message", json={"phone": phone, "name": name, "text": text}, timeout=30)
            if r.ok:
                data = r.json()
                st.subheader("Respuesta")
                st.write(data.get("reply"))

                extraction = data.get("extraction", {})
                source = extraction.get("source", "desconocida")
                st.caption(f"Fuente de interpretación: {source}")

                col_profile, col_current = st.columns(2)
                with col_profile:
                    st.subheader("Perfil acumulado")
                    st.json(data.get("profile", {}))
                with col_current:
                    st.subheader("Detectado en este mensaje")
                    st.json(extraction.get("fields_from_current_message", {}))
            else:
                st.error(r.text)

with wa_tab:
    st.subheader("Prueba GPT → WhatsApp")
    st.caption(
        "Este puente de desarrollo procesa el mensaje con el mismo motor conversacional y envía la respuesta al WhatsApp indicado. "
        "Sirve para validar GPT + Micromega + salida real por WhatsApp mientras Meta todavía no entrega mensajes reales a una app sin publicar."
    )

    try:
        status_response = requests.get(f"{API_URL}/api/admin/whatsapp/status", timeout=10)
        if status_response.ok:
            status = status_response.json()
            c1, c2, c3 = st.columns(3)
            c1.metric("LLM", status.get("llm_provider", "-"))
            c2.metric("Modelo", status.get("openai_model", "-"))
            wa_ready = status.get("whatsapp_access_token_configured") and status.get("whatsapp_phone_number_id_configured")
            c3.metric("WhatsApp", "configurado" if wa_ready else "faltan credenciales")
            if not status.get("openai_configured"):
                st.warning("OpenAI no está configurado en la API.")
            if not wa_ready:
                st.warning("Faltan WHATSAPP_ACCESS_TOKEN y/o WHATSAPP_PHONE_NUMBER_ID en el archivo .env.")
        else:
            st.warning("No se pudo leer el estado de WhatsApp. Reiniciá la API con el código actualizado.")
    except Exception as exc:
        st.warning(f"No se pudo consultar la API: {exc}")

    wa_phone = st.text_input(
        "WhatsApp destinatario",
        value="",
        placeholder="Ej.: 54911XXXXXXXX",
        help="Usá código de país + área + número. El sistema elimina espacios, + y guiones antes de enviar.",
    )
    wa_name = st.text_input("Nombre del contacto de prueba", value="Sebastián")
    wa_text = st.text_area(
        "Mensaje que simula el cliente",
        value="Busco alquilar un 2 ambientes en Caballito hasta 800 mil y tengo un perro.",
        key="wa_test_message",
    )

    if st.button("Procesar con GPT y enviarme la respuesta por WhatsApp", type="primary"):
        if not wa_phone.strip():
            st.error("Ingresá el número de WhatsApp destinatario.")
        else:
            try:
                r = requests.post(
                    f"{API_URL}/api/admin/whatsapp/test-chat",
                    json={"phone": wa_phone, "name": wa_name, "text": wa_text},
                    timeout=45,
                )
                if r.ok:
                    data = r.json()
                    st.success("Respuesta enviada por WhatsApp.")
                    st.write(data.get("reply"))
                    extraction = data.get("extraction", {})
                    st.caption(f"Fuente de interpretación: {extraction.get('source', 'desconocida')}")
                    st.json(data.get("profile", {}))
                else:
                    try:
                        detail = r.json().get("detail", r.text)
                    except Exception:
                        detail = r.text
                    st.error(detail)
            except Exception as exc:
                st.error(f"No se pudo completar la prueba: {exc}")

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
