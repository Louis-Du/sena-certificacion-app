# Informe de certificación v1 (Ene–Sep 2026)

Fuente única de datos: `GET /api/informes/consolidado` (dataset consolidado del lote vigente de ACTAS 2026). No se reimplementan fórmulas: se reutiliza el motor de indicadores (B1–B5).

La interfaz de **Indicadores** permite generar este informe mediante **Exportar
informe**. La ventana presenta los formatos disponibles. PDF, XLSX y CSV consumen
`GET /api/informes/export` y genera el mismo dataset en el formato solicitado, por lo que
la descarga no introduce un cálculo paralelo.

## Informes incluidos en v1
1. **Resumen ejecutivo** (universo consolidado): meta total, certificados (personas), complementaria, pendientes, avance global, efectividad global, brecha, conflictos, fuera de período.
2. **Desglose por categoría/nivel**: Educación Superior, Técnica Laboral, Articulación, Complementaria (meta, certificados, pendientes, avance, brecha, efectividad).
3. **Certificados por mes**: serie Ene–Sep desde `MES DE CERTIFICACIÓN` del consolidado.
4. **Causas de no certificación**: motivos normalizados, incidencias y aprendices únicos pendientes.
5. **Actas del consolidado**: número de acta, aprendices asociados y cruce con tabla `Act` cuando exista.

## Campos y fuentes
- Metadatos: `generated_at`, `periodo`, `source`, `import_id`, `file_name`, `advertencias`.
- Resumen: `resumen_ejecutivo.*` (derivado de `compute_indicadores_2026`).
- Categorías: `desglose_por_categoria` (= `metricas`).
- Mensual: `certificados_por_mes.meses`.
- Causas: `causas_no_certificacion.motivos`.
- Actas: `actas.items`.

## Verificación
Cubierto por `tests/test_informes_consolidado.py` y `tests/test_indicadores.py` (datos de prueba controlados). Endpoint responde 200 sin lote vigente (sin 500 ni cifras inventadas).

## Exportación v1 (#47)
- Formato: Excel `.xlsx` (`GET /api/informes/export`).
- Hojas: `Resumen`, `Categorias`, `CertificadosPorMes`, `Causas`, `Actas`, `Advertencias`.
- Valores vacíos (`None`) se dejan como celda vacía (no se inventan ceros).
- Si no hay datos suficientes, el endpoint responde 404 con mensaje claro.
- La interfaz permite seleccionar un informe consolidado y seis tipos de informe:
  general, ejecutivo,
  aprendices, requisitos y pendientes, causas de pendientes y actas.
- Los seis tipos individuales disponen de PDF, XLSX y CSV mediante `type` y
  `format`. Los
  informes de aprendices y pendientes se obtienen del padrón local; los demás
  reutilizan el consolidado institucional y los cálculos de indicadores.
- El tipo `consolidado` reúne los seis informes en un único documento PDF o en
  un XLSX con hojas separadas. CSV no se ofrece para este tipo porque no admite
  múltiples informes/hojas en un solo archivo.

## Fuera de alcance v1
Envío por correo, permisos y alertas (#45/#48/#49). El PDF incluye portada,
secciones, tablas, encabezado, pie y paginación; el XLSX incluye estilos,
filtros, paneles inmovilizados y gráficos editables.