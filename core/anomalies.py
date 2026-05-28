"""Deteccion de anomalias sobre el historico del usuario.

Dos detectores independientes:
  1. z-score por categoria: importe estadisticamente atipico para esa categoria.
  2. cambio de suscripcion: comercio recurrente cuyo importe cambia >10%.

Diseno para demo: simple, explicable y defendible oralmente. Sin ML.
"""

from __future__ import annotations

from statistics import mean, pstdev

# Umbrales z-score
Z_THRESHOLD = 3.0  # |z| > 3.0 -> regla 3-sigma, cola del 0.13% por lado
MIN_SAMPLES = 10  # minimo de muestras para que z sea fiable
JUMP_FACTOR = 5.0  # fallback con pocos datos: importe >= 5x maximo historico

# Umbrales suscripcion
MIN_SUBSCRIPTION_SAMPLES = 3  # pagos previos minimos para activar el detector
SUBSCRIPTION_CHANGE_THRESHOLD = 0.10  # 10% de desviacion sobre la media


def detect_zscore_anomaly(amount: float, category: str, history: list[float]) -> tuple[bool, str]:
    """Detecta anomalia por z-score del importe frente al historico de la categoria.

    Con menos de MIN_SAMPLES datos usa un salto sobre el maximo como fallback.

    Args:
        amount: importe de la transaccion nueva.
        category: categoria asignada por el clasificador.
        history: importes previos del usuario en esa categoria (sin el actual).

    Returns:
        (is_anomaly, reason). reason="" si no es anomalia.
    """
    magnitude = abs(amount)
    hist = [abs(x) for x in history]

    if len(hist) < MIN_SAMPLES:
        if hist:
            techo = max(hist)
            if techo > 0 and magnitude >= techo * JUMP_FACTOR:
                return True, (
                    f"Importe {magnitude:.2f} muy superior al maximo historico "
                    f"({techo:.2f}) en '{category}' con pocos datos previos."
                )
        return False, ""

    mu = mean(hist)
    sigma = pstdev(hist)

    if sigma == 0:
        if magnitude != mu:
            return True, (
                f"Importe {magnitude:.2f} difiere del valor constante historico "
                f"({mu:.2f}) en '{category}'."
            )
        return False, ""

    z = (magnitude - mu) / sigma
    if abs(z) >= Z_THRESHOLD:
        return True, (
            f"Gasto {magnitude:.2f} en '{category}' a {z:.1f} sigma de la media "
            f"({mu:.2f}, desv {sigma:.2f})."
        )
    return False, ""


def detect_subscription_change(
    description: str, amount: float, merchant_history: list[float]
) -> tuple[bool, str]:
    """Detecta cambio de importe en comercio recurrente (suscripciones, cuotas fijas).

    Solo activa con MIN_SUBSCRIPTION_SAMPLES o mas pagos previos al mismo comercio.
    Flagea si el importe actual se desvía mas de SUBSCRIPTION_CHANGE_THRESHOLD de la media.

    Args:
        description: descripcion anonimizada de la transaccion.
        amount: importe actual.
        merchant_history: importes previos del usuario para ese mismo comercio.

    Returns:
        (is_anomaly, reason). reason="" si no es anomalia.
    """
    if len(merchant_history) < MIN_SUBSCRIPTION_SAMPLES:
        return False, ""

    magnitudes = [abs(x) for x in merchant_history]
    current = abs(amount)
    mu = mean(magnitudes)

    if mu == 0:
        return False, ""

    desviacion = abs(current - mu) / mu
    if desviacion > SUBSCRIPTION_CHANGE_THRESHOLD:
        return True, (
            f"Importe {current:.2f} en '{description}' difiere {desviacion * 100:.0f}% "
            f"de la media historica del comercio ({mu:.2f})."
        )
    return False, ""


def detect_anomaly(amount: float, category: str, history: list[float]) -> tuple[bool, str]:
    """Fachada de compatibilidad hacia detect_zscore_anomaly. Pendiente de eliminar tras F3."""
    return detect_zscore_anomaly(amount, category, history)
