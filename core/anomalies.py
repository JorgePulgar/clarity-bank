"""Deteccion de anomalias sobre el historico del usuario.

Dos senales, ambas por categoria:
  1. z-score del importe frente a la media historica de esa categoria.
  2. importe muy superior al maximo historico (salto brusco) cuando hay pocos datos.

Diseno para demo: simple, explicable y defendible oralmente. No ML.
"""
from __future__ import annotations

from statistics import mean, pstdev

# Umbrales (ajustables). z>=3 = cola del 0.1%; suelo de muestras para que z sea fiable.
Z_THRESHOLD = 3.0
MIN_SAMPLES = 5
JUMP_FACTOR = 4.0          # importe >= 4x el maximo historico con pocos datos


def detect_anomaly(amount: float, category: str, history: list[float]) -> tuple[bool, str]:
    """Decide si `amount` es anomalo para `category` dado el historico del usuario.

    Args:
        amount: importe de la transaccion nueva.
        category: categoria asignada por el clasificador.
        history: importes previos del usuario en esa categoria (sin el actual).

    Returns:
        (is_anomaly, reason). reason="" si no es anomalia.
    """
    magnitude = abs(amount)
    hist = [abs(x) for x in history]

    # Sin historico suficiente -> no podemos afirmar anomalia con z-score.
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
        # Todos los importes previos identicos: cualquier desviacion clara es anomala.
        if magnitude != mu:
            return True, (
                f"Importe {magnitude:.2f} difiere del valor constante historico "
                f"({mu:.2f}) en '{category}'."
            )
        return False, ""

    z = (magnitude - mu) / sigma
    if z >= Z_THRESHOLD:
        return True, (
            f"Gasto {magnitude:.2f} en '{category}' a {z:.1f} sigma de la media "
            f"({mu:.2f}, desv {sigma:.2f})."
        )
    return False, ""
