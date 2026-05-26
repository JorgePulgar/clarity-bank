# Fase 4 — Insights mensuales + integracion del modelo real + panel de coste

**Estado:** PENDIENTE (base de insights hecha en fase 1)
**Objetivo:** insights mensuales ricos vía LLM, enchufe del clasificador real, y visibilidad
del coste de la demo.

> Base ya existente: `core/insights.py` con `aggregate_month` (total gasto/ingreso, balance,
> top 3 categorias, anomalias) y `generate_insight` (LLM Azure si hay credenciales, plantilla
> local si no). Cliente Azure ya cableado. `core/classify.py` ya detecta el modelo real y cae
> al mock si no existe.

## Tareas

- [x] Cliente Azure OpenAI (Sweden Central) configurado desde `.env`.
- [x] `POST /insights/generate` conectado al pipeline de insights.
- [x] El prompt recibe SOLO agregados anonimizados (nunca transacciones con PII).
- [ ] Ampliar `aggregate_user_month`: variacion % vs mes anterior, suscripciones nuevas/canceladas,
      anomalias del mes, dia de mas gasto, comercio mas frecuente.
- [ ] Mejorar el prompt para texto natural de 3-4 parrafos a partir de esos agregados.
- [ ] Integracion del modelo real: flag explicito `USE_MOCK_CLASSIFIER` en `.env` (mock como
      fallback aunque exista el modelo). Documentar en codigo.
- [ ] Panel de coste en Streamlit: contador de transacciones procesadas, nº escaladas al LLM,
      nº insights; coste estimado en € (precios gpt-4o-mini Sweden Central); visible siempre.

## Criterio de done

Importar el historico de demo-user, llamar a `/insights/generate` con `{user_id, month}`,
recibir texto coherente de 3-4 parrafos, y ver el coste de esa llamada en el panel.
