"""Generacion de insights mensuales en lenguaje natural.

Flujo:
  1. Agregar las transacciones del mes (totales, top categorias, anomalias).
  2. Construir un prompt SOLO con datos agregados y descripciones ya anonimizadas.
  3. Si hay credenciales Azure OpenAI -> llamar al LLM (gpt-4o-mini, Sweden Central).
     Si no -> generar texto por plantilla local (fallback determinista para demo).

RGPD: nunca se envia PII al LLM; se usan agregados y texto anonimizado.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from api.config import settings

SYSTEM_PROMPT = (
    "Eres un asistente financiero de ClarityBank. Resume en espanol claro y breve "
    "(maximo 6 frases) los habitos de gasto del mes a partir de datos agregados. "
    "Tono cercano y util. Destaca la categoria de mayor gasto, cambios relevantes y "
    "cualquier anomalia. No inventes cifras: usa solo las proporcionadas."
)


def aggregate_month(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Resume las transacciones de un mes en cifras agregadas (sin PII)."""
    gasto_por_cat: dict[str, float] = defaultdict(float)
    total_gasto = 0.0
    total_ingreso = 0.0
    anomalias: list[str] = []

    for tx in transactions:
        amt = tx.get("amount", 0.0) or 0.0
        cat = tx.get("category") or "otros"
        if amt < 0:
            gasto_por_cat[cat] += -amt
            total_gasto += -amt
        else:
            total_ingreso += amt
        if tx.get("is_anomaly"):
            anomalias.append(tx.get("anomaly_reason") or f"Movimiento atipico en {cat}")

    top = sorted(gasto_por_cat.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return {
        "n_transactions": len(transactions),
        "total_gasto": round(total_gasto, 2),
        "total_ingreso": round(total_ingreso, 2),
        "balance": round(total_ingreso - total_gasto, 2),
        "top_categorias": [{"categoria": c, "gasto": round(v, 2)} for c, v in top],
        "anomalias": anomalias,
    }


def _build_prompt(month: str, agg: dict[str, Any]) -> str:
    tops = ", ".join(f"{t['categoria']} ({t['gasto']:.2f} EUR)" for t in agg["top_categorias"]) or "ninguna"
    anom = "; ".join(agg["anomalias"]) if agg["anomalias"] else "ninguna"
    return (
        f"Mes: {month}\n"
        f"Transacciones: {agg['n_transactions']}\n"
        f"Gasto total: {agg['total_gasto']:.2f} EUR\n"
        f"Ingreso total: {agg['total_ingreso']:.2f} EUR\n"
        f"Balance: {agg['balance']:.2f} EUR\n"
        f"Top categorias de gasto: {tops}\n"
        f"Anomalias detectadas: {anom}\n"
    )


def _template_insight(month: str, agg: dict[str, Any]) -> str:
    """Insight por plantilla (sin LLM). Determinista, suficiente para la demo."""
    if agg["n_transactions"] == 0:
        return f"No hay movimientos registrados en {month}."

    frases = [
        f"En {month} registraste {agg['n_transactions']} movimientos: "
        f"{agg['total_gasto']:.2f} EUR de gasto y {agg['total_ingreso']:.2f} EUR de ingresos "
        f"(balance {agg['balance']:+.2f} EUR)."
    ]
    if agg["top_categorias"]:
        t = agg["top_categorias"][0]
        frases.append(f"Tu mayor gasto fue en {t['categoria']} ({t['gasto']:.2f} EUR).")
    if len(agg["top_categorias"]) > 1:
        resto = ", ".join(f"{x['categoria']}" for x in agg["top_categorias"][1:])
        frases.append(f"Le siguen {resto}.")
    if agg["anomalias"]:
        frases.append(f"Atencion: {len(agg['anomalias'])} movimiento(s) atipico(s) este mes.")
    return " ".join(frases)


def _llm_insight(month: str, agg: dict[str, Any]) -> str:
    """Llama a Azure OpenAI. Lanza excepcion si falla (el caller decide fallback)."""
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
        max_tokens=300,
    )
    return resp.choices[0].message.content.strip()


def generate_insight(month: str, transactions: list[dict[str, Any]]) -> tuple[str, str]:
    """Genera el insight del mes.

    Returns:
        (texto, source) donde source es 'llm' o 'template'.
    """
    agg = aggregate_month(transactions)

    if settings.llm_enabled:
        try:
            return _llm_insight(month, agg), "llm"
        except Exception:
            # Caida del LLM -> no rompemos la demo, devolvemos plantilla.
            pass
    return _template_insight(month, agg), "template"
