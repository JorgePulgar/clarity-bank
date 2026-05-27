"""Dashboard de demostracion ClarityBank (Streamlit).

Tres pantallas: transaccion individual, importar lote, insights mensuales.
Habla con la API por HTTP (no toca la BD directamente) para reflejar el flujo real.

Arrancar (con la API ya levantada):
    streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import os
import time

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
    st.caption("Introduce un movimiento bancario para ver como lo clasifica el sistema.")
    with st.form("tx_form"):
        desc = st.text_input("Descripcion del movimiento", "PAGO TARJETA MERCADONA SL MADRID")
        amount = st.number_input(
            "Importe (EUR)", value=-43.27, step=1.0,
            help="Negativo = gasto, positivo = ingreso",
        )
        submitted = st.form_submit_button("Clasificar", type="primary")

    if submitted:
        t0 = time.time()
        try:
            r = requests.post(
                f"{API_URL}/transactions",
                json={"user_id": user_id, "description": desc, "amount": amount},
                timeout=10,
            )
            latencia_ms = int((time.time() - t0) * 1000)
            r.raise_for_status()
            data = r.json()

            # Cards de resultado
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Categoria", data["category"].capitalize())
            confianza = data["confidence"]
            c2.metric("Confianza", f"{confianza:.0%}")
            nivel_txt = "L1 — Local" if data["classification_level"] == 1 else "L2 — LLM"
            c3.metric("Nivel usado", nivel_txt)
            c4.metric("Latencia", f"{latencia_ms} ms")

            st.progress(confianza, text=f"Confianza del clasificador: {confianza:.0%}")

            # Flag de anomalia
            if data["is_anomaly"]:
                st.error(f"Anomalia detectada: {data['anomaly_reason']}")
            else:
                st.success("Sin anomalias detectadas")

            # Descripcion original vs anonimizada lado a lado
            st.divider()
            col_orig, col_anon = st.columns(2)
            with col_orig:
                st.caption("Descripcion original")
                st.code(data.get("description_raw") or desc, language=None)
            with col_anon:
                st.caption("Descripcion anonimizada (lo que ve el clasificador)")
                st.code(data.get("description_anonymized") or desc, language=None)

        except Exception as e:
            st.error(f"Error al clasificar: {e}")


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
