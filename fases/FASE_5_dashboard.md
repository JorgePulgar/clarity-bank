# Fase 5 — Dashboard funcional completo

**Estado:** COMPLETADA
**Objetivo:** dashboard autoexplicativo. Cualquiera lo abre y entiende el sistema sin ayuda.

> Base: `dashboard/streamlit_app.py` con 3 tabs, sidebar y panel de coste de F4.

## Tareas

- [x] **Pantalla 1 — Transaccion individual**: 4 cards (categoria, confianza con barra de progreso,
      nivel L1/L2, latencia ms), flag anomalia en rojo + razon, descripcion original vs anonimizada
      lado a lado.
- [x] **Pantalla 2 — Importar historico**: boton "Generar e importar historico" (llama a
      `generate_history.generate()` + POST /transactions/import), barra de progreso, uploader CSV
      propio, resumen con grafico de barras gastos por categoria, tabla y lista de anomalias.
- [x] **Pantalla 3 — Insights mensuales**: spinner mientras genera, texto en markdown, caption con
      fuente (LLM/plantilla), transacciones analizadas y coste estimado en EUR.
- [x] **Sidebar global**: estado de conexion con modo clasificador, usuario activo con
      session_state, metricas en vivo (transacciones, % escaladas LLM, insights, coste acumulado),
      boton "Reset demo" (limpia session_state conservando user_id).
- [x] **Pulido visual**: titulo descriptivo con caption del pipeline, tabs renombrados, layout wide,
      sidebar siempre expandida.

## Criterio de done

Cualquier persona que abra el dashboard entiende que hace el sistema sin explicacion. **Cumplido.**
