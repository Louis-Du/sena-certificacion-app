# Reglas de validación e importación

Este documento describe cómo decide el sistema qué registros se pueden importar
y qué significan los contadores que se muestran en la interfaz. La
implementación vive en:

- `app/services/validation.py`: validación estructural y de legibilidad.
- `app/services/records.py`: interpretación, campos obligatorios, deduplicación
  interna y contadores.
- `app/services/imports.py`: vista previa y confirmación.
- `app/services/parsers.py`: lectura de cada formato.

La validación es preliminar: **no escribe en la base de datos**. Solo la
confirmación guarda datos, y siempre usa la misma lista de registros importables
que mostró la vista previa.

## Contadores

| Contador | Qué cuenta | Dónde se ve |
| --- | --- | --- |
| `records_found` | Registros que devolvió el lector del archivo. En `actas_completo` incluye todas las hojas procesadas: certificados, pendientes, complementaria y meta. | Validación y vista previa (`parsed_records`) |
| `valid_records` | Registros que cumplen los campos obligatorios y que, tras quitar duplicados internos, se guardarían. Es el mismo valor que `importable_records`. | Validación |
| `rejected_records` | Registros detectados que no se importan porque les falta un campo obligatorio o porque no son interpretables. | Validación y vista previa |
| `duplicate_records` | Registros válidos repetidos dentro del mismo archivo. Se conserva el último y no se insertan filas repetidas. | Validación y vista previa |
| `records_count` | Registros importables únicos que se van a insertar o actualizar. | Vista previa y confirmación |
| `new_records` | Registros importables cuya llave natural no existe todavía en la base de datos. | Vista previa y confirmación |
| `updated_records` | Registros importables cuya llave natural ya existe y se actualizarán. | Vista previa y confirmación |
| `inconsistencies` | Número de bloques de advertencia que no impiden importar y requieren revisión: duplicados internos, niveles sin clasificar, conflictos CERTIFICADOS/PENDIENTES, valores de mes inválidos y hojas opcionales ausentes. Cada bloque informa en su texto cuántas filas afecta. Los meses fuera del período se muestran como nota informativa y no se suman aquí. | Validación |

`new_records + updated_records` siempre es igual a `records_count` en la misma
vista previa. Al confirmar se guardan exactamente esos registros.

## Estados de validación

- **`error`**: el archivo no se puede leer o no queda ningún registro
  importable. La vista previa y la confirmación se bloquean. También se usa para
  un formato incompatible con el tipo seleccionado.
- **`warning`**: hay registros importables, pero también advertencias o filas
  rechazadas. Se permite importación parcial únicamente de los registros que
  cumplen las reglas.
- **`ready`**: todos los registros detectados son importables y no hay
  advertencias.

La interfaz distingue dos cosas que antes se mezclaban: que **la validación se
haya ejecutado** (`VALIDACION COMPLETA` / `REVISAR ARCHIVO`) y que **el archivo
sea apto** (`APTO PARA IMPORTAR` / `APTO CON ADVERTENCIAS` / `NO APTO`). Un
archivo ilegible muestra `REVISAR ARCHIVO` y `NO APTO`, nunca una etiqueta de
aprobación.

## Tratamiento de archivos ilegibles

Un PDF o DOCX vacío, corrupto o sin contenido interpretable se **rechaza** con
estado `error`. Para que el resultado no se contradiga:

- El primer chequeo se llama **`Archivo recibido`** y describe solo la recepción
  del archivo; no afirma que se haya podido abrir.
- El chequeo **`Contenido legible`** aparece con estado `error` cuando la lectura
  falla. No se muestran indicadores positivos como "abierto correctamente" junto
  a `NO APTO`.
- No se generan registros ficticios y la vista previa y la confirmación quedan
  bloqueadas (HTTP 400).

## Reglas por tipo de documento

### `df14a` (XML, XLSX, XLS, CSV)

- Campo obligatorio por fila: `FICHA`.
- Si falta `FICHA` en el archivo, todas las filas se rechazan y la importación se
  bloquea. No se acepta `CODIGO_GRUPO` como sustituto no documentado.
- Los niveles de formación se clasifican con las reglas existentes. Un nivel no
  reconocido (`OPERARIO`, `CURSO_NO_FORMAL`, `NIVEL_DESCONOCIDO`, etc.) se
  importa, pero se informa como advertencia y **no se asigna automáticamente** a
  ninguna categoría.

### `certificados`, `pendientes` y `csv_certificacion`

- Campos obligatorios por fila: `NÚMERO DE DOCUMENTO`, `NOMBRE`, `FICHA`.
- Un CSV que cambia esos encabezados por otros (`ID_REGISTRO_EXTERNO`,
  `NOMBRE_COMPLETO`, etc.) se informa con las columnas faltantes y sus filas no
  se cuentan como válidas.
- El CSV alternativo se detecta como certificados o pendientes según `MOTIVO`,
  `ESTADO` o las columnas presentes. La validación muestra qué contenido detectó.
- Si hay filas válidas y filas defectuosas, se permite importación parcial: las
  defectuosas quedan en `rejected_records` y no se guardan.

### `actas_completo` (Excel institucional)

Hojas esperadas: `CERTIFICADOS`, `PENDIENTES`, `COMPLEMENTARIA`, `META`.

- `CERTIFICADOS` y `PENDIENTES`: mismas reglas de campos obligatorios que los
  listados anteriores.
- `COMPLEMENTARIA`: cada fila de fecha/cantidad se expande en cuatro canales
  (Presencial, Virtual, Campesena, Full Popular). Por eso un archivo pequeño
  puede producir muchos registros.
- `META`: se reconoce como un registro si contiene al menos una meta oficial.
- Si no existe ninguna hoja esperada, el archivo se rechaza. Si parece una
  matriz de requisitos, el mensaje indica que se seleccione la categoría
  correcta.
- La ausencia de `COMPLEMENTARIA` se conserva como **advertencia**, no como
  error, hasta que exista una decisión administrativa documentada.

### `requisitos` (XLSX, XLS, CSV)

- Campos obligatorios por fila: `DOCUMENTO`, `NOMBRES`, `REQUISITO`, `ESTADO`.
- Se usa el lector genérico de requisitos. Nunca se evalúa con las hojas de
  ACTAS 2026 ni se muestran mensajes de `CERTIFICADOS`/`PENDIENTES`.
- Si faltan columnas obligatorias, todas las filas se rechazan y la importación
  se bloquea.

### `meta` y `complementaria` (XLSX, XLS)

- `meta` se lee únicamente de la hoja `META`; si no se reconoce ninguna meta, no
  hay registros importables.
- `complementaria` se lee únicamente de Excel porque su estructura es un bloque
  de fechas y cantidades por canal, no una tabla con encabezados.

### `informe` (DOCX)

- Se usa solo para la tabla de referencia institucional (metas y avance
  reportado a la fecha de corte).
- Si el documento no contiene la tabla de referencia, no hay registros
  importables y se rechaza.

### `acta` (PDF, DOCX) y `otro` (documentos de apoyo)

- Un PDF o DOCX vacío, corrupto o ilegible se rechaza con estado `error`; no se
  crea ningún registro ficticio y no se puede confirmar.
- Un PDF legible se guarda como registro de metadatos del documento.
- Un DOCX con tabla aporta sus filas; si no tiene tabla pero sí párrafos, se
  guarda un registro de metadatos del documento.
- Un DOCX sin texto ni tablas interpretables se rechaza.

## Advertencias que no bloquean

- **Nivel sin clasificar**: el registro se importa, pero no se suma a ninguna
  categoría. No se crean equivalencias para `OPERARIO`, `NIVEL_DESCONOCIDO` ni
  `CURSO_NO_FORMAL`. Las advertencias se calculan por separado sobre los
  registros importables y sobre los rechazados: cuando el archivo no tiene
  registros importables, el mensaje dice "en filas rechazadas; no seran
  importadas" y nunca afirma que esas filas se importarán.
- **Conflicto CERTIFICADOS/PENDIENTES**: si un aprendiz aparece en ambas hojas
  con la misma ficha, se muestra el documento y la ficha en la advertencia. El
  sistema **no borra, no cambia el estado y no elige una fila automáticamente**.
  Al confirmar se guardan los dos registros importados, pero el estado del
  aprendiz no se actualiza automáticamente: se conserva el estado existente o
  queda sin definir si el aprendiz es nuevo. La revisión es administrativa.
- **Mes fuera del período**: el registro se importa como referencia, pero no se
  suma a los indicadores de Enero-Septiembre 2026.
- **Duplicados internos**: se conserva el último registro con la misma llave
  natural y se informa cuántos se descartaron.
- **Hoja COMPLEMENTARIA ausente**: se informa explícitamente. La decisión de si
  debe ser bloqueante queda pendiente y no se inventa una regla.

## Por qué `ACTAS_2026_correcto.xlsx` produce 21 registros

El archivo tiene 12 filas físicas de datos, pero el procesamiento es:

- 4 registros de `CERTIFICADOS`
- 4 registros de `PENDIENTES`
- 12 registros de `COMPLEMENTARIA` (3 fechas × 4 canales)
- 1 registro de `META`

Total: **21 registros importables**. La vista previa muestra este desglose por
tipo para que no se confunda con aprendices duplicados.

## Decisiones administrativas pendientes

1. **Ausencia de `COMPLEMENTARIA`**: hoy es advertencia. No se bloquea la
   importación del resto de hojas.
2. **Conflicto CERTIFICADOS/PENDIENTES**: hoy se reporta con detalle, pero no se
   resuelve automáticamente.
3. **Niveles sin clasificar**: hoy se importan con advertencia y no se asignan a
   categorías. No se crean equivalencias nuevas.

Estas decisiones deben validarse con el área responsable antes de convertirlas
en reglas bloqueantes o en automatismos.

## Limitaciones conocidas

- El sistema **no inventa reglas administrativas**. Cuando una situación no está
  documentada (hoja `COMPLEMENTARIA` ausente, conflicto entre hojas, nivel sin
  clasificar) se informa como advertencia y se conserva el dato tal como viene.
- La clasificación de niveles cubre `superior`, `tecnica` y `articulacion`. Otros
  valores quedan **sin clasificar** y no se suman a los indicadores por categoría.
- La tabla de referencia institucional del informe de gestión solo se integra si
  el DOCX contiene la tabla esperada; de lo contrario no hay registros
  importables para ese tipo.
- La validación es preliminar y no escribe en la base de datos. Solo se persiste
  al confirmar, y siempre los mismos registros importables que mostró la vista
  previa.

## Pruebas

Las regresiones de estos hallazgos están en
`tests/test_validation_regressions.py`. Incluyen archivos correctos e
incorrectos reales de `archivos_prueba/`, además de casos generados para
`COMPLEMENTARIA` ausente y niveles sin clasificar.

Comando usado para la suite completa con base de datos aislada:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

La configuración de `tests/conftest.py` usa SQLite en memoria para la suite
general y una base temporal por prueba para los clientes de API. No se modifica
la base real `data/sena_certificacion.db`.
