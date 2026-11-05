# Informe de certificación v1 (Ene–Sep 2026)

Fuente única de datos: `GET /api/informes/consolidado` (dataset consolidado del lote vigente de ACTAS 2026). No se reimplementan fórmulas: se reutiliza el motor de indicadores (B1–B5).

La interfaz de **Indicadores** permite descargar este informe mediante **Descargar
informe**. El enlace consume `GET /api/informes/export` y genera el mismo dataset
en formato Excel, por lo que la descarga no introduce un cálculo paralelo.

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

## Fuera de alcance v1
Plantilla visual formal, PDF, envío por correo, permisos y alertas (#45/#48/#49).