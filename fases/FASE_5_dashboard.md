# Fase 5 — Dashboard funcional completo

**Estado:** PENDIENTE (3 pantallas basicas hechas en fase 1)
**Objetivo:** dashboard autoexplicativo. Cualquiera lo abre y entiende el sistema sin ayuda.

> Base ya existente: `dashboard/streamlit_app.py` con 3 tabs (transaccion, importar, insights),
> sidebar con estado de `/health` y selector de usuario, grafico de barras por categoria.

## Tareas

- [ ] **Pantalla 1 — Transaccion individual**: cards visuales (categoria, confianza con barra,
      nivel usado, latencia ms, flag anomalia en rojo + razon) y original vs anonimizado lado a lado.
- [ ] **Pantalla 2 — Importar historico**: selector/creacion de usuario, uploader CSV y boton
      "Generar historico simulado"; barra de progreso; resumen con tabla por categoria, grafico
      de barras y lista de anomalias.
- [ ] **Pantalla 3 — Insights mensuales**: selector usuario + mes, spinner, texto en markdown,
      coste de la llamada debajo.
- [ ] **Sidebar global**: metricas en vivo (transacciones totales, % escaladas al LLM, coste
      acumulado), selector de usuario activo, boton "Reset demo" que limpia la sesion.
- [ ] Pulido visual minimo: colores coherentes, layout limpio, titulos claros. Sin overengineering.

## Criterio de done

Cualquier persona que abra el dashboard entiende que hace el sistema sin explicacion.
