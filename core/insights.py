"""Generacion de insights mensuales en lenguaje natural.

Flujo:
  1. Agregar las transacciones del mes (totales, top categorias, anomalias, variacion).
  2. Construir un prompt SOLO con datos agregados y descripciones ya anonimizadas.
  3. Si hay credenciales Azure OpenAI -> llamar al LLM (gpt-4o-mini, Sweden Central).
     Si no -> generar texto por plantilla local (fallback determinista para demo).

RGPD: nunca se envia PII al LLM; se usan agregados y texto anonimizado.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from api.config import settings

SYSTEM_PROMPT = (
    "Eres un asistente financiero de ClarityBank. Genera en espanol un analisis mensual "
    "de 3 a 4 parrafos a partir de datos agregados de gasto. "
    "Parrafo 1: resumen del mes (gasto total, ingresos, balance, variacion respecto al mes anterior). "
    "Parrafo 2: habitos de gasto, top categorias y dia de mayor actividad. "
    "Parrafo 3: alertas (anomalias, cambios en suscripciones). "
    "Parrafo 4 (opcional): un consejo concreto y accionable basado en los datos. "
    "Tono cercano y util. No inventes cifras: usa solo las proporcionadas."
)


def aggregate_month(
    transactions: list[dict[str, Any]],
    prev_transactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resume las transacciones de un mes en cifras agregadas (sin PII).

    Si se proporcionan prev_transactions, calcula tambien la variacion mensual
    y los cambios en suscripciones activas.
    """
    gasto_por_cat: dict[str, float] = defaultdict(float)
    gasto_por_dia: dict[str, float] = defaultdict(float)
    comercio_count: dict[str, int] = defaultdict(int)
    total_gasto = 0.0
    total_ingreso = 0.0
    anomalias: list[str] = []
    suscripciones_actuales: set[str] = set()

    for tx in transactions:
        amt = float(tx.get("amount", 0.0) or 0.0)
        cat = tx.get("category") or "otros"
        desc = tx.get("description_anonymized") or ""
        dia = (tx.get("created_at") or "")[:10]

        if amt < 0:
            gasto_por_cat[cat] += -amt
            total_gasto += -amt
            if dia:
                gasto_por_dia[dia] += -amt
            if desc:
                comercio_count[desc] += 1
        else:
            total_ingreso += amt

        if cat == "suscripciones" and desc:
            suscripciones_actuales.add(desc)

        if tx.get("is_anomaly"):
            anomalias.append(tx.get("anomaly_reason") or f"Movimiento atipico en {cat}")

    top = sorted(gasto_por_cat.items(), key=lambda kv: kv[1], reverse=True)[:3]
    dia_max = max(gasto_por_dia, key=lambda d: gasto_por_dia[d]) if gasto_por_dia else None
    comercio_top = (
        max(comercio_count, key=lambda c: comercio_count[c]) if comercio_count else None
    )

    variacion_pct: Optional[float] = None
    suscripciones_nuevas: list[str] = []
    suscripciones_canceladas: list[str] = []

    if prev_transactions is not None:
        prev_gasto = sum(
            -float(tx.get("amount", 0.0) or 0.0)
            for tx in prev_transactions
            if float(tx.get("amount", 0.0) or 0.0) < 0
        )
        if prev_gasto > 0:
            variacion_pct = round((total_gasto - prev_gasto) / prev_gasto * 100, 1)

        prev_subs: set[str] = {
            tx.get("description_anonymized") or ""
            for tx in prev_transactions
            if tx.get("category") == "suscripciones"
        } - {""}
        suscripciones_nuevas = sorted(suscripciones_actuales - prev_subs)
        suscripciones_canceladas = sorted(prev_subs - suscripciones_actuales)

    return {
        "n_transactions": len(transactions),
        "total_gasto": round(total_gasto, 2),
        "total_ingreso": round(total_ingreso, 2),
        "balance": round(total_ingreso - total_gasto, 2),
        "top_categorias": [{"categoria": c, "gasto": round(v, 2)} for c, v in top],
        "anomalias": anomalias,
        "variacion_gasto_pct": variacion_pct,
        "suscripciones_nuevas": suscripciones_nuevas,
        "suscripciones_canceladas": suscripciones_canceladas,
        "dia_mas_gasto": dia_max,
        "comercio_frecuente": comercio_top,
    }


def _build_prompt(month: str, agg: dict[str, Any]) -> str:
    tops = ", ".join(f"{t['categoria']} ({t['gasto']:.2f} EUR)" for t in agg["top_categorias"]) or "ninguna"
    anom = "; ".join(agg["anomalias"]) if agg["anomalias"] else "ninguna"
    variacion = (
        f"{agg['variacion_gasto_pct']:+.1f}% respecto al mes anterior"
        if agg.get("variacion_gasto_pct") is not None
        else "sin datos del mes anterior"
    )
    nuevas = ", ".join(agg.get("suscripciones_nuevas") or []) or "ninguna"
    canceladas = ", ".join(agg.get("suscripciones_canceladas") or []) or "ninguna"
    dia = agg.get("dia_mas_gasto") or "desconocido"
    comercio = agg.get("comercio_frecuente") or "desconocido"

    return (
        f"Mes: {month}\n"
        f"Transacciones: {agg['n_transactions']}\n"
        f"Gasto total: {agg['total_gasto']:.2f} EUR ({variacion})\n"
        f"Ingreso total: {agg['total_ingreso']:.2f} EUR\n"
        f"Balance: {agg['balance']:.2f} EUR\n"
        f"Top categorias de gasto: {tops}\n"
        f"Dia de mayor gasto: {dia}\n"
        f"Comercio mas frecuente: {comercio}\n"
        f"Suscripciones nuevas: {nuevas}\n"
        f"Suscripciones canceladas: {canceladas}\n"
        f"Anomalias detectadas: {anom}\n"
    )


def _template_insight(month: str, agg: dict[str, Any]) -> str:
    """Insight por plantilla (sin LLM). Determinista, suficiente para la demo."""
    if agg["n_transactions"] == 0:
        return f"No hay movimientos registrados en {month}."

    variacion_txt = ""
    if agg.get("variacion_gasto_pct") is not None:
        signo = "aumento" if agg["variacion_gasto_pct"] > 0 else "reduccion"
        variacion_txt = f", un {signo} del {abs(agg['variacion_gasto_pct']):.1f}% respecto al mes anterior"

    frases = [
        f"En {month} registraste {agg['n_transactions']} movimientos: "
        f"{agg['total_gasto']:.2f} EUR de gasto{variacion_txt} "
        f"y {agg['total_ingreso']:.2f} EUR de ingresos (balance {agg['balance']:+.2f} EUR)."
    ]

    if agg["top_categorias"]:
        t = agg["top_categorias"][0]
        frases.append(f"Tu mayor gasto fue en {t['categoria']} ({t['gasto']:.2f} EUR).")
    if len(agg["top_categorias"]) > 1:
        resto = ", ".join(x["categoria"] for x in agg["top_categorias"][1:])
        frases.append(f"Le siguen {resto}.")

    if agg.get("comercio_frecuente"):
        frases.append(f"El comercio mas frecuente fue '{agg['comercio_frecuente']}'.")

    if agg.get("suscripciones_nuevas"):
        frases.append(
            f"Suscripciones nuevas este mes: {', '.join(agg['suscripciones_nuevas'])}."
        )
    if agg.get("suscripciones_canceladas"):
        frases.append(
            f"Suscripciones que no aparecen este mes: {', '.join(agg['suscripciones_canceladas'])}."
        )

    if agg["anomalias"]:
        frases.append(f"Atencion: {len(agg['anomalias'])} movimiento(s) atipico(s) este mes.")

    return " ".join(frases)


def _llm_insight(month: str, agg: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Llama a Azure OpenAI. Devuelve (texto, tokens_usados). Lanza excepcion si falla."""
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )
    resp = client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(month, agg)},
        ],
        temperature=0.4,
        max_tokens=500,
    )
    tokens = {
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
    }
    return resp.choices[0].message.content.strip(), tokens


def generate_insight(
    month: str,
    transactions: list[dict[str, Any]],
    prev_transactions: list[dict[str, Any]] | None = None,
) -> tuple[str, str, dict[str, int] | None]:
    """Genera el insight del mes.

    Returns:
        (texto, source, tokens) donde source es 'llm' o 'template' y tokens
        es el dict de uso de tokens del LLM (None si se uso plantilla).
    """
    agg = aggregate_month(transactions, prev_transactions)

    if settings.llm_enabled:
        try:
            text, tokens = _llm_insight(month, agg)
            return text, "llm", tokens
        except Exception:
            pass
    return _template_insight(month, agg), "template", None
