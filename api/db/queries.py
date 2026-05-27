"""Operaciones CRUD sobre SQLite. Sin logica de negocio: solo lee/escribe."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from api.db.database import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- users -----------------------------------------------------------------

def ensure_user(user_id: str) -> None:
    """Crea el usuario si no existe (no falla si ya existe)."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, created_at) VALUES (?, ?)",
            (user_id, _now()),
        )


def user_exists(user_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
    return row is not None


# --- transactions ----------------------------------------------------------

def insert_transaction(tx: dict[str, Any]) -> None:
    """Inserta una transaccion ya procesada (anonimizada + clasificada).

    `tx` debe traer todas las columnas de la tabla transactions.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO transactions (
                id, user_id, description_raw, description_anonymized,
                amount, category, confidence, classification_level,
                is_anomaly, anomaly_reason, created_at
            ) VALUES (
                :id, :user_id, :description_raw, :description_anonymized,
                :amount, :category, :confidence, :classification_level,
                :is_anomaly, :anomaly_reason, :created_at
            )
            """,
            tx,
        )


def get_transactions_by_user(user_id: str, limit: int = 500) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_transactions_by_month(user_id: str, month: str) -> list[dict[str, Any]]:
    """Transacciones de un mes concreto. `month` en formato 'YYYY-MM'."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM transactions
            WHERE user_id = ? AND substr(created_at, 1, 7) = ?
            ORDER BY created_at ASC
            """,
            (user_id, month),
        ).fetchall()
    return [dict(r) for r in rows]


def get_category_history(user_id: str, category: str) -> list[float]:
    """Importes historicos del usuario en una categoria (para z-score de anomalias)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT amount FROM transactions WHERE user_id = ? AND category = ?",
            (user_id, category),
        ).fetchall()
    return [r["amount"] for r in rows]


def get_merchant_history(user_id: str, description_anonymized: str) -> list[float]:
    """Importes historicos del usuario para un comercio concreto (match exacto en descripcion anonimizada)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT amount FROM transactions WHERE user_id = ? AND description_anonymized = ?",
            (user_id, description_anonymized),
        ).fetchall()
    return [r["amount"] for r in rows]


def get_user_stats(user_id: str) -> dict[str, Any]:
    """Agregados basicos para el dashboard: totales y desglose por categoria."""
    with get_connection() as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*)                                    AS n_transactions,
                COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS total_gastos,
                COALESCE(SUM(CASE WHEN amount > 0 THEN  amount ELSE 0 END), 0) AS total_ingresos,
                COALESCE(SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END), 0)       AS n_anomalies
            FROM transactions WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        by_cat = conn.execute(
            """
            SELECT category,
                   COUNT(*)             AS n,
                   COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = ?
            GROUP BY category
            ORDER BY ABS(SUM(amount)) DESC
            """,
            (user_id,),
        ).fetchall()

    return {
        "user_id": user_id,
        "n_transactions": totals["n_transactions"],
        "total_gastos": round(totals["total_gastos"], 2),
        "total_ingresos": round(totals["total_ingresos"], 2),
        "n_anomalies": totals["n_anomalies"],
        "by_category": [dict(r) for r in by_cat],
    }
