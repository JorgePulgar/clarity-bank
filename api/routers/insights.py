"""Endpoint de insights mensuales."""
from __future__ import annotations

from fastapi import APIRouter

from api.db import queries
from api.models.schemas import InsightRequest, InsightResponse
from core.insights import generate_insight

router = APIRouter(prefix="/insights", tags=["insights"])

# Precios gpt-4o-mini Sweden Central (USD) convertidos a EUR (cambio ~0.93)
_EUR_PER_INPUT_TOKEN = 0.150 / 1_000_000 * 0.93
_EUR_PER_OUTPUT_TOKEN = 0.600 / 1_000_000 * 0.93


def _prev_month(month: str) -> str:
    """'2026-05' -> '2026-04'. Maneja el cambio de anyo."""
    y, m = int(month[:4]), int(month[5:7])
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y}-{m:02d}"


def _compute_cost(tokens: dict[str, int] | None) -> float | None:
    """Calcula el coste en EUR de una llamada al LLM. None si no hay tokens."""
    if not tokens:
        return None
    return round(
        tokens.get("prompt_tokens", 0) * _EUR_PER_INPUT_TOKEN
        + tokens.get("completion_tokens", 0) * _EUR_PER_OUTPUT_TOKEN,
        6,
    )


@router.post("/generate", response_model=InsightResponse)
def generate(req: InsightRequest) -> InsightResponse:
    """Genera el insight en lenguaje natural del mes solicitado para un usuario."""
    txs = queries.get_transactions_by_month(req.user_id, req.month)
    prev_txs = queries.get_transactions_by_month(req.user_id, _prev_month(req.month))
    text, source, tokens = generate_insight(req.month, txs, prev_txs)

    cost = _compute_cost(tokens)
    queries.record_insight_call(
        user_id=req.user_id,
        month=req.month,
        source=source,
        prompt_tokens=tokens.get("prompt_tokens", 0) if tokens else 0,
        completion_tokens=tokens.get("completion_tokens", 0) if tokens else 0,
        cost_eur=cost or 0.0,
    )

    return InsightResponse(
        user_id=req.user_id,
        month=req.month,
        text=text,
        source=source,
        n_transactions=len(txs),
        cost_eur_estimate=cost,
    )
