"""Orquestacion del procesamiento de una transaccion.

Pipeline unico reutilizado por POST /transactions y POST /transactions/import:
    anonimizar -> clasificar -> detectar anomalia -> persistir.

Mantener la logica aqui evita duplicarla entre endpoints.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from api.db import queries
from core.anomalies import detect_subscription_change, detect_zscore_anomaly
from core.anonymization import anonymize
from core.classify import classify

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_transaction(
    user_id: str, description: str, amount: float, date: str | None = None
) -> dict[str, Any]:
    """Procesa y persiste una transaccion cruda. Devuelve la fila resultante (dict).

    Pasos:
      1. asegura que el usuario existe.
      2. anonimiza la descripcion (RGPD) antes de clasificar/guardar.
      3. clasifica sobre el texto anonimizado.
      4. detecta anomalia frente al historico de esa categoria.
      5. inserta en SQLite.
    """
    queries.ensure_user(user_id)

    desc_anon, entities = anonymize(description)
    if entities:
        logger.info("anonimizacion user=%s entidades=%s", user_id, entities)
    clf = classify(desc_anon, amount)
    category = clf["categoria"]

    history = queries.get_category_history(user_id, category)
    is_anomaly, reason = detect_zscore_anomaly(amount, category, history)

    if not is_anomaly:
        merchant_history = queries.get_merchant_history(user_id, desc_anon)
        is_anomaly, reason = detect_subscription_change(desc_anon, amount, merchant_history)

    row: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "user_id": user_id,
        "description_raw": description,
        "description_anonymized": desc_anon,
        "amount": amount,
        "category": category,
        "confidence": clf["confianza"],
        "classification_level": clf["nivel_usado"],
        "is_anomaly": 1 if is_anomaly else 0,
        "anomaly_reason": reason or None,
        "created_at": date or _now_iso(),
    }
    queries.insert_transaction(row)

    # Normalizar el bool para la respuesta de la API.
    row["is_anomaly"] = bool(row["is_anomaly"])
    return row
