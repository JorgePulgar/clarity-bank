"""Dashboard de demostracion ClarityBank (Streamlit).

Tres pantallas: transaccion individual, importar lote, insights mensuales.
Habla con la API por HTTP (no toca la BD directamente) para reflejar el flujo real.

Arrancar (con la API ya levantada):
    streamlit run dashboard/streamlit_app.py
"""

from __future__ import annotations

import csv
import io
import os
import random
import re
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

# Categorias que no son gasto de consumo (se excluyen del grafico principal)
_CATS_EXCLUIR_GRAFICO: set[str] = {"ingresos", "transferencias"}

# Regex para extraer el valor sigma de un texto de razon de anomalia
_SIGMA_RE = re.compile(r"(-?[\d]+\.[\d]+) sigma")


def _fmt_eur(amount: float) -> str:
    """Formatea un importe en euros con separadores espanoles: 1.234,56 €"""
    formatted = f"{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sign = "−" if amount < 0 else ""
    return f"{sign}{formatted} €"


def _sigma_de_razon(reason: str) -> float | None:
    """Extrae el valor absoluto de sigma de un texto de razon de anomalia."""
    m = _SIGMA_RE.search(reason)
    return abs(float(m.group(1))) if m else None


def _cap_sigma_texto(reason: str) -> str:
    """Reemplaza valores sigma > 5 con '>5σ' para evitar cifras irreales en la UI."""
    def _repl(m: re.Match) -> str:
        return ">5σ" if abs(float(m.group(1))) > 5.0 else m.group(0)
    return _SIGMA_RE.sub(_repl, reason)


def _mostrar_anomalia(texto_completo: str) -> None:
    """Muestra tarjeta de anomalia con color segun severidad del z-score.

    - z > 5  → rojo (grave)
    - z 3.5–5 → naranja (media)
    - z < 3.5 o sin sigma → amarillo (leve / otro tipo de anomalia)
    """
    z = _sigma_de_razon(texto_completo)
    texto = _cap_sigma_texto(texto_completo)
    if z is not None and z > 5.0:
        st.error(texto, icon=None)
    elif z is not None and z > 3.5:
        st.markdown(
            f'<div style="background:#7C3209;color:#FFD0A0;padding:8px 12px;'
            f'border-radius:4px;margin-bottom:4px;font-size:0.85rem;">🟠 {texto}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning(texto, icon=None)

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
        modo = h.get("classifier", "mock")
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

# Pool ordenado para la simulacion de stream.
# Outliers en posiciones 5, 9 y 16 — visibles con n_stream >= 10.
# Requieren historico previo para que el z-score tenga baseline.
_STREAM_POOL: list[tuple[str, float]] = [
    ("PAGO TARJETA MERCADONA SL MADRID", -43.27),      # 1  alimentacion normal
    ("NETFLIX SUSCRIPCION MENSUAL", -12.99),            # 2  suscripciones normal
    ("UBER TRIP MADRID", -18.50),                       # 3  transporte normal
    ("GLOVO PEDIDO COMIDA", -24.80),                    # 4  restauracion normal
    ("AMAZON COMPRA ONLINE", -1450.00),                 # 5  compras — ANOMALIA
    ("FARMACIA CENTRAL MADRID", -22.10),                # 6  salud normal
    ("ABONO NOMINA EMPRESA SL MADRID", 2000.00),        # 7  ingresos normal
    ("SPOTIFY PREMIUM", -10.99),                        # 8  suscripciones normal
    ("RESTAURANTE EL CELLER DE CAN ROCA", -380.00),     # 9  restauracion — ANOMALIA
    ("REINTEGRO CONCEPTOS VARIOS CUENTA", 150.00),      # 10 ambigua
    ("TRANSFERENCIA ALQUILER PISO MADRID", -750.00),    # 11 hogar normal
    ("AMAZON COMPRA ONLINE", -85.40),                   # 12 compras normal
    ("CUOTA ASOCIACION CULTURAL MADRID", -80.00),       # 13 ambigua
    ("BAR LA ESQUINA MADRID", -14.60),                  # 14 restauracion normal
    ("IBERDROLA FACTURA LUZ OCTUBRE", -78.30),          # 15 hogar normal
    ("TRANSFERENCIA BIZUM VARIOS", -950.00),            # 16 transferencias — ANOMALIA
    ("CARREFOUR EXPRESS MADRID", -38.90),               # 17 alimentacion normal
    ("ZARA TIENDA MADRID", -64.00),                     # 18 compras normal
    ("RENFE CERCANIAS BILLETE", -4.50),                 # 19 transporte normal
    ("MOVISTAR FACTURA FIBRA", -49.99),                 # 20 suscripciones normal
]

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Transaccion individual",
        "Importar historico",
        "Insights mensuales",
        "Flujo en vivo",
    ]
)


# --- Pantalla 1: transaccion individual -----------------------------------
with tab1:
    st.subheader("Clasificar una transaccion")
    st.caption("Introduce un movimiento bancario para ver como lo clasifica el sistema.")
    with st.form("tx_form"):
        desc = st.text_input("Descripcion del movimiento", "PAGO TARJETA MERCADONA SL MADRID")
        amount = st.number_input(
            "Importe (EUR)",
            value=-43.27,
            step=1.0,
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
            nivel = data["classification_level"]
            if nivel == 2 and confianza > 0:
                c2.metric(
                    "Confianza L1",
                    f"{confianza:.0%}",
                    help="Score del clasificador local antes de escalar al LLM. Por debajo del umbral → se uso LLM.",
                )
            elif nivel == 2:
                c2.metric(
                    "Confianza L1",
                    "—",
                    help="El clasificador local escalo al LLM pero no reporto su score.",
                )
            else:
                c2.metric("Confianza", f"{confianza:.0%}")
            nivel_txt = "L1 — Local" if nivel == 1 else "L2 — LLM"
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
        st.caption(
            "Crea un historico realista con gastos tipicos, nomina y outliers intencionados."
        )
        meses = st.slider("Meses de historico", 1, 12, 6, key="gen_meses")
        salario = st.number_input(
            "Salario mensual (EUR)", value=2000.0, step=100.0, key="gen_salario"
        )
        ciudad = st.text_input(
            "Ciudad (para nombres de comercios)", "MADRID", key="gen_ciudad"
        ).upper()
        if st.button("Generar e importar historico", type="primary", key="btn_generar"):
            try:
                barra = st.progress(0, text="Generando transacciones...")
                random.seed(42)
                rows = _gen_historico(
                    user=user_id,
                    months=meses,
                    per_month=50,
                    salary=salario,
                    ciudad=ciudad,
                    n_suscripciones=3,
                )
                barra.progress(40, text=f"Generadas {len(rows)} transacciones. Importando...")
                buf = io.StringIO()
                w = csv.DictWriter(buf, fieldnames=["user_id", "description", "amount", "date"])
                w.writeheader()
                w.writerows(rows)
                r = requests.post(
                    f"{API_URL}/transactions/import",
                    files={
                        "file": (
                            "historico.csv",
                            buf.getvalue().encode("utf-8"),
                            "text/csv",
                        )
                    },
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

            # Metricas principales — columnas mas anchas para cifras monetarias
            c1, c2, c3, c4 = st.columns([1, 1.8, 1.8, 1])
            c1.metric("Transacciones", s["n_transactions"])
            c2.metric("Gastos totales", _fmt_eur(s["total_gastos"]))
            c3.metric("Ingresos totales", _fmt_eur(s["total_ingresos"]))
            c4.metric("Anomalias", s["n_anomalies"])

            # Fetch transacciones una vez — reutilizado por anomalias, grafico y top comercios
            try:
                txs_raw = requests.get(
                    f"{API_URL}/transactions/{user_id}", timeout=10
                ).json()
            except Exception:
                txs_raw = []

            # DataFrame base para analisis temporal y top comercios
            df_txs = pd.DataFrame(txs_raw) if txs_raw else pd.DataFrame()
            if not df_txs.empty:
                df_txs["created_at"] = pd.to_datetime(df_txs["created_at"])
                df_txs["mes"] = df_txs["created_at"].dt.strftime("%Y-%m")
                df_txs_consumo = df_txs[
                    (df_txs["amount"] < 0) & (~df_txs["category"].isin(_CATS_EXCLUIR_GRAFICO))
                ].copy()
                df_txs_consumo["gasto"] = df_txs_consumo["amount"].abs()
            else:
                df_txs_consumo = pd.DataFrame()

            if s["by_category"]:
                df = pd.DataFrame(s["by_category"])

                # Gasto de consumo: solo categorias negativas excluyendo ingresos/transferencias
                df_consumo = df[
                    (df["total"] < 0) & (~df["category"].isin(_CATS_EXCLUIR_GRAFICO))
                ].copy()
                df_consumo["total"] = df_consumo["total"].abs()
                df_consumo = df_consumo.sort_values("total", ascending=False)

                if not df_consumo.empty:
                    st.markdown("**Gasto de consumo por categoria**")
                    st.bar_chart(
                        df_consumo.set_index("category")["total"],
                        use_container_width=True,
                    )

                # Ingresos y transferencias como metricas separadas
                row_ing = df[df["category"] == "ingresos"]
                row_tra = df[df["category"] == "transferencias"]
                if not row_ing.empty or not row_tra.empty:
                    ci, ct = st.columns(2)
                    if not row_ing.empty:
                        ci.info(
                            f"Ingresos: **{_fmt_eur(row_ing.iloc[0]['total'])}** "
                            f"({row_ing.iloc[0]['n']} transacciones)"
                        )
                    if not row_tra.empty:
                        ct.info(
                            f"Transferencias: **{_fmt_eur(abs(row_tra.iloc[0]['total']))}** "
                            f"({row_tra.iloc[0]['n']} transacciones)"
                        )

                # Tabla categorias con columna % del gasto de consumo
                col_tabla, col_anom = st.columns([2, 1])
                with col_tabla:
                    total_consumo = df_consumo["total"].sum() if not df_consumo.empty else 0.0

                    def _pct_gasto(row: pd.Series) -> str:
                        if row["category"] in _CATS_EXCLUIR_GRAFICO or row["total"] >= 0:
                            return "—"
                        if total_consumo == 0:
                            return "—"
                        return (
                            f"{abs(row['total']) / total_consumo * 100:.1f} %"
                            .replace(".", ",")
                        )

                    df_tabla = df.copy()
                    df_tabla["importe"] = df_tabla["total"].apply(_fmt_eur)
                    df_tabla["% gasto"] = df_tabla.apply(_pct_gasto, axis=1)
                    df_tabla = df_tabla.sort_values("total")  # mas negativo (mayor gasto) primero
                    st.dataframe(
                        df_tabla[["category", "n", "importe", "% gasto"]].rename(
                            columns={"category": "Categoria", "n": "N", "importe": "Importe"}
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                with col_anom:
                    st.caption("Anomalias recientes")
                    anomalias = [t for t in txs_raw if t.get("is_anomaly")][:10]
                    if anomalias:
                        for a in anomalias:
                            _mostrar_anomalia(
                                f"{a['category']}: {a['anomaly_reason']}"
                            )
                    else:
                        st.info("Sin anomalias registradas.")

            # --- Bloque 3.1: Evolucion mensual del gasto ---
            if not df_txs_consumo.empty:
                st.divider()
                st.markdown("**Evolucion mensual del gasto de consumo**")
                df_mensual = (
                    df_txs_consumo.groupby("mes")["gasto"]
                    .sum()
                    .reset_index()
                    .sort_values("mes")
                    .rename(columns={"mes": "Mes", "gasto": "Gasto (€)"})
                )
                st.line_chart(df_mensual.set_index("Mes"), use_container_width=True)

            # --- Bloque 3.2: Top 5 comercios por gasto ---
            if not df_txs_consumo.empty:
                st.divider()
                st.markdown("**Top 5 comercios por gasto**")
                df_top = (
                    df_txs_consumo.groupby("description_raw")
                    .agg(Transacciones=("gasto", "count"), Gasto=("gasto", "sum"))
                    .reset_index()
                    .nlargest(5, "Gasto")
                )
                df_top["Comercio"] = df_top["description_raw"].str[:45]
                df_top["Gasto"] = df_top["Gasto"].apply(_fmt_eur)
                st.dataframe(
                    df_top[["Comercio", "Transacciones", "Gasto"]],
                    use_container_width=True,
                    hide_index=True,
                )

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


# --- Pantalla 4: flujo en vivo -------------------------------------------
with tab4:
    st.subheader("Flujo en vivo — Simulacion de stream de transacciones")
    st.caption(
        "Simula la llegada continua de transacciones, como llegarian desde un consumer Kafka "
        "o webhook bancario en produccion. El pipeline es identico: anonimizacion RGPD → "
        "clasificacion (L1/L2) → deteccion de anomalias."
    )

    col_v, col_n, col_hist = st.columns([1, 1, 1])
    velocidad = col_v.slider(
        "Intervalo (s)",
        min_value=0.3,
        max_value=3.0,
        value=1.0,
        step=0.1,
        key="stream_vel",
        help="Tiempo entre transacciones. En produccion este ritmo lo marca Kafka/webhook.",
    )
    n_stream = col_n.slider(
        "Num. transacciones",
        min_value=5,
        max_value=len(_STREAM_POOL),
        value=10,
        key="stream_n",
    )
    gen_historico_previo = col_hist.checkbox(
        "Generar historico previo",
        value=True,
        key="stream_gen_hist",
        help="Importa 6 meses de historico antes de la simulacion. "
             "Necesario para que el z-score tenga baseline y detecte anomalias.",
    )

    n_anom_pool = sum(1 for _, amt in _STREAM_POOL[:n_stream] if amt in (-1450.0, -380.0, -950.0))
    st.info(
        f"{n_stream} transacciones · intervalo {velocidad}s · "
        f"~{n_stream * velocidad:.0f}s total · "
        f"{n_anom_pool} outlier(s) en este rango"
        + (" · historico previo: SI" if gen_historico_previo else " · historico previo: NO → anomalias no detectables")
    )

    iniciar = st.button(
        "Iniciar simulacion",
        type="primary",
        key="btn_stream",
        disabled=not api_ok,
    )
    if not api_ok:
        st.warning("API no disponible. Arranca la API para usar esta pantalla.")

    if iniciar:
        txs_a_procesar = _STREAM_POOL[:n_stream]

        if gen_historico_previo:
            with st.spinner("Generando historico previo (6 meses)..."):
                try:
                    import io as _io
                    import csv as _csv
                    random.seed(42)
                    rows_hist = _gen_historico(
                        user=user_id, months=6, per_month=20,
                        salary=2000.0, ciudad="MADRID", n_suscripciones=3,
                    )
                    buf = _io.StringIO()
                    w = _csv.DictWriter(buf, fieldnames=["user_id", "description", "amount", "date"])
                    w.writeheader()
                    w.writerows(rows_hist)
                    rh = requests.post(
                        f"{API_URL}/transactions/import",
                        files={"file": ("hist.csv", buf.getvalue().encode("utf-8"), "text/csv")},
                        timeout=120,
                    )
                    rh.raise_for_status()
                    res_h = rh.json()
                    st.success(f"Historico listo: {res_h['processed']} transacciones importadas.")
                except Exception as e:
                    st.warning(f"Historico no importado: {e}. Las anomalias pueden no detectarse.")

        ph_estado = st.empty()
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        ph_total = col_m1.empty()
        ph_anomalias = col_m2.empty()
        ph_llm = col_m3.empty()
        ph_tiempo = col_m4.empty()
        ph_tabla = st.empty()
        ph_chart = st.empty()

        filas: list[dict] = []
        t_inicio = time.time()

        for i, (desc, amount) in enumerate(txs_a_procesar, 1):
            ph_estado.info(f"Procesando {i}/{len(txs_a_procesar)}: {desc[:50]}...")

            try:
                resp = requests.post(
                    f"{API_URL}/transactions",
                    json={"user_id": user_id, "description": desc, "amount": amount},
                    timeout=15,
                )
                resp.raise_for_status()
                tx = resp.json()

                anon = tx.get("description_anonymized") or desc
                nivel_num = tx["classification_level"]
                nivel = "L2 LLM" if nivel_num == 2 else "L1 local"
                conf = tx["confidence"]
                if nivel_num == 2:
                    conf_txt = f"{conf:.0%} L1" if conf > 0 else "— L1"
                else:
                    conf_txt = f"{conf:.0%}"
                filas.append(
                    {
                        "Descripcion": desc[:42] + "…" if len(desc) > 42 else desc,
                        "Anonimizada": anon[:42] + "…" if len(anon) > 42 else anon,
                        "Categoria": tx["category"],
                        "Confianza": conf_txt,
                        "Nivel": nivel,
                        "Importe": f"{amount:+.2f}",
                        "Anomalia": "SI" if tx["is_anomaly"] else "—",
                    }
                )
            except Exception:
                filas.append(
                    {
                        "Descripcion": desc[:42],
                        "Anonimizada": "—",
                        "Categoria": "error",
                        "Confianza": "—",
                        "Nivel": "—",
                        "Importe": f"{amount:+.2f}",
                        "Anomalia": "ERR",
                    }
                )

            n_ok = sum(1 for f in filas if f["Categoria"] != "error")
            n_anom = sum(1 for f in filas if f["Anomalia"] == "SI")
            n_llm_cnt = sum(1 for f in filas if f["Nivel"] == "L2 LLM")
            elapsed = time.time() - t_inicio

            ph_total.metric("Procesadas", n_ok)
            ph_anomalias.metric("Anomalias", n_anom)
            ph_llm.metric("Escaladas LLM", n_llm_cnt)
            ph_tiempo.metric("Tiempo", f"{elapsed:.1f}s")

            df_live = pd.DataFrame(filas)
            ph_tabla.dataframe(df_live, use_container_width=True, hide_index=True)

            cats = df_live[df_live["Categoria"] != "error"]["Categoria"].value_counts()
            if not cats.empty:
                ph_chart.bar_chart(cats, use_container_width=True)

            time.sleep(velocidad)

        elapsed_final = time.time() - t_inicio
        ph_estado.success(
            f"Simulacion completada: {n_ok}/{len(txs_a_procesar)} procesadas en "
            f"{elapsed_final:.1f}s | {n_anom} anomalias | {n_llm_cnt} escaladas a LLM"
        )
