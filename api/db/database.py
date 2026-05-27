"""Conexion SQLite y creacion de esquema.

SQLite es deliberado: prototipo, no produccion (ver CLAUDE.md del proyecto).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from api.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id                      TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL REFERENCES users(id),
    description_raw         TEXT,
    description_anonymized  TEXT,
    amount                  REAL NOT NULL,
    category                TEXT,
    confidence              REAL,
    classification_level    INTEGER,   -- 1 = clasificador local, 2 = LLM
    is_anomaly              BOOLEAN DEFAULT 0,
    anomaly_reason          TEXT,
    created_at              TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_user   ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_tx_date   ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_tx_cat    ON transactions(category);

CREATE TABLE IF NOT EXISTS insight_calls (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES users(id),
    month             TEXT NOT NULL,
    source            TEXT NOT NULL,
    prompt_tokens     INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_eur          REAL DEFAULT 0,
    created_at        TIMESTAMP NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    # Sin detect_types: los timestamps se guardan/leen como texto ISO 8601 (lo que
    # produce/espera la API). PARSE_DECLTYPES activaria el conversor deprecado de 3.12+.
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row          # filas accesibles por nombre de columna
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Context manager: commit al salir bien, rollback si hay excepcion."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Crea las tablas si no existen. Idempotente; se llama al arrancar la API."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
