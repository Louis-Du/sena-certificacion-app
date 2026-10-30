# Registro de Cambios de Interfaz (CHANGELOG UI)

**Proyecto:** SENA Certificación App  
**Fecha:** Octubre 2026  
**Versión de diseño:** `20261030-final`

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

### Fase 4 — Panel de Control Ejecutivo / Dashboard (Commit actual)
- Nueva vista `#dashboard-view` accesible desde el enlace lateral `data-view="dashboard"`.
- 4 tarjetas de métricas ejecutivas con animación de entrada (`cardEntrance`):
  1. **Total Aprendices**: Aprendices en base de datos.
  2. **Por Certificar**: Aprendices con requisitos pendientes.
  3. **Certificados**: Aprendices que cumplieron el 100% de requisitos.
  4. **Actas Registradas**: Comités y actas en el sistema.
- Mapa de calor de actividad anual estilo **GitHub Heatmap** distribuido en 52 semanas del año 2026 con 5 niveles de intensidad (`lvl-0` a `lvl-4`).
- Accesos directos a flujos clave (Cargar información, Listado de aprendices, Indicadores).

### Fase 5 — Consistencia en el Resto de Vistas (Commit actual)
- Topbars unificadas en `#aprendices-view`, `#actas-view` e `#indicadores-view` con marca institucional, títulos y botón de recarga rápida.
- Fila de KPIs de indicadores mejorada con elevación sutil y estilo uniforme.
- Diseño responsivo adaptativo para resoluciones móviles y pantallas intermedias (`@media (max-width: 1100px)`, `@media (max-width: 980px)` y `@media (max-width: 640px)`).

### Fase 6 — Cierre y Optimización de Entrega (Commit actual)
- Exposición global de `window.SenaUI = { showToast, loadDashboardData }` para interoperabilidad segura.
- Actualización de parámetros de cache busting en `index.html`: `?v=20261030-final`.
- Validación completa de la suite de pruebas unitarias y de integración (`pytest`).

---

## 3. Matriz de Datos: Reales vs. Demostrativos

| Componente / Elemento | Estado de Datos | Origen / Comportamiento |
| :--- | :--- | :--- |
| **Métrica "Total Aprendices"** | **Real** | Consulta directa a `/api/learners?page=1&page_size=1` (campo `total`). |
| **Métrica "Por Certificar"** | **Real** | Calculado en tiempo real desde `/api/indicadores` (`total_pendientes`). |
| **Métrica "Certificados"** | **Real** | Calculado en tiempo real desde `/api/indicadores` (`total_certificados`). |
| **Métrica "Actas Registradas"** | **Real** | Conteo exacto desde `/api/acts` (`items.length`). |
| **Fechas con actas en el Heatmap** | **Real** | Las fechas que contienen actas registradas en SQLite iluminan el día exacto en el calendario. |
| **Matriz diaria continua del Heatmap** | **Demostrativo / Proyectado** | La base de datos no registra marcas de tiempo continuas por día para cada cambio de estado histórico. Los días sin actas registradas se calculan mediante un modelo determinístico congruente con los cierres de comités trimestrales (finales de marzo, junio, septiembre y diciembre de 2026). Cuenta con aviso visible en la leyenda: `◈ Matriz proyectada/demostrativa`. |
| **Carga y Validación de Archivos** | **Real** | Endpoint `/api/files/validate` y `/api/imports/{id}/confirm`. |
| **Listado y Filtros de Aprendices** | **Real** | Endpoint `/api/learners` con paginación, filtros de estado y búsqueda. |
| **Detalle de Aprendiz** | **Real** | Endpoint `/api/learners/{id}` con requisitos y trazabilidad. |
| **Registro y Consulta de Actas** | **Real** | Formulario y listado sincronizados con la tabla `acts` en SQLite. |
| **Tablero de Indicadores y Gráficas** | **Real** | Endpoint `/api/indicadores` con renderizado Chart.js. |

---

## 4. Archivos Modificados en el Cierre

- `app/static/index.html`: Inclusión de `#dashboard-view`, enlace en sidebar, consistencia de topbars y versionado de assets.
- `app/static/styles.css`: Estilos para métricas, cuadrícula de dashboard, heatmap, quick action cards y mejoras responsivas.
- `app/static/ui-enhancements.js`: Lógica de carga de métricas (`loadDashboardData`), renderizado del heatmap de 52 semanas, enrutamiento del dashboard y exposición de `window.SenaUI`.
- `docs/CHANGELOG_UI.md`: Documentación formal de la arquitectura visual y matriz de datos.
