"""App FastAPI de ClarityBank: punto de entrada.

Arrancar en local:
    uvicorn api.main:app --reload
Docs interactivas: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import settings
from api.db import init_db
from api.routers import insights, transactions, users
from core.anonymization import presidio_available
from core.classify import using_real_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crea las tablas SQLite al arrancar (idempotente)."""
    init_db()
    yield


app = FastAPI(
    title="ClarityBank API",
    version="0.1.0",
    description="Categorizacion de transacciones, anomalias e insights (prototipo TFM).",
    lifespan=lifespan,
)

app.include_router(transactions.router)
app.include_router(insights.router)
app.include_router(users.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Estado del sistema y que componentes estan en modo real vs mock/fallback."""
    return {
        "status": "ok",
        "db_path": str(settings.db_path),
        "classifier": "real" if using_real_model() else "mock",
        "anonymization": "presidio+regex" if presidio_available() else "regex",
        "insights": "llm" if settings.llm_enabled else "template",
    }
