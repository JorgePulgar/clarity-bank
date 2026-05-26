# Fase 3 — Deteccion de anomalias + historico simulado

**Estado:** EN CURSO (base hecha en fase 1)
**Objetivo:** detectores de anomalias defendibles + generador de historico realista para demo.

> Base ya existente: `core/anomalies.py::detect_anomaly` (z-score por categoria + salto sobre
> el maximo historico cuando hay pocos datos), integrado en el pipeline. `scripts/generate_history.py`
> genera CSV con recurrencias y 1 outlier.

## Tareas

- [x] z-score por categoria integrado en `POST /transactions` y en import (vía `service.py`).
- [x] `scripts/generate_history.py` base (params user/months/per-month/seed, recurrencias, 1 outlier).
- [ ] Refactor `core/anomalies.py` a dos detectores con firma explicita:
  - [ ] `detect_zscore_anomaly(transaction, user_history) -> tuple[bool, str]` (|z| > 2.5 por categoria).
  - [ ] `detect_subscription_change(transaction, user_history) -> tuple[bool, str]` (comercio
        recurrente cuyo importe cambia >10% respecto al patron historico).
- [ ] Integrar ambos detectores en el pipeline (sustituir la funcion unica actual).
- [ ] Ampliar `generate_history.py`: 6 meses por defecto, params sueldo/ciudad/suscripciones,
      ~300-500 transacciones, 3-5 outliers intencionados.
- [ ] Tests de los detectores con casos sinteticos (normal, outlier z-score, cambio de suscripcion).

## Criterio de done

`python scripts/generate_history.py --user-id demo-user` → ~500 transacciones; importarlas vía
API; inyectar una de 800€ en alimentacion → salta el flag de anomalia.
