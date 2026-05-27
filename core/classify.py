"""Wrapper sobre el clasificador de transacciones.

Mi companera entrega el modelo real en models/load_classifier.py con la firma:

    load() -> Callable
    classify(description: str, amount: float) -> dict
        {"categoria": str, "confianza": float, "nivel_usado": int}

Mientras tanto, este modulo usa un MOCK basado en palabras clave. La sustitucion
es trivial: en cuanto exista models/load_classifier.py con load(), se usa ese.
Para forzar el mock en demos, llamar a use_mock().
"""

from __future__ import annotations

import os
from typing import Callable, Optional

# Categorias validas (espejo de schemas.Categoria; aqui sin dependencia para evitar ciclo).
CATEGORIAS = {
    "alimentacion",
    "restauracion",
    "transporte",
    "ocio",
    "compras",
    "hogar",
    "salud",
    "suscripciones",
    "transferencias",
    "ingresos",
    "impuestos_tasas",
    "otros",
}

# Reglas del mock: subcadena (mayusculas) -> categoria. Orden = prioridad.
_MOCK_RULES: list[tuple[str, str]] = [
    ("MERCADONA", "alimentacion"),
    ("CARREFOUR", "alimentacion"),
    ("LIDL", "alimentacion"),
    ("DIA", "alimentacion"),
    ("ALCAMPO", "alimentacion"),
    ("MCDONALD", "restauracion"),
    ("BURGER", "restauracion"),
    ("RESTAURANTE", "restauracion"),
    ("BAR ", "restauracion"),
    ("CAFE", "restauracion"),
    ("GLOVO", "restauracion"),
    ("UBER EATS", "restauracion"),
    ("UBER", "transporte"),
    ("CABIFY", "transporte"),
    ("RENFE", "transporte"),
    ("METRO", "transporte"),
    ("EMT", "transporte"),
    ("REPSOL", "transporte"),
    ("CEPSA", "transporte"),
    ("GASOLINERA", "transporte"),
    ("PARKING", "transporte"),
    ("NETFLIX", "suscripciones"),
    ("SPOTIFY", "suscripciones"),
    ("HBO", "suscripciones"),
    ("AMAZON PRIME", "suscripciones"),
    ("DISNEY", "suscripciones"),
    ("ICLOUD", "suscripciones"),
    ("CINE", "ocio"),
    ("TEATRO", "ocio"),
    ("STEAM", "ocio"),
    ("PLAYSTATION", "ocio"),
    ("ZARA", "compras"),
    ("AMAZON", "compras"),
    ("EL CORTE INGLES", "compras"),
    ("MEDIAMARKT", "compras"),
    ("PRIMARK", "compras"),
    ("IBERDROLA", "hogar"),
    ("ENDESA", "hogar"),
    ("NATURGY", "hogar"),
    ("MOVISTAR", "hogar"),
    ("VODAFONE", "hogar"),
    ("ORANGE", "hogar"),
    ("ALQUILER", "hogar"),
    ("COMUNIDAD", "hogar"),
    ("FARMACIA", "salud"),
    ("CLINICA", "salud"),
    ("HOSPITAL", "salud"),
    ("DENTISTA", "salud"),
    ("SANITAS", "salud"),
    ("TRANSFERENCIA", "transferencias"),
    ("BIZUM", "transferencias"),
    ("NOMINA", "ingresos"),
    ("SALARIO", "ingresos"),
    ("ABONO", "ingresos"),
    ("AEAT", "impuestos_tasas"),
    ("HACIENDA", "impuestos_tasas"),
    ("IMPUESTO", "impuestos_tasas"),
    ("TASA", "impuestos_tasas"),
]


def _mock_classify(description: str, amount: float) -> dict:
    """Clasificador de relleno por palabras clave. Datos realistas, deterministas."""
    desc = (description or "").upper()

    for needle, cat in _MOCK_RULES:
        if needle in desc:
            # nivel 1 = local; confianza alta para coincidencia directa
            return {"categoria": cat, "confianza": 0.92, "nivel_usado": 1}

    # Heuristica de respaldo: ingreso positivo sin match -> 'ingresos'
    if amount > 0:
        return {"categoria": "ingresos", "confianza": 0.55, "nivel_usado": 1}

    # Sin match -> caso dificil que en produccion iria al LLM (nivel 2)
    return {"categoria": "otros", "confianza": 0.40, "nivel_usado": 2}


def _load_real() -> Optional[Callable[[str, float], dict]]:
    """Intenta cargar el clasificador real de mi companera. None si aun no existe."""
    try:
        from models.load_classifier import load  # type: ignore
    except Exception:
        return None
    try:
        fn = load()
        return fn if callable(fn) else None
    except Exception:
        # El modelo existe pero fallo al cargar (p.ej. falta el .pkl). Caemos al mock.
        return None


# USE_MOCK_CLASSIFIER=1|true|yes fuerza el mock aunque exista el modelo real.
# Util para demos y tests sin necesidad de llamar a use_mock() explicitamente.
_FORCE_MOCK = os.getenv("USE_MOCK_CLASSIFIER", "").lower() in ("1", "true", "yes")

# Se resuelve una vez al importar. _classifier=None -> usar mock.
_classifier: Optional[Callable[[str, float], dict]] = None if _FORCE_MOCK else _load_real()


def use_mock() -> None:
    """Fuerza el uso del mock (util en tests y demos sin modelo)."""
    global _classifier
    _classifier = None


def using_real_model() -> bool:
    """True si esta activo el clasificador real (no el mock)."""
    return _classifier is not None


def classify(description: str, amount: float) -> dict:
    """Clasifica una transaccion en una de las 12 categorias.

    Args:
        description: texto (idealmente ya anonimizado) del movimiento.
        amount: importe; negativo gasto, positivo ingreso.

    Returns:
        dict con claves: categoria (str), confianza (float 0-1), nivel_usado (int 1|2).
        La categoria siempre pertenece a CATEGORIAS; si el modelo devuelve algo
        fuera de la lista, se normaliza a 'otros'.
    """
    fn = _classifier or _mock_classify
    result = fn(description, amount)

    if result.get("categoria") not in CATEGORIAS:
        result["categoria"] = "otros"
    result.setdefault("confianza", 0.0)
    result.setdefault("nivel_usado", 1)
    return result
