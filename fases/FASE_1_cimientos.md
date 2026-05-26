# Fase 1 — Cimientos del prototipo

**Estado:** COMPLETADA
**Objetivo:** estructura del repo + esqueleto funcional de punta a punta (API, BD, dashboard,
tests) para poder enviar una transaccion y ver el flujo conectado.

> Nota: esta fase se construyo de golpe en la sesion inicial. Ya incluye **persistencia real**
> (no mocks de BD) y un **mock de clasificador coherente** por palabras clave, lo que adelanta
> parte de las fases 2 y 3. Commit baseline: `chore: baseline fase 1`.

## Tareas

- [x] Estructura completa de carpetas segun el arbol del proyecto.
- [x] `requirements.txt` con dependencias minimas (API, dashboard, anonimizacion, LLM, tests).
- [x] `.gitignore` (Python + `.env` + `/models/*.pkl` + datos + `.claude`/`CLAUDE.md`/`MEMORIA.md`).
- [x] `.env.example` (Azure OpenAI, rutas BD, modelo spacy).
- [x] 5 endpoints FastAPI **reales** (no stubs): `POST /transactions`, `GET /transactions/{user_id}`,
      `POST /transactions/import`, `POST /insights/generate`, `GET /users/{user_id}/stats` + `/health`.
- [x] SQLite: esquema completo (`users`, `transactions`) + CRUD (`api/db/`).
- [x] Streamlit con 3 pantallas (transaccion, importar, insights) — version basica.
- [x] README inicial explicando la estructura.
- [x] Tests smoke: la API arranca y responde los 5 endpoints (7 tests, pasan).

## Criterio de done

Arrancar la API con `uvicorn`, abrir Streamlit, enviar una transaccion y ver el flujo
conectado de punta a punta. **Cumplido** (verificado tambien con `scripts/e2e_demo.py`).
