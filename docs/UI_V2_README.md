# UI v2 — rediseño radical SENA Certificación

Este paquete cambia de forma clara la **sensación** de la interfaz respecto a la versión anterior (verde + sidebar ancha + paneles estáticos).

## Cambios clave

1. **Sidebar tipo rail** (como la captura médica): iconos circulares, fondo navy, indicador rosa animado en el ítem activo, tooltips al hover.
2. **Confirmación y conflictos en modal flotante**: al validar, el resumen y la resolución de coherencia se centran en un diálogo modal.
3. **Tipografía más grande y legible**: Inter, títulos ~2rem, cuerpo ≥15–17px, pesos 600–800.
4. **Barra de carga** al validar/confirmar importación (disponibilidad percibida).
5. **Sin Dashboard aparte**: KPIs + heatmap viven al inicio de **Indicadores**.
6. **Heatmap con datos reales** vía:
   - `GET /api/activity/heatmap?year=2026`
   - `GET /api/activity/day/YYYY-MM-DD` (aprendices al hover/click)
7. Toasts + foco/Escape en modal (accesibilidad básica).

## Cómo aplicar

```bash
# Frontend
cp ui-redesign-v2/static/styles.css    app/static/styles.css
cp ui-redesign-v2/static/index.html    app/static/index.html
cp ui-redesign-v2/static/ui-enhancements.js app/static/ui-enhancements.js
# app.js puede quedarse el del repo (compatible por IDs)

# Backend (heatmap real)
cp ui-redesign-v2/backend/activity.py  app/services/activity.py
# Añadir rutas descritas en backend/ENDPOINT_PATCH.md dentro de app/main.py
```

Reinicia la API y fuerza recarga del navegador (Ctrl+F5).

## Pruebas manuales

1. Navegar con el rail: Cargar → Aprendices → Actas → Indicadores (indicador rosa activo).
2. Cargar un Excel ACTAS 2026 → Validar → debe abrirse **modal** con resumen y conflictos.
3. Resolver conflictos → Confirmar (barra de progreso visible).
4. Indicadores: ver 4 KPIs arriba, heatmap debajo; hover en un cuadro con actividad muestra aprendices/importaciones.
5. Teclado: Tab en sidebar, Escape cierra modal.

## Notas

- Si el endpoint de activity no está montado, el heatmap muestra vacío y el tooltip lo indica; el resto de la UI sigue operativo.
- `app.js` no se reescribió: el modal observa `#confirmation-panel` y los botones originales.
- El heatmap combina `RequirementStatusHistory` + `ImportHistory` (peso por registros importados).
