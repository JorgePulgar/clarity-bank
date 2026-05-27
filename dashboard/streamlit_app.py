"""Dashboard de demostracion ClarityBank (Streamlit).

Tres pantallas: transaccion individual, importar lote, insights mensuales.
Habla con la API por HTTP (no toca la BD directamente) para reflejar el flujo real.

Arrancar (con la API ya levantada):
    streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

from __future__ import annotations

import csv
import io
import os
import random
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# Permite importar scripts/ aunque el dashboard se arranque desde cualquier directorio.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.generate_history import generate as _gen_historico  # noqa: E402

API_URL = os.environ.get("CLARITY_API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="ClarityBank — Categorizacion de transacciones",
    page_icon=":bank:",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("ClarityBank — Categorizacion inteligente de transacciones")
st.caption(
    "Prototipo TFM · Pipeline: anonimizacion RGPD → clasificacion → deteccion de anomalias → insights LLM"
)

# Sidebar global: conexion, usuario activo, metricas en vivo, reset
with st.sidebar:
    st.title("ClarityBank")
    st.caption(f"API: `{API_URL}`")

    # Estado de conexion
    api_ok = False
    try:
        h = requests.get(f"{API_URL}/health", timeout=2).json()
        api_ok = True
        modo = h.get("classifier_mode", "mock")
        st.success(f"API conectada — clasificador: {modo}")
    except Exception:
        st.error("API no disponible")

    st.divider()

    # Usuario activo
    st.subheader("Usuario activo")
    if "user_id" not in st.session_state:
        st.session_state["user_id"] = "demo-user"
    user_id = st.text_input("user_id", key="user_id")

    st.divider()

    # Metricas en vivo
    st.subheader("Metricas en vivo")
    if api_ok:
        try:
            cs = requests.get(f"{API_URL}/users/{user_id}/cost-stats", timeout=2).json()
            n_tx = cs["n_transactions"]
            n_llm = cs["n_llm_calls"]
            pct_llm = round(n_llm / n_tx * 100, 1) if n_tx > 0 else 0.0
            col1, col2 = st.columns(2)
            col1.metric("Transacciones", n_tx)
            col2.metric("Escaladas LLM", f"{pct_llm}%")
            col3, col4 = st.columns(2)
            col3.metric("Insights", cs["n_insights"])
            col4.metric("Coste acum.", f"€{cs['total_cost_eur']:.4f}")
        except Exception:
            st.caption("Sin datos para este usuario")
    else:
        st.caption("Sin conexion a la API")

    st.divider()

    # Reset demo
    if st.button("Reset demo", help="Limpia el estado de la sesion Streamlit (no borra la BD)"):
        uid = st.session_state.get("user_id", "demo-user")
        st.session_state.clear()
        st.session_state["user_id"] = uid
        st.rerun()

tab1, tab2, tab3 = st.tabs([
    "Transaccion individual",
    "Importar historico",
    "Insights mensuales",
])


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


# --- Pantalla 2: importar historico ---------------------------------------
with tab2:
    st.subheader("Importar transacciones")

    col_gen, col_up = st.columns([1, 1])

    # Generar historico simulado
    with col_gen:
        st.markdown("**Generar historico simulado**")
        st.caption("Crea un historico realista con gastos tipicos, nomina y outliers intencionados.")
        meses = st.slider("Meses de historico", 1, 12, 6, key="gen_meses")
        salario = st.number_input("Salario mensual (EUR)", value=2000.0, step=100.0, key="gen_salario")
        ciudad = st.text_input("Ciudad (para nombres de comercios)", "MADRID", key="gen_ciudad").upper()
        if st.button("Generar e importar historico", type="primary", key="btn_generar"):
            try:
                barra = st.progress(0, text="Generando transacciones...")
                random.seed(42)
                rows = _gen_historico(
                    user=user_id, months=meses, per_month=50,
                    salary=salario, ciudad=ciudad, n_suscripciones=3,
                )
                barra.progress(40, text=f"Generadas {len(rows)} transacciones. Importando...")
                buf = io.StringIO()
                w = csv.DictWriter(buf, fieldnames=["user_id", "description", "amount", "date"])
                w.writeheader()
                w.writerows(rows)
                r = requests.post(
                    f"{API_URL}/transactions/import",
                    files={"file": ("historico.csv", buf.getvalue().encode("utf-8"), "text/csv")},
                    timeout=120,
                )
                barra.progress(100, text="Importacion completada.")
                r.raise_for_status()
                res = r.json()
                c1, c2, c3 = st.columns(3)
                c1.metric("Recibidas", res["received"])
                c2.metric("Procesadas", res["processed"])
                c3.metric("Anomalias detectadas", res["anomalies"])
            except Exception as e:
                st.error(f"Error al generar/importar: {e}")

    # Subir CSV propio
    with col_up:
        st.markdown("**Subir CSV propio**")
        st.caption("Columnas: `user_id`, `description`, `amount`, `date` (opcional).")
        up = st.file_uploader("Fichero CSV o JSON", type=["csv", "json"], key="up_fichero")
        if up is not None and st.button("Importar fichero", key="btn_importar"):
            try:
                with st.spinner("Importando..."):
                    r = requests.post(
                        f"{API_URL}/transactions/import",
                        files={"file": (up.name, up.getvalue())},
                        timeout=120,
                    )
                r.raise_for_status()
                res = r.json()
                c1, c2, c3 = st.columns(3)
                c1.metric("Recibidas", res["received"])
                c2.metric("Procesadas", res["processed"])
                c3.metric("Anomalias detectadas", res["anomalies"])
                if res["errors"]:
                    st.warning("Errores en algunas filas:")
                    st.write(res["errors"][:5])
            except Exception as e:
                st.error(f"Error al importar: {e}")

    # Resumen del usuario
    st.divider()
    st.subheader(f"Resumen de {user_id}")
    if st.button("Actualizar resumen", key="btn_stats"):
        try:
            s = requests.get(f"{API_URL}/users/{user_id}/stats", timeout=10).json()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Transacciones", s["n_transactions"])
            c2.metric("Gastos totales", f"{s['total_gastos']:.2f} EUR")
            c3.metric("Ingresos totales", f"{s['total_ingresos']:.2f} EUR")
            c4.metric("Anomalias", s["n_anomalies"])
            if s["by_category"]:
                df = pd.DataFrame(s["by_category"])
                df_gastos = df[df["total"] < 0].copy()
                df_gastos["total"] = df_gastos["total"].abs()
                if not df_gastos.empty:
                    st.bar_chart(df_gastos.set_index("category")["total"], use_container_width=True)
                # Tabla completa + lista de anomalias
                col_tabla, col_anom = st.columns([2, 1])
                with col_tabla:
                    st.dataframe(df.rename(columns={"category": "Categoria", "n": "N", "total": "Total EUR"}),
                                 use_container_width=True)
                with col_anom:
                    st.caption("Anomalias recientes")
                    try:
                        txs = requests.get(f"{API_URL}/transactions/{user_id}", timeout=10).json()
                        anomalias = [t for t in txs if t.get("is_anomaly")][:10]
                        if anomalias:
                            for a in anomalias:
                                st.warning(f"{a['category']}: {a['anomaly_reason']}", icon=None)
                        else:
                            st.info("Sin anomalias registradas.")
                    except Exception:
                        st.caption("No se pudieron cargar anomalias.")
        except Exception as e:
            st.error(f"Error al cargar stats: {e}")


# --- Pantalla 3: insights mensuales ---------------------------------------
with tab3:
    st.subheader("Insights mensuales")
    st.caption(
        "Genera un analisis en lenguaje natural del mes a partir de los datos del usuario. "
        "Si hay credenciales Azure OpenAI configuradas, usa el LLM; si no, usa una plantilla local."
    )
    col_sel, _ = st.columns([1, 2])
    with col_sel:
        month = st.text_input("Mes (YYYY-MM)", "2026-04", key="ins_month")
    if st.button("Generar insight", type="primary", key="btn_insight"):
        try:
            with st.spinner("Generando insight mensual..."):
                r = requests.post(
                    f"{API_URL}/insights/generate",
                    json={"user_id": user_id, "month": month},
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()

            st.markdown(data["text"])
            st.divider()
            coste = data.get("cost_eur_estimate")
            if coste is not None:
                st.caption(
                    f"Fuente: **LLM (Azure gpt-4o-mini)** — "
                    f"{data['n_transactions']} transacciones — "
                    f"Coste estimado: **€{coste:.4f}**"
                )
            else:
                st.caption(
                    f"Fuente: **plantilla local** (sin LLM) — "
                    f"{data['n_transactions']} transacciones"
                )
        except Exception as e:
            st.error(f"Error al generar insight: {e}")
