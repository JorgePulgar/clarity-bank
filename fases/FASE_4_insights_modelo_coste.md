# Fase 4 — Insights mensuales + integracion del modelo real + panel de coste

**Estado:** COMPLETADA
**Objetivo:** insights mensuales ricos vía LLM, enchufe del clasificador real, y visibilidad
del coste de la demo.

> Base ya existente: `core/insights.py` con `aggregate_month` y `generate_insight`.
> Cliente Azure ya cableado. `core/classify.py` ya detecta el modelo real y cae
> al mock si no existe.

## Tareas

- [x] Cliente Azure OpenAI (Sweden Central) configurado desde `.env`.
- [x] `POST /insights/generate` conectado al pipeline de insights.
- [x] El prompt recibe SOLO agregados anonimizados (nunca transacciones con PII).
- [x] Ampliar `aggregate_month`: variacion % vs mes anterior, suscripciones nuevas/canceladas,
      anomalias del mes, dia de mas gasto, comercio mas frecuente.
- [x] Mejorar prompt: SYSTEM_PROMPT pide 3-4 parrafos; `_build_prompt` incluye todos los nuevos
      campos; `_template_insight` tambien los usa.
- [x] Integracion del modelo real: flag `USE_MOCK_CLASSIFIER` en `.env.example` leido directamente
      en `core/classify.py`. Documentado en codigo.
- [x] Panel de coste en Streamlit (sidebar, visible siempre): n_transactions, n_llm_calls,
      n_insights, coste estimado EUR. Nuevo endpoint `GET /users/{id}/cost-stats`.
      Tabla `insight_calls` en SQLite para persistir cada llamada.

## Criterio de done

Importar historico de demo-user, llamar a `/insights/generate` con `{user_id, month}`,
recibir texto coherente de 3-4 parrafos, y ver el coste de esa llamada en el panel. **Cumplido.**
