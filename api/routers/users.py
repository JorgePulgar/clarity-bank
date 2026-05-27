"""Endpoint de estadisticas agregadas de usuario (para el dashboard)."""

from __future__ import annotations

from fastapi import APIRouter

from api.db import queries
from api.models.schemas import CostStats, UserStats

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}/stats", response_model=UserStats)
def user_stats(user_id: str) -> UserStats:
    """Agregados basicos del usuario: totales, anomalias y desglose por categoria."""
    return UserStats(**queries.get_user_stats(user_id))


@router.get("/{user_id}/cost-stats", response_model=CostStats)
def cost_stats(user_id: str) -> CostStats:
    """Estadisticas de coste: transacciones procesadas, llamadas LLM e insights generados."""
    return CostStats(**queries.get_cost_stats(user_id))
