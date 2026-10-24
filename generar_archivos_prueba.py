"""
Generador de archivos de prueba (correctos e incorrectos) para el sistema SENA Certificacion App.
Este script genera pares de archivos de prueba para cada uno de los 6 documentos oficiales/demo:
1. Requisitos_pendientes_demo.xlsx
2. DF14A_demo.xlsx
3. DF-14A_1.xml
4. ACTAS 2026(PENDIENTES).csv
5. Acta_certificacion_23_demo.docx
6. ACTAS 2026.xlsx (Documentos positivos)
"""

import os
import shutil
from io import BytesIO
import pandas as pd
from docx import Document

from app.services.validation import validate_file

# Carpetas de salida
WORKSPACE_TEST_DIR = r"d:\Proyecto\repositorio\sena-certificacion-app\archivos_prueba"
PROYECTO_TEST_DIR = r"D:\Proyecto\archivos_prueba"

DIRS = [
    os.path.join(WORKSPACE_TEST_DIR, "correctos"),
    os.path.join(WORKSPACE_TEST_DIR, "incorrectos"),
    os.path.join(PROYECTO_TEST_DIR, "correctos"),
    os.path.join(PROYECTO_TEST_DIR, "incorrectos"),
]

for d in DIRS:
    os.makedirs(d, exist_ok=True)


def save_file(rel_subfolder: str, filename: str, content: bytes):
    """Guarda el archivo en ambos directorios (workspace y D:\\Proyecto)."""
    p1 = os.path.join(WORKSPACE_TEST_DIR, rel_subfolder, filename)
    p2 = os.path.join(PROYECTO_TEST_DIR, rel_subfolder, filename)
    with open(p1, "wb") as f:
        f.write(content)
    with open(p2, "wb") as f:
        f.write(content)
    print(f"Guardado: {rel_subfolder}/{filename} ({len(content)} bytes)")


# ==============================================================================
# 1. Requisitos_pendientes_demo.xlsx
# ==============================================================================
def generar_requisitos():
    # Correcto
    df_ok = pd.DataFrame([
        {
            "DOCUMENTO": "1043000100",
            "NOMBRES": "LAURA SOFÍA PÉREZ GÓMEZ",
            "FICHA": "2558701",
            "REQUISITO": "Pruebas Saber TyT",
            "ESTADO": "Cumplido",
            "OBSERVACIONES": "Verificado en plataforma ICFES",
        },
        {
            "DOCUMENTO": "1043000100",
            "NOMBRES": "LAURA SOFÍA PÉREZ GÓMEZ",
            "FICHA": "2558701",
            "REQUISITO": "Paz y Salvo Biblioteca",
            "ESTADO": "Cumplido",
            "OBSERVACIONES": "Paz y salvo emitido sin pendientes",
        },
        {
            "DOCUMENTO": "1043000237",
            "NOMBRES": "CARLOS ANDRÉS RODRÍGUEZ MARTÍNEZ",
            "FICHA": "2558702",
            "REQUISITO": "Comprobante APE",
            "ESTADO": "Cumplido",
            "OBSERVACIONES": "Inscripción APE activa y verificada",
        },
        {
            "DOCUMENTO": "1043000374",
            "NOMBRES": "MARÍA FERNANDA HERNÁNDEZ DÍAZ",
            "FICHA": "2601145",
            "REQUISITO": "Destrucción de Carnet",
            "ESTADO": "Cumplido",
            "OBSERVACIONES": "Entregado en administración educativa",
        },
    ])
    buf_ok = BytesIO()
    df_ok.to_excel(buf_ok, index=False)
    save_file("correctos", "Requisitos_pendientes_demo_correcto.xlsx", buf_ok.getvalue())
    # Tambien actualizamos Requisitos_correcto.xlsx para retrocompatibilidad
    save_file("correctos", "Requisitos_correcto.xlsx", buf_ok.getvalue())

    # Incorrecto: Faltan columnas obligatorias (DOCUMENTO, NOMBRES, REQUISITO, ESTADO)
    df_err = pd.DataFrame([
        {
            "FICHA": "2558701",
            "PROGRAMA": "GESTION EMPRESARIAL",
            "TELEFONO_CONTACTO": "3001234567",
            "OBSERVACIONES": "Falta información de requisitos",
        },
        {
            "FICHA": "2558702",
            "PROGRAMA": "ADSO",
            "TELEFONO_CONTACTO": "3109876543",
            "OBSERVACIONES": "Documento no registrado",
        },
    ])
    buf_err = BytesIO()
    df_err.to_excel(buf_err, index=False)
    save_file("incorrectos", "Requisitos_pendientes_demo_incorrecto.xlsx", buf_err.getvalue())
    save_file("incorrectos", "Requisitos_incorrecto_sin_columnas_clave.xlsx", buf_err.getvalue())


# ==============================================================================
# 2. DF14A_demo.xlsx
# ==============================================================================
def generar_df14a_xlsx():
    # Correcto: Contiene las 11 columnas exactas de DF14A_demo.xlsx con niveles clasificados
    df_ok = pd.DataFrame([
        {
            "TIPO_DOCUMENTO": "CC",
            "DOCUMENTO": "1043000100",
            "NOMBRES": "LAURA SOFÍA PÉREZ GÓMEZ",
            "FICHA": "2558701",
            "PROGRAMA": "GESTION EMPRESARIAL",
            "NIVEL_FORMACION": "TECNÓLOGO",
            "MODALIDAD": "Presencial",
            "FECHA_INICIO": "2024-02-05",
            "FECHA_FIN": "2026-08-05",
            "ESTADO_ASPIRANTE": "Por Certificar",
            "CORREO_ELECTRONICO": "laura.perez@correo-demo.edu.co",
        },
        {
            "TIPO_DOCUMENTO": "CC",
            "DOCUMENTO": "1043000237",
            "NOMBRES": "CARLOS ANDRÉS RODRÍGUEZ MARTÍNEZ",
            "FICHA": "2558702",
            "PROGRAMA": "ANALISIS Y DESARROLLO DE SOFTWARE",
            "NIVEL_FORMACION": "TECNÓLOGO",
            "MODALIDAD": "Presencial",
            "FECHA_INICIO": "2024-02-05",
            "FECHA_FIN": "2026-08-05",
            "ESTADO_ASPIRANTE": "Por Certificar",
            "CORREO_ELECTRONICO": "carlos.rodriguez@correo-demo.edu.co",
        },
        {
            "TIPO_DOCUMENTO": "TI",
            "DOCUMENTO": "1043000374",
            "NOMBRES": "MARÍA FERNANDA HERNÁNDEZ DÍAZ",
            "FICHA": "2601145",
            "PROGRAMA": "ASISTENCIA ADMINISTRATIVA",
            "NIVEL_FORMACION": "TÉCNICO",
            "MODALIDAD": "Presencial",
            "FECHA_INICIO": "2025-01-20",
            "FECHA_FIN": "2026-07-20",
            "ESTADO_ASPIRANTE": "Por Certificar",
            "CORREO_ELECTRONICO": "maria.hernandez@correo-demo.edu.co",
        },
    ])
    buf_ok = BytesIO()
    df_ok.to_excel(buf_ok, index=False)
    save_file("correctos", "DF14A_demo_correcto.xlsx", buf_ok.getvalue())
    save_file("correctos", "DF14A_correcto.xlsx", buf_ok.getvalue())

    # Incorrecto: Omite columna obligatoria FICHA y agrega niveles sin clasificar
    df_err = pd.DataFrame([
        {
            "TIPO_DOCUMENTO": "CC",
            "DOCUMENTO": "1043000100",
            "NOMBRES": "LAURA SOFÍA PÉREZ GÓMEZ",
            "CODIGO_GRUPO": "2558701",  # Renombrado intencionalmente
            "PROGRAMA": "GESTION EMPRESARIAL",
            "NIVEL_FORMACION": "OPERARIO",  # Sin clasificar misional
            "MODALIDAD": "Presencial",
            "FECHA_INICIO": "2024-02-05",
            "FECHA_FIN": "2026-08-05",
            "ESTADO_ASPIRANTE": "Por Certificar",
            "CORREO_ELECTRONICO": "laura.perez@correo-demo.edu.co",
        },
        {
            "TIPO_DOCUMENTO": "CC",
            "DOCUMENTO": "1043000237",
            "NOMBRES": "CARLOS ANDRÉS RODRÍGUEZ MARTÍNEZ",
            "CODIGO_GRUPO": "2558702",
            "PROGRAMA": "ANALISIS Y DESARROLLO DE SOFTWARE",
            "NIVEL_FORMACION": "CURSO_NO_FORMAL",  # Invalido
            "MODALIDAD": "Presencial",
            "FECHA_INICIO": "2024-02-05",
            "FECHA_FIN": "2026-08-05",
            "ESTADO_ASPIRANTE": "Por Certificar",
            "CORREO_ELECTRONICO": "carlos.rodriguez@correo-demo.edu.co",
        },
    ])
    buf_err = BytesIO()
    df_err.to_excel(buf_err, index=False)
    save_file("incorrectos", "DF14A_demo_incorrecto.xlsx", buf_err.getvalue())
    save_file("incorrectos", "DF14A_incorrecto_sin_ficha_y_nivel_invalido.xlsx", buf_err.getvalue())


# ==============================================================================
# 3. DF-14A_1.xml
# ==============================================================================
def generar_df14a_xml():
    # Correcto: Formato SpreadsheetML 2003 con encabezados de DF-14A y columna FICHA
    xml_ok = """<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:html="http://www.w3.org/TR/REC-html40">
  <Worksheet ss:Name="DF-14A">
    <Table>
      <Row><Cell><Data ss:Type="String">DF-14A_</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">MATRICULADOS_RESUMEN_POR_FICHA</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">23-09-2026</Data></Cell></Row>
      <Row>
        <Cell><Data ss:Type="String">CODIGO_REGIONAL</Data></Cell>
        <Cell><Data ss:Type="String">REGIONAL</Data></Cell>
        <Cell><Data ss:Type="String">CODIGO_CENTRO</Data></Cell>
        <Cell><Data ss:Type="String">CENTRO</Data></Cell>
        <Cell><Data ss:Type="String">CODIGO_PROGRAMA</Data></Cell>
        <Cell><Data ss:Type="String">VERSION_PROGRAMA</Data></Cell>
        <Cell><Data ss:Type="String">PROGRAMA</Data></Cell>
        <Cell><Data ss:Type="String">NIVEL_FORMACION</Data></Cell>
        <Cell><Data ss:Type="String">DURACION_MAXIMA</Data></Cell>
        <Cell><Data ss:Type="String">DURACION_ETAPA_LECTIVA</Data></Cell>
        <Cell><Data ss:Type="String">DURACION_ETAPA_PRODUCTIVA</Data></Cell>
        <Cell><Data ss:Type="String">FICHA</Data></Cell>
        <Cell><Data ss:Type="String">FECHA_INICIO_FICHA</Data></Cell>
        <Cell><Data ss:Type="String">FECHA_FIN_FICHA</Data></Cell>
        <Cell><Data ss:Type="String">CUPO</Data></Cell>
        <Cell><Data ss:Type="String">ESTADO_FICHA</Data></Cell>
        <Cell><Data ss:Type="String">TIPO_RESPUESTA</Data></Cell>
        <Cell><Data ss:Type="String">PROGRAMA_ESPECIAL</Data></Cell>
        <Cell><Data ss:Type="String">POR_CERTIFICAR</Data></Cell>
        <Cell><Data ss:Type="String">CERTIFICADO</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">13</Data></Cell>
        <Cell><Data ss:Type="String">REGIONAL BOLÍVAR</Data></Cell>
        <Cell><Data ss:Type="String">9304</Data></Cell>
        <Cell><Data ss:Type="String">CENTRO DE COMERCIO Y SERVICIOS</Data></Cell>
        <Cell><Data ss:Type="String">122115</Data></Cell>
        <Cell><Data ss:Type="String">1</Data></Cell>
        <Cell><Data ss:Type="String">GESTION EMPRESARIAL</Data></Cell>
        <Cell><Data ss:Type="String">TECNÓLOGO</Data></Cell>
        <Cell><Data ss:Type="String">24</Data></Cell>
        <Cell><Data ss:Type="String">18</Data></Cell>
        <Cell><Data ss:Type="String">6</Data></Cell>
        <Cell><Data ss:Type="String">2558701</Data></Cell>
        <Cell><Data ss:Type="String">2024-02-05 00:00:00.0</Data></Cell>
        <Cell><Data ss:Type="String">2026-08-05 00:00:00.0</Data></Cell>
        <Cell><Data ss:Type="String">35</Data></Cell>
        <Cell><Data ss:Type="String">Terminada por fecha</Data></Cell>
        <Cell><Data ss:Type="String">ABIERTA</Data></Cell>
        <Cell><Data ss:Type="String">REGULAR</Data></Cell>
        <Cell><Data ss:Type="String">1</Data></Cell>
        <Cell><Data ss:Type="String">28</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">13</Data></Cell>
        <Cell><Data ss:Type="String">REGIONAL BOLÍVAR</Data></Cell>
        <Cell><Data ss:Type="String">9304</Data></Cell>
        <Cell><Data ss:Type="String">CENTRO DE COMERCIO Y SERVICIOS</Data></Cell>
        <Cell><Data ss:Type="String">228106</Data></Cell>
        <Cell><Data ss:Type="String">2</Data></Cell>
        <Cell><Data ss:Type="String">ANALISIS Y DESARROLLO DE SOFTWARE</Data></Cell>
        <Cell><Data ss:Type="String">TECNÓLOGO</Data></Cell>
        <Cell><Data ss:Type="String">24</Data></Cell>
        <Cell><Data ss:Type="String">18</Data></Cell>
        <Cell><Data ss:Type="String">6</Data></Cell>
        <Cell><Data ss:Type="String">2558702</Data></Cell>
        <Cell><Data ss:Type="String">2024-02-05 00:00:00.0</Data></Cell>
        <Cell><Data ss:Type="String">2026-08-05 00:00:00.0</Data></Cell>
        <Cell><Data ss:Type="String">30</Data></Cell>
        <Cell><Data ss:Type="String">Terminada por fecha</Data></Cell>
        <Cell><Data ss:Type="String">ABIERTA</Data></Cell>
        <Cell><Data ss:Type="String">REGULAR</Data></Cell>
        <Cell><Data ss:Type="String">2</Data></Cell>
        <Cell><Data ss:Type="String">25</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">13</Data></Cell>
        <Cell><Data ss:Type="String">REGIONAL BOLÍVAR</Data></Cell>
        <Cell><Data ss:Type="String">9304</Data></Cell>
        <Cell><Data ss:Type="String">CENTRO DE COMERCIO Y SERVICIOS</Data></Cell>
        <Cell><Data ss:Type="String">134101</Data></Cell>
        <Cell><Data ss:Type="String">1</Data></Cell>
        <Cell><Data ss:Type="String">ASISTENCIA ADMINISTRATIVA</Data></Cell>
        <Cell><Data ss:Type="String">TÉCNICO</Data></Cell>
        <Cell><Data ss:Type="String">12</Data></Cell>
        <Cell><Data ss:Type="String">6</Data></Cell>
        <Cell><Data ss:Type="String">6</Data></Cell>
        <Cell><Data ss:Type="String">2601145</Data></Cell>
        <Cell><Data ss:Type="String">2025-01-20 00:00:00.0</Data></Cell>
        <Cell><Data ss:Type="String">2026-07-20 00:00:00.0</Data></Cell>
        <Cell><Data ss:Type="String">30</Data></Cell>
        <Cell><Data ss:Type="String">Terminada por fecha</Data></Cell>
        <Cell><Data ss:Type="String">ABIERTA</Data></Cell>
        <Cell><Data ss:Type="String">REGULAR</Data></Cell>
        <Cell><Data ss:Type="String">1</Data></Cell>
        <Cell><Data ss:Type="String">22</Data></Cell>
      </Row>
    </Table>
  </Worksheet>
</Workbook>"""
    save_file("correctos", "DF_14A_1_correcto.xml", xml_ok.encode("utf-8"))

    # Incorrecto: Falta columna FICHA (sustituida por CODIGO_CURSO) y niveles no clasificados
    xml_err = """<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:html="http://www.w3.org/TR/REC-html40">
  <Worksheet ss:Name="DF-14A">
    <Table>
      <Row><Cell><Data ss:Type="String">DF-14A_</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">MATRICULADOS_RESUMEN_POR_FICHA</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">23-09-2026</Data></Cell></Row>
      <Row>
        <Cell><Data ss:Type="String">CODIGO_REGIONAL</Data></Cell>
        <Cell><Data ss:Type="String">PROGRAMA</Data></Cell>
        <Cell><Data ss:Type="String">NIVEL_FORMACION</Data></Cell>
        <Cell><Data ss:Type="String">CODIGO_CURSO</Data></Cell> <!-- Falta FICHA -->
        <Cell><Data ss:Type="String">POR_CERTIFICAR</Data></Cell>
        <Cell><Data ss:Type="String">CERTIFICADO</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">13</Data></Cell>
        <Cell><Data ss:Type="String">CURSO CORTO DE SOLDADURA</Data></Cell>
        <Cell><Data ss:Type="String">OPERARIO</Data></Cell> <!-- Nivel sin clasificar -->
        <Cell><Data ss:Type="String">9999001</Data></Cell>
        <Cell><Data ss:Type="String">2</Data></Cell>
        <Cell><Data ss:Type="String">10</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">13</Data></Cell>
        <Cell><Data ss:Type="String">TALLER ESPECIAL</Data></Cell>
        <Cell><Data ss:Type="String">COMPLEMENTARIA VIRTUAL</Data></Cell> <!-- Nivel sin clasificar -->
        <Cell><Data ss:Type="String">9999002</Data></Cell>
        <Cell><Data ss:Type="String">5</Data></Cell>
        <Cell><Data ss:Type="String">15</Data></Cell>
      </Row>
    </Table>
  </Worksheet>
</Workbook>"""
    save_file("incorrectos", "DF_14A_1_incorrecto.xml", xml_err.encode("utf-8"))


# ==============================================================================
# 4. ACTAS 2026(PENDIENTES).csv
# ==============================================================================
def generar_actas_pendientes_csv():
    # Las 31 columnas exactas del archivo original
    cols = [
        "ITEM", "NIVEL", "FICHA", "PROGRAMA", "NÚMERO DE DOCUMENTO", "NOMBRE",
        "APELLIDOS", "INSTRUCTOR DE SEGUIMIENTO", "ACTA", "CORREO",
        "FECHA DE RECIBIDO EN ADMON EDUCATIVA", "BIBLIOTECA",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)", "BIENESTAR DEL APRENDIZ",
        "FECHA DE RECIBIDO (BIENESTAR DEL APRENDIZ)", "ALMACEN",
        "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)", "TIPO DE ENTREGA DE DOCUMENTOS",
        "Formato de Evaluación de la Etapa Productiva:",
        "Copia del Documento de Identidad vigente",
        "Evidencia de la presentación de las\npruebas Saber T y T. ( SOLO TGO)",
        "Comprobante de inscripción en la APE- Agencia Pública de empleo",
        "Comprobante de Destrucción de Carnet.", "Certificado de la Empresa",
        "ESTADO", "MOTIVO DE NO CERTIFICACION", "FECHA TERMINACIÓN DE FICHA ",
        "FICHA DESPUES DE DOS AÑOS", "FECHA DE EVALUACIÓN", "TELEFONO ", "Unnamed: 30"
    ]

    # Correcto: Niveles Tecnólogo / Técnico / SENATIC, estados PENDIENTE, columnas completas
    rows_ok = [
        [
            1, "TECNÓLOGO", 2558701, "GESTION EMPRESARIAL", 1043000100, "LAURA SOFÍA",
            "PÉREZ GÓMEZ", "JORGE PINEDO", 362025, "laura.perez@correo.edu.co",
            "12/03/2026", "X", "15/03/2026", "X", "16/03/2026", "X", "18/03/2026",
            "DIGITAL", "N.A", "X", "X", "X", "X", "N.A", "PENDIENTE", "No anexa T&T",
            "10/01/2025", "10/01/2027", "20/02/2026", "3001234567", None
        ],
        [
            2, "TECNÓLOGO", 2558702, "ANALISIS Y DESARROLLO DE SOFTWARE", 1043000237, "CARLOS ANDRÉS",
            "RODRÍGUEZ MARTÍNEZ", "OSCAR DAVID RAMOS", 362025, "carlos.rodriguez@correo.edu.co",
            "12/03/2026", "X", "15/03/2026", "X", "16/03/2026", "X", "18/03/2026",
            "DIGITAL", "N.A", "X", "X", "X", "X", "N.A", "PENDIENTE", "APE",
            "10/01/2025", "10/01/2027", "20/02/2026", "3109876543", None
        ],
        [
            3, "TÉCNICO", 2601145, "ASISTENCIA ADMINISTRATIVA", 1043000374, "MARÍA FERNANDA",
            "HERNÁNDEZ DÍAZ", "TATIANA ORTEGA", 372026, "maria.hernandez@correo.edu.co",
            "14/04/2026", "X", "18/04/2026", "X", "19/04/2026", "X", "20/04/2026",
            "DIGITAL", "N.A", "X", "N.A", "X", "X", "N.A", "PENDIENTE", "Documento de Identidad",
            "20/07/2025", "20/07/2027", "10/04/2026", "3154567890", None
        ],
        [
            4, "SENATIC", 3007863, "SISTEMAS TELEINFORMÁTICOS", 1043000485, "DIEGO ALEJANDRO",
            "CASTRO MORA", "CARLOS GOMEZ", 382026, "diego.castro@correo.edu.co",
            "10/05/2026", "X", "12/05/2026", "X", "13/05/2026", "X", "14/05/2026",
            "DIGITAL", "N.A", "X", "N.A", "X", "X", "N.A", "PENDIENTE", "Destrucción del Carnet",
            "15/09/2025", "15/09/2027", "05/05/2026", "3201122334", None
        ],
    ]
    df_csv_ok = pd.DataFrame(rows_ok, columns=cols)
    csv_ok_bytes = df_csv_ok.to_csv(index=False, encoding="utf-8").encode("utf-8")
    save_file("correctos", "ACTAS_2026_PENDIENTES_completo_correcto.csv", csv_ok_bytes)
    save_file("correctos", "ACTAS_2026_PENDIENTES_correcto.csv", csv_ok_bytes)

    # Incorrecto: Sin columnas obligatorias (NÚMERO DE DOCUMENTO y NOMBRE renombrados) y nivel OPERARIO
    rows_err = [
        [
            1, "OPERARIO", 2558701, "GESTION EMPRESARIAL", 1043000100, "LAURA SOFÍA",
            "PÉREZ GÓMEZ", "JORGE PINEDO", 362025, "laura.perez@correo.edu.co",
            "12/03/2026", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", None, None, None, None, "N.A", "PENDIENTE", "No anexa T&T",
            "10/01/2025", "10/01/2027", "20/02/2026", "3001234567", None
        ],
        [
            2, "NIVEL_DESCONOCIDO", 2558702, "ADSO", 1043000237, "CARLOS ANDRÉS",
            "RODRÍGUEZ MARTÍNEZ", "OSCAR DAVID RAMOS", 362025, "carlos.rodriguez@correo.edu.co",
            "12/03/2026", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", None, None, None, None, "N.A", "PENDIENTE", "APE",
            "10/01/2025", "10/01/2027", "20/02/2026", "3109876543", None
        ],
    ]
    # Alteramos encabezados clave para que falten
    cols_err = list(cols)
    cols_err[4] = "ID_REGISTRO_EXTERNO"   # era NÚMERO DE DOCUMENTO
    cols_err[5] = "NOMBRE_COMPLETO"       # era NOMBRE
    df_csv_err = pd.DataFrame(rows_err, columns=cols_err)
    csv_err_bytes = df_csv_err.to_csv(index=False, encoding="utf-8").encode("utf-8")
    save_file("incorrectos", "ACTAS_2026_PENDIENTES_incorrecto.csv", csv_err_bytes)
    save_file("incorrectos", "ACTAS_2026_PENDIENTES_incorrecto_sin_documento.csv", csv_err_bytes)


# ==============================================================================
# 5. Acta_certificacion_23_demo.docx
# ==============================================================================
def generar_acta_docx():
    # Correcto: Documento Word formal con encabezado y tabla de aprendices
    doc_ok = Document()
    doc_ok.add_paragraph("ACTA DE CERTIFICACIÓN No. 23")
    doc_ok.add_paragraph("Centro de Comercio y Servicios – Regional Bolívar")
    doc_ok.add_paragraph("Fecha: 02 de octubre de 2026")
    doc_ok.add_paragraph("Remitida por: Coordinación Académica (datos de demostración)")
    doc_ok.add_paragraph("Asunto: Relación de aprendices en estado 'Por Certificar' para trámite de certificación.")
    doc_ok.add_paragraph("")
    doc_ok.add_paragraph("Total de aprendices relacionados: 3")

    # Tabla con 5 columnas
    table = doc_ok.add_table(rows=4, cols=5)
    headers = ["No.", "Documento", "Nombre", "Ficha", "Programa"]
    for col_idx, h in enumerate(headers):
        table.cell(0, col_idx).text = h

    data = [
        ("1", "1043000100", "LAURA SOFÍA PÉREZ GÓMEZ", "2558701", "Tecnólogo en Gestión Empresarial"),
        ("2", "1043000237", "CARLOS ANDRÉS RODRÍGUEZ MARTÍNEZ", "2558702", "Tecnólogo en Análisis y Desarrollo de Software"),
        ("3", "1043000374", "MARÍA FERNANDA HERNÁNDEZ DÍAZ", "2601145", "Técnico en Asistencia Administrativa"),
    ]
    for row_idx, row_vals in enumerate(data, start=1):
        for col_idx, val in enumerate(row_vals):
            table.cell(row_idx, col_idx).text = val

    buf_doc_ok = BytesIO()
    doc_ok.save(buf_doc_ok)
    save_file("correctos", "Acta_certificacion_23_demo_correcto.docx", buf_doc_ok.getvalue())

    # Incorrecto: Documento vacío sin párrafos ni tablas (dispara ValueError en validation.py)
    doc_err = Document()
    buf_doc_err = BytesIO()
    doc_err.save(buf_doc_err)
    save_file("incorrectos", "Acta_certificacion_23_demo_incorrecto_vacio.docx", buf_doc_err.getvalue())


# ==============================================================================
# 6. ACTAS 2026.xlsx (Documentos positivos / paquete institucional completo)
# ==============================================================================
def generar_actas_institucional_xlsx():
    # Hojas operativas: CERTIFICADOS, PENDIENTES, COMPLEMENTARIA, META
    cols_cert = [
        "ITEM", "NIVEL", "FICHA", "PROGRAMA", "NÚMERO DE DOCUMENTO", "NOMBRE",
        "APELLIDOS", "INSTRUCTOR DE SEGUIMIENTO", "ACTA", "CORREO",
        "FECHA DE RECIBIDO EN ADMON EDUCATIVA", "BIBLIOTECA",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)", "BIENESTAR DEL APRENDIZ",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIENESTAR)", "ALMACEN",
        "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)", "TIPO DE ENTREGA DE DOCUMENTOS",
        "Formato de Evaluación de la Etapa Productiva:",
        "Copia del Documento de Identidad vigente",
        "Evidencia de la presentación de las\npruebas Saber T y T. ( SOLO TGO)",
        "Comprobante de inscripción en la APE- Agencia Pública de empleo",
        "Comprobante de Destrucción de Carnet.", "Certificado de la Empresa",
        "ESTADO", "MES DE CERTIFICACIÓN ", "FECHA TERMINACIÓN DE FICHA ",
        "FICHA DESPUES DE DOS AÑOS", "FECHA DE EVALUACIÓN", "Unnamed: 29"
    ]

    cols_pend = [
        "ITEM", "NIVEL", "FICHA", "PROGRAMA", "NÚMERO DE DOCUMENTO", "NOMBRE",
        "APELLIDOS", "INSTRUCTOR DE SEGUIMIENTO", "ACTA", "CORREO",
        "FECHA DE RECIBIDO EN ADMON EDUCATIVA", "BIBLIOTECA",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)", "BIENESTAR DEL APRENDIZ",
        "FECHA DE RECIBIDO (BIENESTAR DEL APRENDIZ)", "ALMACEN",
        "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)", "TIPO DE ENTREGA DE DOCUMENTOS",
        "Formato de Evaluación de la Etapa Productiva:",
        "Copia del Documento de Identidad vigente",
        "Evidencia de la presentación de las\npruebas Saber T y T. ( SOLO TGO)",
        "Comprobante de inscripción en la APE- Agencia Pública de empleo",
        "Comprobante de Destrucción de Carnet.", "Certificado de la Empresa",
        "ESTADO", "MOTIVO DE NO CERTIFICACION", "FECHA TERMINACIÓN DE FICHA ",
        "FICHA DESPUES DE DOS AÑOS", "FECHA DE EVALUACIÓN", "TELEFONO ", "Unnamed: 30"
    ]

    # --- VERSION CORRECTA ---
    # 4 certificados sin conflicto con pendientes
    cert_rows_ok = [
        [
            1, "TECNÓLOGO", 2847836, "GESTION ADMINISTRATIVA", 1043966273, "DANNER DAIR",
            "CORREA MARTINEZ", "EDUARDO VILLANUEVA", 362025, "danner@correo.edu.co",
            "11/05/2025", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", "X", "X", "X", "X", "N.A", "CERTIFICADOS", "ENERO",
            "03/10/2025", "03/04/2027", "11/05/2025", None
        ],
        [
            2, "TECNÓLOGO", 2847836, "GESTION ADMINISTRATIVA", 1043966274, "ANDREA PAOLA",
            "GARCIA DIAZ", "EDUARDO VILLANUEVA", 362025, "andrea@correo.edu.co",
            "11/05/2025", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", "X", "X", "X", "X", "N.A", "CERTIFICADOS", "FEBRERO",
            "03/10/2025", "03/04/2027", "11/05/2025", None
        ],
        [
            3, "TÉCNICO", 2618155, "COMERCIO INTERNACIONAL", 1007977943, "ANIBAL SEGUNDO",
            "HERNANDEZ VEGA", "JUAN ATENCIO", 52025, "anibal@correo.edu.co",
            "20/03/2025", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", "X", "X", "X", "X", "N.A", "CERTIFICADOS", "MARZO",
            "05/09/2023", "05/03/2025", "14/03/2025", None
        ],
        [
            4, "MEDIA TECNICA", 2920809, "SERVICIOS DE BARISMO", 1043975791, "ANDRES FELIPE",
            "MARTINEZ RAMIREZ", "ANDIS ANAYA", 2025, "andres@correo.edu.co",
            "27/11/2025", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", "X", "N.A", "X", "X", "N.A", "CERTIFICADOS", "ABRIL",
            "20/11/2025", "20/11/2027", "25/11/2025", None
        ],
    ]

    # 4 pendientes sin coincidir en cédula/ficha con certificados
    pend_rows_ok = [
        [
            1, "TECNÓLOGO", 1965912, "DIRECCION DE VENTAS", 1143374709, "GERSON JAVIER",
            "DIAZ NUÑEZ", "FIDIAS MANYOMA", 162025, "gerson@correo.edu.co",
            "12/06/2025", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", None, None, None, None, "N.A", "PENDIENTE", "No anexa T&T",
            "07/10/2021", "07/04/2023", "23/05/2024", "3001112233", None
        ],
        [
            2, "TECNÓLOGO", 2374476, "ADSI", 79889414, "JESUS ADRIAN",
            "PUERTA FANDIÑO", "CARLOS MUÑOZ EBRATT", 22025, "adrian@correo.edu.co",
            "26/02/2025", "X", "28/02/2025", "X", "03/03/2025", "X", None,
            "DIGITAL", "N.A", None, None, None, None, "N.A", "PENDIENTE", "APE",
            "02/08/2023", "02/02/2025", "17/02/2025", "3112223344", None
        ],
        [
            3, "TÉCNICO", 2834367, "ASESORIA COMERCIAL", 1112789584, "LEIDY NATHALIA",
            "CARDONA ESCOBAR", "ERNESTO GUZMAN", 122025, "leidy@correo.edu.co",
            "14/05/2025", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", None, None, None, None, "N.A", "PENDIENTE", "Carta Carnet Sin Firma",
            "10/12/2024", "10/06/2026", "08/05/2025", "3223334455", None
        ],
        [
            4, "SENATIC", 3007871, "SISTEMAS TELEINFORMÁTICOS", 1201214756, "DALIA MARCELA",
            "GONZALEZ OROZCO", "MARCO ALMANZA", 2025, "dalia@correo.edu.co",
            "14/09/2025", "X", None, "X", None, "X", None,
            "DIGITAL", "N.A", "X", "N.A", "X", "X", "N.A", "PENDIENTE", "Documento Vencido",
            "10/09/2025", "10/09/2027", "12/09/2025", "3334445566", None
        ],
    ]

    # Matriz complementaria (Presencial col 0-1, Virtual col 3-4, Campesena col 7-8, Full Popular col 10-11)
    comp_rows_ok = [
        ["FECHA", "N° DE CERTIFICADOS", None, "FECHA", "N° DE CERTIFICADOS VIRTUAL", None, None, "FECHA", "N° CERTIFICADOS CAMPESENA", None, "FECHA", "N° CERTIFICADOS FULL POPULAR"],
        ["26/02/2026", 15, None, "26/02/2026", 80, None, None, "26/02/2026", 10, None, "26/02/2026", 5],
        ["13/03/2026", 25, None, "13/03/2026", 120, None, None, "13/03/2026", 18, None, "13/03/2026", 12],
        ["20/04/2026", 40, None, "20/04/2026", 95, None, None, "20/04/2026", 22, None, "20/04/2026", 8],
    ]

    # Matriz META
    meta_rows_ok = [
        ["METAS DE CERTIFICACIÓN"],
        [
            "TECNICO LABORAL Y OTROS",
            "ARTICULACION CON LA MEDIA",
            "EDUCACIÓN SUPERIOR",
            "TOTAL TITULADA",
            "TOTAL COMPLEMENTARIA",
            "TOTAL FORMACIÓN PROFESIONAL",
        ],
        [1910, 1995, 943, 4848, 83726, 88574],
    ]

    buf_actas_ok = BytesIO()
    with pd.ExcelWriter(buf_actas_ok, engine="openpyxl") as writer:
        pd.DataFrame(cert_rows_ok, columns=cols_cert).to_excel(writer, sheet_name="CERTIFICADOS", index=False)
        pd.DataFrame(pend_rows_ok, columns=cols_pend).to_excel(writer, sheet_name="PENDIENTES", index=False)
        pd.DataFrame(comp_rows_ok).to_excel(writer, sheet_name="COMPLEMENTARIA", index=False, header=False)
        pd.DataFrame(meta_rows_ok).to_excel(writer, sheet_name="META", index=False, header=False)

    save_file("correctos", "ACTAS_2026_institucional_correcto.xlsx", buf_actas_ok.getvalue())
    save_file("correctos", "ACTAS_2026_correcto.xlsx", buf_actas_ok.getvalue())

    # --- VERSION INCORRECTA ---
    # Provocamos:
    # 1. Conflicto cruzado: Aprendiz 1043966273 con ficha 2847836 está en CERTIFICADOS y en PENDIENTES
    # 2. Mes de certificación fuera del corte: DICIEMBRE
    # 3. Nivel de formación no clasificado: OPERARIO
    # 4. Falta la hoja COMPLEMENTARIA
    cert_rows_err = list(cert_rows_ok)
    # Cambiamos mes a DICIEMBRE para provocar advertencia de fecha/corte
    cert_rows_err[0][25] = "DICIEMBRE"

    pend_rows_err = list(pend_rows_ok)
    # Agregamos al aprendiz 1043966273 / ficha 2847836 (conflicto con certificado 1) y con nivel OPERARIO
    pend_rows_err.append([
        5, "OPERARIO", 2847836, "GESTION ADMINISTRATIVA", 1043966273, "DANNER DAIR",
        "CORREA MARTINEZ", "EDUARDO VILLANUEVA", 362025, "danner@correo.edu.co",
        "11/05/2025", "X", None, "X", None, "X", None,
        "DIGITAL", "N.A", None, None, None, None, "N.A", "PENDIENTE", "No anexa T&T",
        "03/10/2025", "03/04/2027", "11/05/2025", "3009998877", None
    ])

    buf_actas_err = BytesIO()
    with pd.ExcelWriter(buf_actas_err, engine="openpyxl") as writer:
        pd.DataFrame(cert_rows_err, columns=cols_cert).to_excel(writer, sheet_name="CERTIFICADOS", index=False)
        pd.DataFrame(pend_rows_err, columns=cols_pend).to_excel(writer, sheet_name="PENDIENTES", index=False)
        # Omitimos hoja COMPLEMENTARIA intencionalmente
        pd.DataFrame(meta_rows_ok).to_excel(writer, sheet_name="META", index=False, header=False)

    save_file("incorrectos", "ACTAS_2026_institucional_incorrecto.xlsx", buf_actas_err.getvalue())
    save_file("incorrectos", "ACTAS_2026_incorrecto_conflictos_y_meses.xlsx", buf_actas_err.getvalue())


def main():
    print("=== Generando Archivos de Prueba ===")
    generar_requisitos()
    generar_df14a_xlsx()
    generar_df14a_xml()
    generar_actas_pendientes_csv()
    generar_acta_docx()
    generar_actas_institucional_xlsx()
    print("=== Generación Finalizada con Éxito ===")


if __name__ == "__main__":
    main()
