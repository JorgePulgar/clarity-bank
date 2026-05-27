"""Endpoint de insights mensuales."""
from __future__ import annotations

from fastapi import APIRouter

from api.db import queries
from api.models.schemas import InsightRequest, InsightResponse
from core.insights import generate_insight

router = APIRouter(prefix="/insights", tags=["insights"])


def _prev_month(month: str) -> str:
    """'2026-05' -> '2026-04'. Maneja el cambio de anyo."""
    y, m = int(month[:4]), int(month[5:7])
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y}-{m:02d}"


@router.post("/generate", response_model=InsightResponse)
def generate(req: InsightRequest) -> InsightResponse:
    """Genera el insight en lenguaje natural del mes solicitado para un usuario."""
    txs = queries.get_transactions_by_month(req.user_id, req.month)
    prev_txs = queries.get_transactions_by_month(req.user_id, _prev_month(req.month))
    text, source, _tokens = generate_insight(req.month, txs, prev_txs)
    return InsightResponse(
        user_id=req.user_id,
        month=req.month,
        text=text,
        source=source,
        n_transactions=len(txs),
    )
