"""Punto de entrega del clasificador real (lo rellena mi companera de ML).

Contrato esperado por core/classify.py:

    def load() -> Callable[[str, float], dict]:
        '''Carga el modelo serializado y devuelve la funcion classify lista para usar.'''

    def classify(description: str, amount: float) -> dict:
        return {
            "categoria": str,    # una de las 12 categorias (ver CLAUDE.md)
            "confianza": float,  # 0.0 - 1.0
            "nivel_usado": int,  # 1 = clasificador local, 2 = LLM
        }

MIENTRAS NO ESTE LISTO: load() lanza NotImplementedError a proposito. core/classify.py
captura la excepcion y usa el mock automaticamente. No hace falta tocar nada mas:
en cuanto este modulo implemente load() devolviendo un callable, el sistema lo usara.
"""

from __future__ import annotations

from typing import Callable


def load() -> Callable[[str, float], dict]:
    """Carga el modelo y devuelve la funcion classify. Lanza NotImplementedError hasta que ML lo implemente."""
    raise NotImplementedError(
        "Clasificador real aun no entregado. core/classify.py usa el mock por defecto."
    )
