"""Anonimizacion de descripciones antes de persistir o enviar al LLM.

RGPD: ningun dato personal sale de la infra sin anonimizar (ver CLAUDE.md).

Dos capas:
  1. Regex propio para PII tipica de banca espanola (IBAN, tarjeta, DNI/NIE, email,
     telefono, nombres tras marcadores, cuentas enmascaradas). Determinista, sin
     dependencias, siempre activo.
  2. Presidio (NER) para nombres de persona y otras entidades. OPCIONAL: si presidio
     o el modelo spacy no estan instalados, se omite esta capa y se sigue con regex.

Asi la API arranca aunque presidio no este disponible (p.ej. sin wheel para 3.14).

La funcion publica `anonymize` devuelve (texto_anonimizado, entidades) donde
entidades es un dict tipo -> nº ocurrencias, sin exponer el valor original.
"""

from __future__ import annotations

import re
from typing import Optional

# --- Capa 1: regex --------------------------------------------------------

_REGEX_RULES: list[tuple[re.Pattern, str]] = [
    # IBAN espanol: ES + 22 digitos (con o sin espacios)
    (re.compile(r"\bES\d{2}[\s]?(?:\d{4}[\s]?){5}\b", re.I), "<IBAN>"),
    # Tarjeta: 13-16 digitos, posibles separadores
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "<TARJETA>"),
    # DNI (8 digitos + letra) / NIE (X|Y|Z + 7 digitos + letra)
    (re.compile(r"\b[XYZ]?\d{7,8}[A-Z]\b", re.I), "<DNI>"),
    # Email
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<EMAIL>"),
    # Telefono espanol: +34 opcional + 9 digitos empezando 6/7/8/9
    (re.compile(r"\b(?:\+34[\s-]?)?[6789]\d{2}[\s-]?\d{3}[\s-]?\d{3}\b"), "<TELEFONO>"),
    # Nombres de persona tras marcadores de banca (DE/A opcional, mayusculas/minusculas)
    # TRA(?:N)?SFERENCIA cubre tanto TRANSFERENCIA como TRASFERENCIA (typo comun)
    (
        re.compile(
            r"((?:BIZUM|TRA(?:N)?SFERENCIA)\s+(?:(?:DE|A)\s+)?)"
            r"[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜa-záéíóúñü]+(?:\s+[A-ZÁÉÍÓÚÑÜa-záéíóúñü]+){1,3}",
            re.UNICODE | re.IGNORECASE,
        ),
        r"\1<PERSONA>",
    ),
    # Cuenta parcialmente enmascarada: *****1234
    (re.compile(r"\*{2,}\d{4,}"), "<CUENTA>"),
]

# Extrae el nombre de entidad del tag (soporta "<IBAN>" y r"\1 <PERSONA>")
_TAG_NAME_RE = re.compile(r"<([A-Z]+)>")


def _regex_anonymize(text: str) -> tuple[str, dict[str, int]]:
    """Aplica todas las reglas regex y devuelve (texto, conteo de entidades)."""
    entities: dict[str, int] = {}
    for pattern, tag in _REGEX_RULES:
        matches = list(pattern.finditer(text))
        if matches:
            m = _TAG_NAME_RE.search(tag)
            if m:
                et = m.group(1)
                entities[et] = entities.get(et, 0) + len(matches)
            text = pattern.sub(tag, text)
    return text, entities


# --- Capa 2: Presidio (lazy, opcional) ------------------------------------

_analyzer = None  # presidio AnalyzerEngine | None
_anonymizer = None  # presidio AnonymizerEngine | None
_presidio_ready: Optional[bool] = None  # None = aun no intentado


def _init_presidio() -> bool:
    """Inicializa Presidio una sola vez. Devuelve False si no esta disponible."""
    global _analyzer, _anonymizer, _presidio_ready
    if _presidio_ready is not None:
        return _presidio_ready

    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine

        from api.config import settings

        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "es", "model_name": settings.presidio_spacy_model}],
            }
        )
        _analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["es"])
        _anonymizer = AnonymizerEngine()
        _presidio_ready = True
    except Exception:
        # Falta presidio, spacy o el modelo. Seguimos solo con regex.
        _presidio_ready = False

    return _presidio_ready


# Solo PII real. Excluye ORGANIZATION/LOCATION/GPE: son nombres de comercio,
# no datos personales, y son la señal clave para el clasificador.
_PII_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "IBAN_CODE",
    "CREDIT_CARD", "CRYPTO", "URL", "IP_ADDRESS",
]

# Palabras clave bancarias que NO deben convertirse a title case antes del NER
# (evita que spacy las confunda con nombres propios).
_BANKING_KEYWORDS = frozenset({
    "TRANSFERENCIA", "TRASFERENCIA", "BIZUM", "PAGO", "CARGO", "RECIBO",
    "NOMINA", "ABONO", "INGRESO", "REINTEGRO", "COMPRA", "COBRO",
    "TARJETA", "CUOTA", "FACTURA", "MOVIMIENTO", "CONCEPTO", "TRASPASO",
    "DE", "A", "AL", "DEL", "EN", "POR", "CON", "SL", "SA", "SLU",
})


def _to_ner_case(text: str) -> str:
    """Title case para NER manteniendo palabras clave bancarias en mayusculas."""
    return " ".join(
        w if w.upper() in _BANKING_KEYWORDS else w.capitalize()
        for w in text.split()
    )


def _presidio_anonymize(text: str) -> tuple[str, dict[str, int]]:
    """Aplica Presidio NER (solo PII) y devuelve (texto, conteo de entidades detectadas).

    Convierte a title case para el analisis NER: spacy detecta mejor nombres propios
    en texto mixto que en MAYUSCULAS. Las posiciones de span se conservan (title()
    no cambia la longitud), por lo que la anonimizacion se aplica sobre el texto original.
    """
    text_for_ner = _to_ner_case(text)
    results = _analyzer.analyze(text=text_for_ner, language="es", entities=_PII_ENTITIES)  # type: ignore[union-attr]
    entities: dict[str, int] = {}
    for r in results:
        entities[r.entity_type] = entities.get(r.entity_type, 0) + 1
    from presidio_anonymizer.entities import OperatorConfig
    operators = {"PERSON": OperatorConfig("replace", {"new_value": "<PERSONA>"})}
    out = _anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)  # type: ignore[union-attr]
    return out.text, entities


# --- API publica ----------------------------------------------------------


def anonymize(text: str) -> tuple[str, dict[str, int]]:
    """Anonimiza texto y devuelve (texto_anonimizado, entidades).

    entidades: dict tipo_entidad -> nº_ocurrencias. Nunca expone el valor original.
    Aplica siempre regex; aplica Presidio encima si esta disponible.
    Idempotente sobre texto ya anonimizado.
    """
    if not text:
        return text, {}
    out, entities = _regex_anonymize(text)
    if _init_presidio():
        try:
            out, presidio_entities = _presidio_anonymize(out)
            for k, v in presidio_entities.items():
                entities[k] = entities.get(k, 0) + v
        except Exception:
            pass  # ante cualquier fallo de NER, nos quedamos con el resultado regex
    return out, entities


def presidio_available() -> bool:
    """True si la capa Presidio esta operativa (para diagnostico/dashboard)."""
    return _init_presidio()
