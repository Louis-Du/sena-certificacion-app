# Registro de Cambios de Interfaz (CHANGELOG UI)

**Proyecto:** SENA Certificación App  
**Fecha:** Octubre 2026  
**Versión de diseño:** `20261030-v5`

---

## 1. Resumen Ejecutivo del Rediseño

Se completó la modernización visual integral de la aplicación web local de seguimiento de certificación del SENA sin alterar la lógica de negocio, los esquemas de base de datos ni los endpoints de la API FastAPI. Se preservaron todos los IDs, clases funcionales, atributos `data-*` y selectores requeridos por el controlador JavaScript (`app.js`).

---

## 2. Fases Implementadas

### Fase 1 — Base Visual y Sistema de Diseño (Commit `f7033b9`)
- Implementación de tokens y variables CSS (`--canvas: #f1f5f9`, `--paper: #ffffff`, `--ink: #0f172a`, `--muted: #64748b`, `--teal: #0f766e`, `--sidebar-bg: #0f172a`).
- Tipografía profesional: Google Fonts **Inter** (cuerpo) y **Space Grotesk** (encabezados/marca).
- Eliminación de la dependencia de Bootstrap CDN para unificar estilos y evitar interferencias en componentes nativos.
- Reestructuración de la concha de diseño (`.app-layout`, `.sidebar`, `.page-content`).

### Fase 2 — Vista de Carga de Información (Commit `f110f2f`)
- Rediseño de la vista `#carga-view` con flujo por etapas (Pasos 1 a 4).
- Selector de fuentes principales (Actas de Comité, DF14A, ACTAS 2026) y selector secundario para carga de requisitos.
- Zona de arrastre `#drop-zone` con estados visuales mejorados para `:hover` y `.dragging`.
- Paneles modulares para inspección de validación previa y confirmación en base de datos.

### Fase 3 — Sistema de Notificaciones Toasts (Commit `a79507a`)
- Contenedor flotante `#toast-container` con posicionamiento fijo superior derecho y soporte de accesibilidad `aria-live="polite"`.
- Módulo `app/static/ui-enhancements.js` con función universal `showToast(message, type, duration)`.
- `MutationObserver` integrado sobre `#feedback` y formularios secundarios para proyectar mensajes relevantes como toasts sin ruido visual fijo.

### Fase 4 — Indicadores unificados, sin Dashboard aparte
- Se eliminó la vista `#dashboard-view`: las 4 métricas ejecutivas y el heatmap viven al inicio de **Indicadores**.
- Tarjetas superiores: Total aprendices, Por certificar/pendientes, Certificados y Actas registradas.
- Heatmap anual estilo **GitHub** con datos reales de `RequirementStatusHistory` e `ImportHistory`.
- Pestañas pill **Resumen / Causas / Actas del período** para reducir el desplazamiento vertical sin ocultar información.

### Fase 5 — Rail, modal y retroalimentación
- Sidebar tipo rail con iconos SVG, tooltip, indicador rosa animado y un único ítem activo.
- Confirmación de importación y conflictos de coherencia en modal flotante, con cierre por botón, backdrop o `Escape`, foco contenido y cierre automático al terminar.
- Barras de progreso global y dentro del modal durante validación, vista previa y confirmación.
- Toasts diferenciados para información, advertencia, error y éxito.

### Fase 6 — Cierre y verificación
- Endpoints `GET /api/activity/heatmap?year=2026` y `GET /api/activity/day/YYYY-MM-DD` documentados en `app/main.py`.
- Cache busting actualizado a `?v=20261030-v5`.
- Verificación con navegador real (Playwright/Firefox) y suite `pytest` sin E2E.

---

## 3. Matriz de Datos: Reales vs. Demostrativos

| Componente / Elemento | Estado de Datos | Origen / Comportamiento |
| :--- | :--- | :--- |
| **Métrica "Total Aprendices"** | **Real** | Consulta directa a `/api/learners?page=1&page_size=1` (campo `total`). |
| **Métrica "Por Certificar"** | **Real** | Calculado en tiempo real desde `/api/indicadores` (`total_pendientes`). |
| **Métrica "Certificados"** | **Real** | Calculado en tiempo real desde `/api/indicadores` (`total_certificados`). |
| **Métrica "Actas Registradas"** | **Real** | Conteo exacto desde `/api/acts` (`items.length`). |
| **Fechas con actividad en el Heatmap** | **Real** | Cada celda cuenta cambios de requisitos (`RequirementStatusHistory.recorded_at`) e importaciones confirmadas (`ImportHistory.imported_at`). |
| **Detalle de un día del Heatmap** | **Real** | `GET /api/activity/day/YYYY-MM-DD` devuelve aprendices e importaciones de esa fecha. |
| **Matriz diaria del Heatmap** | **Real** | El backend genera los 365 días del año consultado; los días sin eventos quedan en nivel 0. |
| **Carga y Validación de Archivos** | **Real** | Endpoint `/api/files/validate` y `/api/imports/{id}/confirm`. |
| **Listado y Filtros de Aprendices** | **Real** | Endpoint `/api/learners` con paginación, filtros de estado y búsqueda. |
| **Detalle de Aprendiz** | **Real** | Endpoint `/api/learners/{id}` con requisitos y trazabilidad. |
| **Registro y Consulta de Actas** | **Real** | Formulario y listado sincronizados con la tabla `acts` en SQLite. |
| **Tablero de Indicadores y Gráficas** | **Real** | Endpoint `/api/indicadores` con renderizado Chart.js. |

---

## 4. Archivos Modificados en el Cierre

- `app/static/index.html`: rail con iconos SVG, indicadores unificados, modal de revisión, barra de progreso global y cache busting `v5`.
- `app/static/styles.css`: sistema visual, chips, rail, modal, heatmap, pestañas pill, KPIs y ajustes responsivos.
- `app/static/ui-enhancements.js`: toasts, modal, progreso, heatmap real con tooltip, pestañas, navegación y ajuste de gráficos.
- `app/services/activity.py`: agregación del heatmap y detalle diario.
- `app/main.py`: documentación y validación del parámetro `year` en los endpoints de actividad.
- `docs/CHANGELOG_UI.md`: documentación formal de la arquitectura visual y matriz de datos.
