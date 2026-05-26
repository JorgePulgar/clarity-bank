"""Fixtures de test. Aisla la BD usando un fichero SQLite temporal."""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

# IMPORTANTE: fijar la ruta de BD ANTES de importar nada de api.* (settings se
# instancia al importar). Cada corrida usa un fichero nuevo y descartable.
_tmp_db = Path(tempfile.gettempdir()) / f"clarity_test_{uuid.uuid4().hex}.db"
os.environ["CLARITY_DB_PATH"] = str(_tmp_db)
# Sin credenciales -> insights por plantilla (no llama al LLM en tests).
os.environ["AZURE_OPENAI_ENDPOINT"] = ""
os.environ["AZURE_OPENAI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
from core import classify as classify_mod  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _force_mock_classifier():
    # Garantiza el mock (no depende de si existe modelo real).
    classify_mod.use_mock()
    yield
    if _tmp_db.exists():
        _tmp_db.unlink()


@pytest.fixture()
def client() -> TestClient:
    # El lifespan crea las tablas al entrar en el contexto.
    with TestClient(app) as c:
        yield c
