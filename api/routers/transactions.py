"""Endpoints de transacciones: crear, listar e importar en lote."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.db import queries
from api.models.schemas import ImportResult, TransactionIn, TransactionOut
from api.service import process_transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(tx: TransactionIn) -> TransactionOut:
    """Recibe una transaccion, la anonimiza, clasifica, detecta anomalia y la guarda."""
    row = process_transaction(tx.user_id, tx.description, tx.amount, tx.date)
    return TransactionOut(**row)


@router.get("/{user_id}", response_model=list[TransactionOut])
def list_transactions(user_id: str, limit: int = 500) -> list[TransactionOut]:
    """Histórico de transacciones del usuario, mas recientes primero."""
    rows = queries.get_transactions_by_user(user_id, limit=limit)
    return [TransactionOut(**{**r, "is_anomaly": bool(r["is_anomaly"])}) for r in rows]


@router.post("/import", response_model=ImportResult)
async def import_transactions(file: UploadFile = File(...)) -> ImportResult:
    """Importa transacciones en lote desde CSV o JSON.

    CSV: cabeceras user_id, description, amount, [date].
    JSON: lista de objetos con esas mismas claves.
    Cada fila pasa por el pipeline completo (anonimizar/clasificar/anomalia/guardar).
    """
    raw = (await file.read()).decode("utf-8", errors="replace")
    name = (file.filename or "").lower()

    if name.endswith(".json") or raw.lstrip().startswith(("[", "{")):
        records = _parse_json(raw)
    else:
        records = _parse_csv(raw)

    processed = 0
    anomalies = 0
    errors: list[str] = []

    for i, rec in enumerate(records):
        try:
            row = process_transaction(
                user_id=str(rec["user_id"]),
                description=str(rec.get("description", "")),
                amount=float(rec["amount"]),
                date=rec.get("date") or None,
            )
            processed += 1
            if row["is_anomaly"]:
                anomalies += 1
        except (KeyError, ValueError, TypeError) as e:
            errors.append(f"fila {i}: {e}")

    return ImportResult(
        received=len(records), processed=processed, anomalies=anomalies, errors=errors
    )


def _parse_json(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON invalido: {e}")
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="Se esperaba lista de objetos JSON")
    return data


def _parse_csv(raw: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)
