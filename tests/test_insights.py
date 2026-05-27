"""Tests de insights: agregacion, plantilla y ruta LLM mockeada."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

import pytest

import api.config as cfg_mod
from core.insights import aggregate_month, generate_insight

# ---------------------------------------------------------------------------
# Fixtures de datos
# ---------------------------------------------------------------------------

TX_MES = [
    {
        "amount": -43.27,
        "category": "alimentacion",
        "description_anonymized": "MERCADONA MADRID",
        "created_at": "2026-04-05T10:00:00",
        "is_anomaly": False,
        "anomaly_reason": None,
    },
    {
        "amount": -12.99,
        "category": "suscripciones",
        "description_anonymized": "NETFLIX SUSCRIPCION",
        "created_at": "2026-04-05T11:00:00",
        "is_anomaly": False,
        "anomaly_reason": None,
    },
    {
        "amount": 2000.0,
        "category": "ingresos",
        "description_anonymized": "ABONO NOMINA",
        "created_at": "2026-04-01T08:00:00",
        "is_anomaly": False,
        "anomaly_reason": None,
    },
    {
        "amount": -1450.0,
        "category": "compras",
        "description_anonymized": "AMAZON COMPRA ONLINE",
        "created_at": "2026-04-20T15:00:00",
        "is_anomaly": True,
        "anomaly_reason": "Gasto 1450.0 a 4.7 sigma de la media.",
    },
]

TX_MES_PREV = [
    {
        "amount": -50.0,
        "category": "alimentacion",
        "description_anonymized": "MERCADONA MADRID",
        "created_at": "2026-03-05T10:00:00",
        "is_anomaly": False,
        "anomaly_reason": None,
    },
    {
        "amount": -12.99,
        "category": "suscripciones",
        "description_anonymized": "NETFLIX SUSCRIPCION",
        "created_at": "2026-03-05T11:00:00",
        "is_anomaly": False,
        "anomaly_reason": None,
    },
]


# ---------------------------------------------------------------------------
# aggregate_month
# ---------------------------------------------------------------------------


def test_aggregate_sin_transacciones():
    agg = aggregate_month([])
    assert agg["n_transactions"] == 0
    assert agg["total_gasto"] == 0.0
    assert agg["top_categorias"] == []


def test_aggregate_totales():
    agg = aggregate_month(TX_MES)
    assert agg["n_transactions"] == 4
    assert agg["total_ingreso"] == 2000.0
    assert agg["total_gasto"] == pytest.approx(43.27 + 12.99 + 1450.0)


def test_aggregate_anomalias():
    agg = aggregate_month(TX_MES)
    assert len(agg["anomalias"]) == 1
    assert "4.7 sigma" in agg["anomalias"][0]


def test_aggregate_top_categorias_ordenadas():
    agg = aggregate_month(TX_MES)
    tops = [t["categoria"] for t in agg["top_categorias"]]
    assert tops[0] == "compras"  # 1450 EUR es el mayor gasto


def test_aggregate_suscripciones_nuevas():
    agg = aggregate_month(TX_MES, TX_MES_PREV)
    assert agg["variacion_gasto_pct"] is not None


def test_aggregate_variacion_positiva():
    """Mes actual mas gasto que el anterior -> variacion > 0."""
    agg = aggregate_month(TX_MES, TX_MES_PREV)
    assert agg["variacion_gasto_pct"] > 0


def test_aggregate_sin_previo_no_variacion():
    agg = aggregate_month(TX_MES)
    assert agg["variacion_gasto_pct"] is None


# ---------------------------------------------------------------------------
# generate_insight — ruta template
# ---------------------------------------------------------------------------


def test_generate_insight_template_sin_transacciones():
    texto, source, tokens = generate_insight("2026-04", [])
    assert source == "template"
    assert tokens is None
    assert "No hay movimientos" in texto


def test_generate_insight_template_con_transacciones():
    texto, source, tokens = generate_insight("2026-04", TX_MES)
    assert source == "template"
    assert tokens is None
    assert "2026-04" in texto
    assert "compras" in texto.lower() or "alimentacion" in texto.lower()


def test_generate_insight_template_incluye_anomalias():
    texto, _, _ = generate_insight("2026-04", TX_MES)
    assert "atipico" in texto.lower()


# ---------------------------------------------------------------------------
# generate_insight — ruta LLM mockeada
# ---------------------------------------------------------------------------


def _patch_llm_enabled():
    """Context manager que fuerza settings.llm_enabled=True parcheando la property."""
    return patch.object(
        type(cfg_mod.settings), "llm_enabled", new_callable=PropertyMock, return_value=True
    )


def test_generate_insight_llm_llamado_cuando_habilitado():
    """Con LLM habilitado y mock de _llm_insight, se retorna source='llm'."""
    mock_tokens = {"prompt_tokens": 150, "completion_tokens": 80}
    with (
        _patch_llm_enabled(),
        patch(
            "core.insights._llm_insight",
            return_value=("Texto del LLM simulado.", mock_tokens),
        ) as mock_llm,
    ):
        texto, source, tokens = generate_insight("2026-04", TX_MES)

    assert source == "llm"
    assert texto == "Texto del LLM simulado."
    assert tokens == mock_tokens
    mock_llm.assert_called_once()


def test_generate_insight_llm_fallback_a_template_si_falla():
    """Si el LLM lanza excepcion, se cae al template transparentemente."""
    with (
        _patch_llm_enabled(),
        patch("core.insights._llm_insight", side_effect=RuntimeError("timeout")),
    ):
        texto, source, tokens = generate_insight("2026-04", TX_MES)

    assert source == "template"
    assert tokens is None
    assert texto


def test_generate_insight_llm_recibe_mes_correcto():
    """El mes se pasa correctamente a _llm_insight."""
    with (
        _patch_llm_enabled(),
        patch("core.insights._llm_insight", return_value=("ok", {})) as mock_llm,
    ):
        generate_insight("2026-06", TX_MES)

    args, _ = mock_llm.call_args
    assert args[0] == "2026-06"
