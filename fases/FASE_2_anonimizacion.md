# Fase 2 — Anonimizacion RGPD

**Estado:** EN CURSO (base hecha en fase 1)
**Objetivo:** pipeline de anonimizacion robusto y verificable. Ningun dato personal se
persiste crudo en campos anonimizados ni sale al LLM.

> Base ya existente (`core/anonymization.py`): regex para IBAN ES, tarjeta, DNI/NIE, email,
> telefono + capa Presidio (NER es) opcional con degradacion a solo-regex. Integrado en el
> pipeline (`api/service.py`) antes de clasificar y guardar.

## Tareas

- [x] `core/anonymization.py` con regex base + Presidio opcional (degrada a regex).
- [x] Anonimizacion integrada en el pipeline antes de clasificar/guardar.
- [x] Cambiar firma a `anonymize(text) -> tuple[str, dict]` devolviendo tambien el dict de
      entidades detectadas (tipo → nº ocurrencias), sin exponer el valor original. (c80ae22)
- [x] Regex para nombres de persona tras marcadores: `BIZUM DE`, `TRANSFERENCIA DE`,
      `TRANSFERENCIA A` → sustituir el nombre por `<PERSONA>`. (c80ae22)
- [x] Regex para cuentas parcialmente enmascaradas (`*****1234`) → `<CUENTA>`. (c80ae22)
- [x] Logging por request de **que** se anonimizo (tipos y conteos), nunca el dato original.
- [ ] Suite de tests con ≥10 casos representativos (BIZUM DE nombre, IBAN, DNI, email,
      telefono, cuenta enmascarada, texto sin PII, idempotencia, etc.).

## Criterio de done

Meter 10 transacciones distintas vía API: todas se anonimizan correctamente, se guardan,
se consultan con `GET`, y los tests de anonimizacion pasan.
