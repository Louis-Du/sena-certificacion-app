# Reporte final de correcciones de informes

## Cambios realizados

### Parte A. Defectos visuales
- `informe_causas` / `informe_pendientes` (hoja `Análisis de pendientes`): gráfico movido debajo de las notas (`anchor=A{row+1}`), tamaño ajustado y rango dinámico.
- `informe_ejecutivo`: gráfico de dona solo muestra valores (`showCatName=False`), agrandado.
- Todas las hojas: `freeze_panes=None` (sin bloque de filas congeladas).

### Parte B. Contenido
- B1: subtítulo de "Personas pendientes únicas" corregido a "Personas con estado Pendiente".
- B2: gráfico de causas incluye todas las causas + "Sin motivo informado".
- B3: alerta de calidad `acta_identificador_invalido` (severidad Media) para actas con identificador inválido; marcada en observación.
- B4: diccionario de normalización de causas unificado en `parsers._canonical_cause`, documentado y ampliado con sinónimos.

### Parte C. Cifras no coincidentes
- Se mantiene el cálculo actual; se reportan hallazgos para decisión humana (C2, C3, C4, C5).
- C1: certificados = 1.685 − 3 conflictos − 45 (OCTUBRE) = 1.637, confirmado.
- C6: fechas se normalizan con `parse_date_value`; revisar ambigüedad dd/mm.

### Parte D. Cobertura
- Propuestas: avance por categoría, certificados por mes desde CERTIFICADOS, desglose por nivel, jornadas. No todas implementadas por alcance.

## Decisiones requeridas
- C2: ¿usar 48.703 en lugar de 50.146 para complementaria?
- C3: ¿universo correcto para avance global (58,5% vs 67,4%)?
- C4: ¿doble conteo de Campesena/Full Popular en META?
- C5: ¿calcular certificados por mes desde CERTIFICADOS?
- Periodo del informe: ¿ampliar a octubre/noviembre?
"