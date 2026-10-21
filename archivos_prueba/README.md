# Archivos de prueba

Este directorio contiene los archivos correctos e incorrectos usados para
verificar el flujo de validación e importación. Las reglas completas, los
contadores y las decisiones administrativas pendientes están documentados en
[`docs/validation_rules.md`](../docs/validation_rules.md).

La validación nunca escribe en la base de datos. La importación solo se guarda
después de confirmar y únicamente con los registros que la vista previa mostró
como importables.

## Resumen de comportamiento

| Archivo | Tipo | Resultado esperado |
| --- | --- | --- |
| `correctos/Requisitos_correcto.xlsx` | `requisitos` | `ready` |
| `correctos/Requisitos_pendientes_demo_correcto.xlsx` | `requisitos` | `ready` |
| `correctos/DF14A_correcto.xlsx` | `df14a` | `ready` |
| `correctos/DF14A_correcto.xls` | `df14a` | `ready` |
| `correctos/DF14A_demo_correcto.xlsx` | `df14a` | `ready` |
| `correctos/DF_14A_1_correcto.xml` | `df14a` | `ready` |
| `correctos/ACTAS_2026_PENDIENTES_correcto.csv` | `csv_certificacion` | `ready` |
| `correctos/ACTAS_2026_PENDIENTES_completo_correcto.csv` | `csv_certificacion` | `ready` |
| `correctos/Acta_certificacion_correcto.pdf` | `acta` | `ready` |
| `correctos/Acta_certificacion_23_demo_correcto.docx` | `acta` | `ready` |
| `correctos/ACTAS_2026_correcto.xlsx` | `actas_completo` | `ready`, 21 registros |
| `correctos/ACTAS_2026_institucional_correcto.xlsx` | `actas_completo` | `ready` |
| `incorrectos/Requisitos_incorrecto_sin_columnas_clave.xlsx` | `requisitos` | `error`, 0 importables |
| `incorrectos/Requisitos_pendientes_demo_incorrecto.xlsx` | `requisitos` | `error`, 0 importables |
| `incorrectos/DF14A_incorrecto_sin_ficha_y_nivel_invalido.xlsx` | `df14a` | `error`, 0 importables |
| `incorrectos/DF14A_demo_incorrecto.xlsx` | `df14a` | `error`, 0 importables |
| `incorrectos/DF_14A_1_incorrecto.xml` | `df14a` | `error`, 0 importables |
| `incorrectos/ACTAS_2026_PENDIENTES_incorrecto.csv` | `csv_certificacion` | `error`, 0 importables |
| `incorrectos/ACTAS_2026_PENDIENTES_incorrecto_sin_documento.csv` | `csv_certificacion` | `error`, 0 importables |
| `incorrectos/Acta_certificacion_incorrecto_vacio.pdf` | `acta` | `error`, PDF ilegible |
| `incorrectos/Acta_certificacion_23_demo_incorrecto_vacio.docx` | `acta` | `error`, DOCX sin texto ni tablas |
| `incorrectos/ACTAS_2026_incorrecto_conflictos_y_meses.xlsx` | `actas_completo` | `warning`, 10 importables |
| `incorrectos/ACTAS_2026_institucional_incorrecto.xlsx` | `actas_completo` | `warning` |

## Notas por archivo

### Requisitos

Los archivos incorrectos conservan solo `FICHA`, `PROGRAMA`,
`TELEFONO_CONTACTO` y `OBSERVACIONES`. Faltan `DOCUMENTO`, `NOMBRES`,
`REQUISITO` y `ESTADO`, por lo que no queda ningún registro importable. La
validación usa las reglas de requisitos y no las hojas de ACTAS 2026.

### DF14A

- Los archivos incorrectos cambian `FICHA` por `CODIGO_GRUPO`. Al faltar el
  campo obligatorio, las filas se rechazan y no se puede confirmar.
- También incluyen niveles `OPERARIO` y `CURSO_NO_FORMAL`. El sistema los
  informa como advertencia, pero no inventa equivalencias ni los asigna a una
  categoría.
- `DF14A_correcto.xls` se agregó para cubrir el formato XLS además de XLSX, XML
  y CSV.

### CSV de certificación

Los archivos incorrectos usan `ID_REGISTRO_EXTERNO` y `NOMBRE_COMPLETO` en lugar
de `NÚMERO DE DOCUMENTO` y `NOMBRE`. La validación informa ambas columnas
faltantes y deja `valid_records = 0`. La vista previa y la confirmación se
bloquean.

### Actas PDF/DOCX

Los archivos vacíos o corruptos se rechazan con estado `error`. No se crea un
registro de relleno y no se permite confirmar. Un acta legible sí puede generar
un registro de metadatos del documento o filas de su tabla, según el contenido.

### Excel institucional ACTAS 2026

- `ACTAS_2026_correcto.xlsx` produce 21 registros: 4 certificados, 4 pendientes,
  12 complementaria (3 fechas × 4 canales) y 1 meta. No son aprendices
  duplicados.
- `ACTAS_2026_incorrecto_conflictos_y_meses.xlsx` produce 10 registros
  importables (4 certificados, 5 pendientes y 1 meta). Reporta el conflicto
  entre certificados y pendientes con documento y ficha, y el mes fuera del
  período. No borra ni cambia estados automáticamente: al confirmar conserva el
  estado previo del aprendiz o lo deja sin definir si es nuevo.
- La ausencia de la hoja `COMPLEMENTARIA` se mantiene como advertencia. La
  decisión de si debe ser bloqueante está pendiente y documentada.

## Ejecutar las pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Las pruebas de API usan bases SQLite temporales o en memoria. No se modifica
`data/sena_certificacion.db`.
