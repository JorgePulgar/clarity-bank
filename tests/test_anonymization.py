"""Tests de anonimizacion. Cubre los 12 tipos de PII y casos borde."""

from __future__ import annotations


from core.anonymization import anonymize


def anon(text: str) -> str:
    """Devuelve solo el texto anonimizado (ignora el dict de entidades)."""
    return anonymize(text)[0]


def entities(text: str) -> dict[str, int]:
    """Devuelve solo el dict de entidades detectadas."""
    return anonymize(text)[1]


# --- Casos de sustitucion -------------------------------------------------


def test_iban():
    resultado = anon("Transferencia recibida de ES2114650100722030876293")
    assert "<IBAN>" in resultado
    assert "ES21" not in resultado


def test_dni():
    resultado = anon("Identificacion del cliente: 12345678A")
    assert "<DNI>" in resultado
    assert "12345678A" not in resultado


def test_nie():
    resultado = anon("NIE del titular: X1234567L")
    assert "<DNI>" in resultado
    assert "X1234567L" not in resultado


def test_email():
    resultado = anon("Contacto soporte en juan.garcia@banco.es")
    assert "<EMAIL>" in resultado
    assert "juan.garcia" not in resultado


def test_telefono():
    resultado = anon("Llamada desde 612 345 678")
    assert "<TELEFONO>" in resultado
    assert "612" not in resultado


def test_telefono_con_prefijo():
    resultado = anon("Contacto: +34 699123456")
    assert "<TELEFONO>" in resultado


def test_cuenta_enmascarada():
    resultado = anon("Cargo en cuenta *****1234")
    assert "<CUENTA>" in resultado
    assert "*****1234" not in resultado


def test_bizum_de():
    resultado = anon("BIZUM DE Juan Garcia")
    assert "<PERSONA>" in resultado
    assert "BIZUM DE" in resultado
    assert "Juan" not in resultado


def test_transferencia_de():
    resultado = anon("TRANSFERENCIA DE Maria Lopez Ruiz")
    assert "<PERSONA>" in resultado
    assert "TRANSFERENCIA DE" in resultado
    assert "Maria" not in resultado


def test_transferencia_a():
    resultado = anon("TRANSFERENCIA A Pedro Martinez")
    assert "<PERSONA>" in resultado
    assert "TRANSFERENCIA A" in resultado
    assert "Pedro" not in resultado


# --- Texto sin PII --------------------------------------------------------


def test_texto_limpio():
    texto = "Compra supermercado Mercadona 45.20 EUR"
    assert anon(texto) == texto


def test_texto_vacio():
    texto, ents = anonymize("")
    assert texto == ""
    assert ents == {}


# --- Dict de entidades ----------------------------------------------------


def test_dict_iban():
    ents = entities("Pago a ES2114650100722030876293")
    assert ents.get("IBAN") == 1


def test_dict_multiples_pii():
    texto = "Email: test@test.com y DNI 87654321Z"
    ents = entities(texto)
    assert ents.get("EMAIL") == 1
    assert ents.get("DNI") == 1


def test_dict_persona():
    ents = entities("BIZUM DE Ana Torres")
    assert ents.get("PERSONA") == 1


# --- Idempotencia ---------------------------------------------------------


def test_idempotencia():
    texto = "BIZUM DE Juan Garcia IBAN ES2114650100722030876293"
    primera, _ = anonymize(texto)
    segunda, _ = anonymize(primera)
    assert primera == segunda
