"""Esquemas pydantic de entrada/salida de la API.

Define el contrato HTTP. Independiente del esquema SQL (que vive en api/db).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Lista cerrada de 12 categorias (ver CLAUDE.md). Usada como type para validar.
Categoria = Literal[
    "alimentacion", "restauracion", "transporte", "ocio", "compras", "hogar",
    "salud", "suscripciones", "transferencias", "ingresos", "impuestos_tasas", "otros",
]


# --- /transactions ---------------------------------------------------------

class TransactionIn(BaseModel):
    """Transaccion cruda que entra al sistema."""

    user_id: str = Field(..., examples=["user_0001"])
    description: str = Field(..., examples=["PAGO TARJETA MERCADONA SL MADRID"])
    amount: float = Field(..., description="Negativo = gasto, positivo = ingreso", examples=[-43.27])
    # Opcional: fecha del movimiento. Si falta, se usa el instante de ingesta.
    date: Optional[str] = Field(None, description="ISO 8601; por defecto 'ahora'")


class TransactionOut(BaseModel):
    """Transaccion procesada y persistida."""

    id: str
    user_id: str
    description_raw: Optional[str]
    description_anonymized: Optional[str]
    amount: float
    category: Optional[str]
    confidence: Optional[float]
    classification_level: Optional[int]
    is_anomaly: bool
    anomaly_reason: Optional[str]
    created_at: str


# --- /transactions/import --------------------------------------------------

class ImportResult(BaseModel):
    """Resumen de una importacion en lote."""

    received: int
    processed: int
    anomalies: int
    errors: list[str] = []


# --- /insights/generate ----------------------------------------------------

class InsightRequest(BaseModel):
    user_id: str = Field(..., examples=["user_0001"])
    month: str = Field(..., description="Formato YYYY-MM", examples=["2026-04"])


class InsightResponse(BaseModel):
    user_id: str
    month: str
    text: str
    source: Literal["llm", "template"] = Field(
        ..., description="'llm' si lo genero Azure OpenAI, 'template' si fallback local"
    )
    n_transactions: int
    cost_eur_estimate: Optional[float] = Field(
        None, description="Coste estimado en EUR de la llamada al LLM (None si se uso plantilla)"
    )


# --- /users/{id}/stats -----------------------------------------------------

class CategoryStat(BaseModel):
    category: Optional[str]
    n: int
    total: float


class UserStats(BaseModel):
    user_id: str
    n_transactions: int
    total_gastos: float
    total_ingresos: float
    n_anomalies: int
    n_llm_calls: int = 0
    by_category: list[CategoryStat]


class CostStats(BaseModel):
    n_transactions: int
    n_llm_calls: int
    n_insights: int
    total_cost_eur: float
