"""Tests de los detectores de anomalias con casos sinteticos."""

from __future__ import annotations


from core.anomalies import detect_subscription_change, detect_zscore_anomaly

# --- detect_zscore_anomaly ------------------------------------------------


def test_zscore_sin_historico():
    es_anomalia, _ = detect_zscore_anomaly(50.0, "alimentacion", [])
    assert not es_anomalia


def test_zscore_historico_insuficiente_sin_salto():
    """Con pocos datos y sin salto extremo, no es anomalia."""
    es_anomalia, _ = detect_zscore_anomaly(60.0, "alimentacion", [50.0, 55.0, 52.0])
    assert not es_anomalia


def test_zscore_historico_insuficiente_con_salto():
    """Con pocos datos y salto >= 4x el maximo, es anomalia."""
    es_anomalia, razon = detect_zscore_anomaly(800.0, "alimentacion", [50.0, 55.0, 60.0])
    assert es_anomalia
    assert "maximo historico" in razon


def test_zscore_normal_dentro_de_banda():
    # historico con media ~30 y desv ~3; 32 queda en z~0.7 -> no anomalia
    historico = [25.0, 35.0, 30.0, 28.0, 32.0, 27.0, 33.0]
    es_anomalia, _ = detect_zscore_anomaly(32.0, "alimentacion", historico)
    assert not es_anomalia


def test_zscore_outlier_alto():
    """Importe muy por encima de la media -> anomalia."""
    historico = [25.0, 35.0, 30.0, 28.0, 32.0, 27.0, 33.0]
    es_anomalia, razon = detect_zscore_anomaly(500.0, "alimentacion", historico)
    assert es_anomalia
    assert "sigma" in razon


def test_zscore_sigma_cero_importe_igual():
    """Todos iguales y nuevo importe igual -> no es anomalia."""
    historico = [50.0] * 6
    es_anomalia, _ = detect_zscore_anomaly(50.0, "suscripciones", historico)
    assert not es_anomalia


def test_zscore_sigma_cero_importe_distinto():
    """Todos iguales pero nuevo importe diferente -> anomalia."""
    historico = [50.0] * 6
    es_anomalia, razon = detect_zscore_anomaly(80.0, "suscripciones", historico)
    assert es_anomalia
    assert "constante historico" in razon


def test_zscore_razon_incluye_categoria():
    historico = [25.0, 35.0, 30.0, 28.0, 32.0, 27.0, 33.0]
    _, razon = detect_zscore_anomaly(500.0, "restauracion", historico)
    assert "restauracion" in razon


# --- detect_subscription_change -------------------------------------------


def test_suscripcion_sin_historico():
    es_anomalia, _ = detect_subscription_change("NETFLIX SUSCRIPCION", -13.99, [])
    assert not es_anomalia


def test_suscripcion_historico_insuficiente():
    es_anomalia, _ = detect_subscription_change("NETFLIX SUSCRIPCION", -13.99, [-13.99, -13.99])
    assert not es_anomalia


def test_suscripcion_estable():
    historico = [-13.99, -13.99, -13.99, -13.99]
    es_anomalia, _ = detect_subscription_change("NETFLIX SUSCRIPCION", -13.99, historico)
    assert not es_anomalia


def test_suscripcion_cambio_menor_umbral():
    """Variacion <10% no es anomalia."""
    historico = [-13.99, -13.99, -13.99]
    es_anomalia, _ = detect_subscription_change("NETFLIX SUSCRIPCION", -14.50, historico)
    assert not es_anomalia


def test_suscripcion_cambio_mayor_umbral():
    """Subida del 40% del precio -> anomalia."""
    historico = [-13.99, -13.99, -13.99, -13.99]
    es_anomalia, razon = detect_subscription_change("NETFLIX SUSCRIPCION", -19.59, historico)
    assert es_anomalia
    assert "NETFLIX" in razon


def test_suscripcion_bajada_precio():
    """Bajada significativa tambien es anomalia (puede indicar cambio de plan)."""
    historico = [-13.99, -13.99, -13.99, -13.99]
    es_anomalia, _ = detect_subscription_change("NETFLIX SUSCRIPCION", -7.99, historico)
    assert es_anomalia


def test_suscripcion_historico_mu_cero():
    """Si la media historica es 0, no puede calcularse desviacion -> no anomalia."""
    es_anomalia, _ = detect_subscription_change("DESC", 0.0, [0.0, 0.0, 0.0])
    assert not es_anomalia
