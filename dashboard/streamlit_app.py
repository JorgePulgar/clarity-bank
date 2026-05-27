"""Dashboard de demostracion ClarityBank (Streamlit).

Tres pantallas: transaccion individual, importar lote, insights mensuales.
Habla con la API por HTTP (no toca la BD directamente) para reflejar el flujo real.

Arrancar (con la API ya levantada):
    streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("CLARITY_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="ClarityBank Demo", page_icon="*", layout="wide")
st.title("ClarityBank - Demo")

# Estado de la API en la barra lateral.
with st.sidebar:
    st.header("Conexion")
    st.caption(f"API: {API_URL}")
    try:
        h = requests.get(f"{API_URL}/health", timeout=3).json()
        st.success("API conectada")
        st.json(h)
    except Exception as e:
        st.error(f"API no disponible: {e}")
    st.divider()
    user_id = st.text_input("user_id", value="user_demo")
    st.divider()
    st.header("Panel de Coste")
    try:
        cs = requests.get(f"{API_URL}/users/{user_id}/cost-stats", timeout=3).json()
        c1, c2 = st.columns(2)
        c1.metric("Transacciones", cs["n_transactions"])
        c2.metric("Nivel 2 (LLM)", cs["n_llm_calls"])
        c3, c4 = st.columns(2)
        c3.metric("Insights", cs["n_insights"])
        c4.metric("Coste est. EUR", f"{cs['total_cost_eur']:.4f}")
    except Exception:
        st.caption("Sin datos de coste")

tab1, tab2, tab3 = st.tabs(["Transaccion individual", "Importar lote", "Insights"])


# --- Pantalla 1: transaccion individual -----------------------------------
with tab1:
    st.subheader("Clasificar una transaccion")
    with st.form("tx_form"):
        desc = st.text_input("Descripcion", "PAGO TARJETA MERCADONA SL MADRID")
        amount = st.number_input("Importe (EUR)", value=-43.27, step=1.0,
                                  help="Negativo = gasto, positivo = ingreso")
        submitted = st.form_submit_button("Enviar")
    if submitted:
        try:
            r = requests.post(
                f"{API_URL}/transactions",
                json={"user_id": user_id, "description": desc, "amount": amount},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            c1, c2, c3 = st.columns(3)
            c1.metric("Categoria", data["category"])
            c2.metric("Confianza", f"{data['confidence']:.0%}")
            c3.metric("Nivel", f"L{data['classification_level']}")
            st.caption(f"Anonimizado: {data['description_anonymized']}")
            if data["is_anomaly"]:
                st.warning(f"Anomalia: {data['anomaly_reason']}")
            else:
                st.info("Sin anomalias.")
        except Exception as e:
            st.error(f"Error: {e}")


# --- Pantalla 2: importar lote --------------------------------------------
with tab2:
    st.subheader("Importar CSV o JSON")
    st.caption("CSV con cabeceras: user_id, description, amount, [date]")
    up = st.file_uploader("Fichero", type=["csv", "json"])
    if up is not None and st.button("Procesar lote"):
        try:
            r = requests.post(
                f"{API_URL}/transactions/import",
                files={"file": (up.name, up.getvalue())},
                timeout=60,
            )
            r.raise_for_status()
            res = r.json()
            c1, c2, c3 = st.columns(3)
            c1.metric("Recibidas", res["received"])
            c2.metric("Procesadas", res["processed"])
            c3.metric("Anomalias", res["anomalies"])
            if res["errors"]:
                st.warning("Errores:")
                st.write(res["errors"])
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    st.subheader(f"Estadisticas de {user_id}")
    if st.button("Actualizar stats"):
        try:
            s = requests.get(f"{API_URL}/users/{user_id}/stats", timeout=10).json()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Transacciones", s["n_transactions"])
            c2.metric("Gastos", f"{s['total_gastos']:.2f}")
            c3.metric("Ingresos", f"{s['total_ingresos']:.2f}")
            c4.metric("Anomalias", s["n_anomalies"])
            if s["by_category"]:
                df = pd.DataFrame(s["by_category"])
                st.bar_chart(df.set_index("category")["total"])
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")


# --- Pantalla 3: insights --------------------------------------------------
with tab3:
    st.subheader("Insight mensual")
    month = st.text_input("Mes (YYYY-MM)", "2026-04")
    if st.button("Generar insight"):
        try:
            r = requests.post(
                f"{API_URL}/insights/generate",
                json={"user_id": user_id, "month": month},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            st.write(data["text"])
            st.caption(f"Fuente: {data['source']} - {data['n_transactions']} transacciones")
        except Exception as e:
            st.error(f"Error: {e}")
