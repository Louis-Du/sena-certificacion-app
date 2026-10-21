# Archivos de Prueba para Validación y Carga del Sistema

Este directorio contiene juegos de datos de prueba diseñados específicamente a partir de los 6 archivos originales del proceso de certificación del SENA:
1. `Requisitos_pendientes_demo.xlsx`
2. `DF14A_demo.xlsx`
3. `DF-14A_1.xml`
4. `ACTAS 2026(PENDIENTES).csv`
5. `Acta_certificacion_23_demo.docx`
6. `Documentos positivos\ACTAS 2026.xlsx`

Cada documento cuenta con su versión **correcta** (válida, conforme al esquema oficial y lista para procesar con estado `READY`) y su versión **incorrecta** (con errores provocados deliberadamente para verificar que el sistema capture anomalías, genere advertencias `WARNING` o errores controlados, y proteja la integridad de los datos).

---

## 📁 Estructura del Directorio

```text
archivos_prueba/
├── correctos/
│   ├── Requisitos_pendientes_demo_correcto.xlsx
│   ├── DF14A_demo_correcto.xlsx
│   ├── DF_14A_1_correcto.xml
│   ├── ACTAS_2026_PENDIENTES_completo_correcto.csv
│   ├── Acta_certificacion_23_demo_correcto.docx
│   └── ACTAS_2026_institucional_correcto.xlsx
└── incorrectos/
    ├── Requisitos_pendientes_demo_incorrecto.xlsx
    ├── DF14A_demo_incorrecto.xlsx
    ├── DF_14A_1_incorrecto.xml
    ├── ACTAS_2026_PENDIENTES_incorrecto.csv
    ├── Acta_certificacion_23_demo_incorrecto_vacio.docx
    └── ACTAS_2026_institucional_incorrecto.xlsx
```

---

## 🧪 Detalle de Estructura y Comportamiento Esperado

### 1. Requisitos Pendientes (Excel)
* **Archivo Original:** `D:\Proyecto\Requisitos_pendientes_demo.xlsx`
* **Tipo en el Sistema:** `requisitos`
* **Columnas del original:** `DOCUMENTO`, `NOMBRES`, `FICHA`, `REQUISITO`, `ESTADO`, `OBSERVACIONES`

#### Versión Correcta: `Requisitos_pendientes_demo_correcto.xlsx`
* **Estructura:** Contiene las 6 columnas completas con 4 registros de aprendices y estado `Cumplido` en requisitos clave (Saber TyT, Paz y Salvo Biblioteca, APE, Destrucción de Carnet).
* **Resultado del Sistema:** `status: READY` (Verde).
  - Archivo abierto correctamente.
  - Columnas obligatorias presentes (`DOCUMENTO`, `NOMBRES`, `REQUISITO`, `ESTADO`).
  - 4 registros encontrados y 4 válidos, 0 inconsistencias.

#### Versión Incorrecta: `Requisitos_pendientes_demo_incorrecto.xlsx`
* **Estructura:** Omite las 4 columnas obligatorias, dejando solo encabezados no vinculantes (`FICHA`, `PROGRAMA`, `TELEFONO_CONTACTO`, `OBSERVACIONES`).
* **Resultado del Sistema:** `status: WARNING` (Ámbar).
  - Alerta: `Faltan 4 columna(s) obligatoria(s): DOCUMENTO, NOMBRES, REQUISITO, ESTADO`.

---

### 2. DF14A (Excel Demostrativo)
* **Archivo Original:** `D:\Proyecto\DF14A_demo.xlsx`
* **Tipo en el Sistema:** `df14a`
* **Columnas del original:** `TIPO_DOCUMENTO`, `DOCUMENTO`, `NOMBRES`, `FICHA`, `PROGRAMA`, `NIVEL_FORMACION`, `MODALIDAD`, `FECHA_INICIO`, `FECHA_FIN`, `ESTADO_ASPIRANTE`, `CORREO_ELECTRONICO`

#### Versión Correcta: `DF14A_demo_correcto.xlsx`
* **Estructura:** Las 11 columnas exactas con niveles clasificados (`TECNÓLOGO`, `TÉCNICO`), estados válidos (`Por Certificar`) y correos electrónicos funcionales.
* **Resultado del Sistema:** `status: READY` (Verde).
  - Columnas obligatorias presentes (`FICHA`).
  - 3 registros encontrados y 3 registros válidos, 0 inconsistencias.

#### Versión Incorrecta: `DF14A_demo_incorrecto.xlsx`
* **Estructura:** Omite la columna `FICHA` (renombrada a `CODIGO_GRUPO`) e incluye niveles de formación no reconocidos por la regla misional (`OPERARIO` y `CURSO_NO_FORMAL`).
* **Resultado del Sistema:** `status: WARNING` (Ámbar).
  - Alerta: `Faltan 1 columna(s) obligatoria(s): FICHA`.
  - Alerta: `2 registros con nivel de formación sin clasificar (CURSO_NO_FORMAL, OPERARIO)`.
  - Reporte de 2 inconsistencias.

---

### 3. DF-14A XML (SpreadsheetML Oficial de SOFIA Plus)
* **Archivo Original:** `D:\Proyecto\DF-14A_1.xml` (14.6 MB, 7.056 filas)
* **Tipo en el Sistema:** `df14a`
* **Formato:** XML Spreadsheet 2003 (`Workbook`, `Worksheet`, `Table`, `Row`, `Cell`, `Data ss:Type="String"`)

#### Versión Correcta: `DF_14A_1_correcto.xml`
* **Estructura:** Archivo XML SpreadsheetML con filas preliminares institucionales (`DF-14A_`, `MATRICULADOS_RESUMEN_POR_FICHA`, fecha de corte), fila de encabezados con `FICHA`, `PROGRAMA`, `NIVEL_FORMACION`, `POR_CERTIFICAR`, `CERTIFICADO`, etc., y 3 registros válidos de tecnólogos y técnicos.
* **Resultado del Sistema:** `status: READY` (Verde).
  - Procesado por `parse_df14a_xml`.
  - Columnas obligatorias presentes (`FICHA`).
  - 3 registros encontrados y 3 registros válidos, 0 inconsistencias.

#### Versión Incorrecta: `DF_14A_1_incorrecto.xml`
* **Estructura:** Archivo XML SpreadsheetML donde la fila de encabezados omite la columna `FICHA` (sustituida por `CODIGO_CURSO`) y contiene niveles sin clasificar (`OPERARIO`, `COMPLEMENTARIA VIRTUAL`).
* **Resultado del Sistema:** `status: WARNING` (Ámbar).
  - Alerta: `Faltan 1 columna(s) obligatoria(s): FICHA`.

---

### 4. ACTAS 2026 (PENDIENTES).csv
* **Archivo Original:** `D:\Proyecto\ACTAS 2026(PENDIENTES).csv` (290 filas, 31 columnas)
* **Tipo en el Sistema:** `csv_certificacion` (detectado como `pendientes`)
* **Columnas del original:** 31 columnas (`ITEM`, `NIVEL`, `FICHA`, `PROGRAMA`, `NÚMERO DE DOCUMENTO`, `NOMBRE`, `APELLIDOS`, `INSTRUCTOR DE SEGUIMIENTO`, `ACTA`, `CORREO`, ..., `ESTADO`, `MOTIVO DE NO CERTIFICACION`, etc.)

#### Versión Correcta: `ACTAS_2026_PENDIENTES_completo_correcto.csv`
* **Estructura:** Archivo CSV codificado en UTF-8 con las 31 columnas originales completas. Aprendices con niveles clasificados (`TECNÓLOGO`, `TÉCNICO`, `SENATIC`), estado `PENDIENTE` y motivos desagregables (`No anexa T&T`, `APE`, `Destrucción del Carnet`).
* **Resultado del Sistema:** `status: READY` (Verde).
  - Contenido detectado automáticamente: *Listado de pendientes*.
  - Columnas obligatorias presentes (`NÚMERO DE DOCUMENTO`, `NOMBRE`, `FICHA`).
  - 4 registros encontrados y 4 válidos, 0 inconsistencias.

#### Versión Incorrecta: `ACTAS_2026_PENDIENTES_incorrecto.csv`
* **Estructura:** Archivo CSV que carece de las columnas obligatorias `NÚMERO DE DOCUMENTO` y `NOMBRE` (renombradas intencionalmente a `ID_REGISTRO_EXTERNO` y `NOMBRE_COMPLETO`), además de incluir niveles no clasificados (`OPERARIO`, `NIVEL_DESCONOCIDO`).
* **Resultado del Sistema:** `status: WARNING` (Ámbar).
  - Alerta: `Faltan 2 columna(s) obligatoria(s): NÚMERO DE DOCUMENTO, NOMBRE`.
  - Alerta: `2 registros con nivel de formación sin clasificar (NIVEL_DESCONOCIDO, OPERARIO)`.

---

### 5. Acta de Certificación (Documento Word .docx)
* **Archivo Original:** `D:\Proyecto\Acta_certificacion_23_demo.docx`
* **Tipo en el Sistema:** `acta`
* **Estructura del original:** Documento con párrafos formales de acta de comité de certificación y tabla con columnas `No.`, `Documento`, `Nombre`, `Ficha`, `Programa`.

#### Versión Correcta: `Acta_certificacion_23_demo_correcto.docx`
* **Estructura:** Documento Word con metadatos del acta (Número 23, Centro de Comercio y Servicios, fecha, asunto) y tabla estructurada de 5 columnas con 3 aprendices válidos.
* **Resultado del Sistema:** `status: READY` (Verde).
  - Archivo abierto y legible.
  - Procesado con `parse_acta_docx`, extrayendo párrafos, encabezados y registros de la tabla.

#### Versión Incorrecta: `Acta_certificacion_23_demo_incorrecto_vacio.docx`
* **Estructura:** Documento Word sin contenido (0 párrafos y 0 tablas).
* **Resultado del Sistema:** `status: WARNING` (Ámbar).
  - Alerta: `Contenido legible: El documento no contiene contenido.`

---

### 6. ACTAS 2026.xlsx (Excel Institucional Multi-Hoja)
* **Archivo Original:** `D:\Proyecto\Documentos positivos\ACTAS 2026.xlsx` (4.438 certificados, 290 pendientes, complementaria, metas)
* **Tipo en el Sistema:** `actas_completo`
* **Hojas obligatorias:** `CERTIFICADOS`, `PENDIENTES`, `COMPLEMENTARIA`, `META`

#### Versión Correcta: `ACTAS_2026_institucional_correcto.xlsx`
* **Estructura:**
  - Hoja `CERTIFICADOS`: 4 aprendices con niveles clasificados, sin duplicados ni traslapes con pendientes, meses de certificación de la vigencia (`ENERO`, `FEBRERO`, `MARZO`, `ABRIL`).
  - Hoja `PENDIENTES`: 4 aprendices distintos, con estado `PENDIENTE` y motivos claros.
  - Hoja `COMPLEMENTARIA`: Matriz de canales (Presencial, Virtual, Campesena, Full Popular) con fechas y cantidades del año 2026.
  - Hoja `META`: Rótulos oficiales y metas numéricas (Técnico laboral: 1910, Articulación: 1995, Superior: 943, Total titulada: 4848, Complementaria: 83726, FPI: 88574).
* **Resultado del Sistema:** `status: READY` (Verde).
  - Las 4 hojas detectadas.
  - 8 registros válidos combinados (4 certificados + 4 pendientes), 0 conflictos cruzados, 0 niveles sin clasificar.

#### Versión Incorrecta: `ACTAS_2026_institucional_incorrecto.xlsx`
* **Estructura:**
  - Omisión de la hoja `COMPLEMENTARIA`.
  - Conflicto cruzado: El aprendiz `1043966273` con ficha `2847836` aparece simultáneamente en `CERTIFICADOS` y en `PENDIENTES`.
  - Nivel sin clasificar: Registro en `PENDIENTES` con nivel `OPERARIO`.
  - Mes fuera de corte: Registro en `CERTIFICADOS` con mes `DICIEMBRE`.
* **Resultado del Sistema:** `status: WARNING` (Ámbar).
  - Alerta: `Hoja COMPLEMENTARIA no encontrada`.
  - Alerta: `Coherencia: 1 aprendices figuran simultáneamente en CERTIFICADOS y PENDIENTES con la misma ficha`.
  - Alerta: `1 registros con nivel de formación sin clasificar (OPERARIO)`.
  - Reporte de 2 inconsistencias.
