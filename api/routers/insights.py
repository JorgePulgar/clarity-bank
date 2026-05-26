"""Endpoint de insights mensuales."""
from __future__ import annotations

from fastapi import APIRouter

from api.db import queries
from api.models.schemas import InsightRequest, InsightResponse
from core.insights import generate_insight

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post("/generate", response_model=InsightResponse)
def generate(req: InsightRequest) -> InsightResponse:
    """Genera el insight en lenguaje natural del mes solicitado para un usuario."""
    txs = queries.get_transactions_by_month(req.user_id, req.month)
    text, source = generate_insight(req.month, txs)
    return InsightResponse(
        user_id=req.user_id,
        month=req.month,
        text=text,
        source=source,
        n_transactions=len(txs),
    )
