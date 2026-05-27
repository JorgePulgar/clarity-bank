"""Esquemas pydantic de entrada/salida de la API.

Define el contrato HTTP. Independiente del esquema SQL (que vive en api/db).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Lista cerrada de 12 categorias (ver CLAUDE.md). Usada como type para validar.
Categoria = Literal[
    "alimentacion",
    "restauracion",
    "transporte",
    "ocio",
    "compras",
    "hogar",
    "salud",
    "suscripciones",
    "transferencias",
    "ingresos",
    "impuestos_tasas",
    "otros",
]


# --- /transactions ---------------------------------------------------------


class TransactionIn(BaseModel):
    """Transaccion cruda que entra al sistema."""

    user_id: str = Field(
        ...,
        description="Identificador del usuario (opaco, sin PII).",
        examples=["user_0001"],
    )
    description: str = Field(
        ...,
        description="Texto original del movimiento bancario. Se anonimiza antes de clasificar.",
        examples=["PAGO TARJETA MERCADONA SL MADRID"],
    )
    amount: float = Field(
        ...,
        description="Importe del movimiento en EUR. Negativo = gasto, positivo = ingreso.",
        examples=[-43.27],
    )
    date: Optional[str] = Field(
        None,
        description="Fecha del movimiento en formato ISO 8601. Si se omite, se usa el instante de ingesta.",
        examples=["2026-04-15T10:30:00"],
    )


class TransactionOut(BaseModel):
    """Transaccion procesada y persistida, con categoria y resultado de anomalia."""

    id: str = Field(..., description="UUID hex de la transaccion.", examples=["a1b2c3d4e5f6"])
    user_id: str = Field(..., examples=["user_0001"])
    description_raw: Optional[str] = Field(
        None,
        description="Descripcion original tal como llego (con posible PII).",
        examples=["PAGO TARJETA MERCADONA SL MADRID"],
    )
    description_anonymized: Optional[str] = Field(
        None,
        description="Descripcion con PII sustituida por placeholders (<IBAN>, <EMAIL>, etc.).",
        examples=["PAGO TARJETA MERCADONA SL MADRID"],
    )
    amount: float = Field(..., description="Importe en EUR.", examples=[-43.27])
    category: Optional[str] = Field(
        None,
        description="Categoria asignada (una de las 12 fijas).",
        examples=["alimentacion"],
    )
    confidence: Optional[float] = Field(
        None,
        description="Confianza del clasificador [0, 1].",
        examples=[0.92],
    )
    classification_level: Optional[int] = Field(
        None,
        description="Nivel usado: 1 = clasificador local, 2 = LLM.",
        examples=[1],
    )
    is_anomaly: bool = Field(
        ...,
        description="True si el importe es atipico respecto al historico del usuario.",
        examples=[False],
    )
    anomaly_reason: Optional[str] = Field(
        None,
        description="Descripcion legible de por que se considero anomalia. Null si no es anomalia.",
        examples=["Gasto 1450.0 en 'compras' a 4.7 sigma de la media (45.20, desv 280.10)."],
    )
    created_at: str = Field(
        ...,
        description="Timestamp ISO 8601 de cuando se proceso la transaccion.",
        examples=["2026-04-15T10:30:00+00:00"],
    )


# --- /transactions/import --------------------------------------------------


class ImportResult(BaseModel):
    """Resumen de una importacion en lote desde CSV o JSON."""

    received: int = Field(..., description="Filas recibidas en el fichero.", examples=[150])
    processed: int = Field(..., description="Filas procesadas correctamente.", examples=[148])
    anomalies: int = Field(..., description="Transacciones marcadas como anomalia.", examples=[7])
    errors: list[str] = Field(
        default=[],
        description="Lista de errores por fila (vacia si todo fue correcto).",
        examples=[["fila 3: campo 'amount' invalido"]],
    )


# --- /insights/generate ----------------------------------------------------


class InsightRequest(BaseModel):
    """Peticion de insight mensual para un usuario."""

    user_id: str = Field(..., description="ID del usuario.", examples=["user_0001"])
    month: str = Field(
        ...,
        description="Mes a analizar en formato YYYY-MM.",
        examples=["2026-04"],
    )


class InsightResponse(BaseModel):
    """Insight mensual generado por LLM o por plantilla local."""

    user_id: str = Field(..., examples=["user_0001"])
    month: str = Field(..., examples=["2026-04"])
    text: str = Field(
        ...,
        description="Texto del insight en lenguaje natural.",
        examples=[
            "En abril registraste 34 movimientos: 1506.26 EUR de gasto y 2000.00 EUR de ingresos."
        ],
    )
    source: Literal["llm", "template"] = Field(
        ...,
        description="'llm' si fue generado por Azure OpenAI gpt-4o-mini; 'template' si fue el fallback local.",
        examples=["template"],
    )
    n_transactions: int = Field(
        ...,
        description="Numero de transacciones del mes incluidas en el analisis.",
        examples=[34],
    )
    cost_eur_estimate: Optional[float] = Field(
        None,
        description="Coste estimado en EUR de la llamada al LLM. Null si se uso la plantilla local.",
        examples=[0.000126],
    )


# --- /users/{id}/stats -----------------------------------------------------


class CategoryStat(BaseModel):
    """Estadistica de una categoria para el desglose del usuario."""

    category: Optional[str] = Field(None, examples=["alimentacion"])
    n: int = Field(..., description="Numero de transacciones.", examples=[42])
    total: float = Field(
        ..., description="Suma de importes (negativo = gasto).", examples=[-1240.50]
    )


class UserStats(BaseModel):
    """Agregados globales del usuario para el dashboard."""

    user_id: str = Field(..., examples=["user_0001"])
    n_transactions: int = Field(
        ..., description="Total de transacciones procesadas.", examples=[154]
    )
    total_gastos: float = Field(
        ..., description="Suma de gastos (valor positivo).", examples=[3241.85]
    )
    total_ingresos: float = Field(..., description="Suma de ingresos.", examples=[12000.0])
    n_anomalies: int = Field(..., description="Transacciones marcadas como anomalia.", examples=[3])
    n_llm_calls: int = Field(
        default=0,
        description="Transacciones que requirieron escalar al LLM (nivel 2).",
        examples=[1],
    )
    by_category: list[CategoryStat] = Field(
        ...,
        description="Desglose por categoria ordenado por volumen de gasto descendente.",
    )


class CostStats(BaseModel):
    """Estadisticas de coste para el panel de eficiencia."""

    n_transactions: int = Field(
        ..., description="Total de transacciones del usuario.", examples=[154]
    )
    n_llm_calls: int = Field(
        ...,
        description="Transacciones que usaron el LLM (nivel 2).",
        examples=[1],
    )
    n_insights: int = Field(..., description="Numero de insights generados.", examples=[2])
    total_cost_eur: float = Field(
        ...,
        description="Coste total acumulado en EUR de las llamadas al LLM.",
        examples=[0.000252],
    )
