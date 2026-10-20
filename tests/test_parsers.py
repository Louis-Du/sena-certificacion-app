"""
Pruebas de los lectores de documentos fuente (``app.services.parsers``).

Que se verifica aqui
--------------------
1. Lectura de las hojas relevantes de ``ACTAS 2026.xlsx`` (CERTIFICADOS,
   PENDIENTES, COMPLEMENTARIA y META).
2. Clasificacion misional por NIVEL de formacion y normalizacion de variantes
   de escritura ("TECNÓLOGO" vs "TECNOLOGO").
3. Separacion de motivos de no certificacion en incidencias.
4. Extraccion de la tabla de referencia del informe de gestion en Word.

Los datos usados son pequenos y controlados: NO se reproducen cifras
institucionales reales, para no confundir el resultado de una prueba con un
dato oficial.
"""

from io import BytesIO

import pandas as pd

from app.services.parsers import (
    classify_nivel,
    extract_corte_referencia,
    frame_to_records,
    list_excel_sheets,
    normalize_nivel,
    parse_acta_docx,
    parse_df14a_xml,
    parse_informe_referencia,
    read_actas_csv_records,
    read_certificados_records,
    read_complementaria_records,
    read_meta_sheet,
    read_pendientes_records,
    split_motivos,
)
from app.services.validation import check_required_columns, normalize_column_name
from tests.conftest import docx_bytes


# ---------------------------------------------------------------------------
# Utilidades para construir archivos de prueba en memoria
# ---------------------------------------------------------------------------
def _multi_sheet_xlsx(sheets: dict[str, list[dict]]) -> bytes:
    """Construye un .xlsx en memoria con varias hojas (encabezados en fila 1)."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def _actas_xlsx(
    certificados: list[dict],
    pendientes: list[dict],
    complementaria: list[list],
    meta: list[list],
) -> bytes:
    """
    Construye un archivo compatible con ``ACTAS 2026.xlsx``.

    * CERTIFICADOS y PENDIENTES se escriben con encabezados (como el archivo real).
    * COMPLEMENTARIA se escribe SIN encabezado porque el lector ubica las columnas
      por posicion, no por nombre.
    * META se escribe SIN encabezado porque son rotulos y valores en celdas sueltas.
    """
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(certificados).to_excel(writer, sheet_name="CERTIFICADOS", index=False)
        pd.DataFrame(pendientes).to_excel(writer, sheet_name="PENDIENTES", index=False)
        pd.DataFrame(complementaria).to_excel(
            writer, sheet_name="COMPLEMENTARIA", index=False, header=False
        )
        pd.DataFrame(meta).to_excel(writer, sheet_name="META", index=False, header=False)
    return buffer.getvalue()


def _certificados_sheet() -> pd.DataFrame:
    """Hoja CERTIFICADOS minima: encabezados reales + dos filas de datos."""
    return pd.DataFrame(
        {
            "NIVEL": ["TECNÓLOGO", "TÉCNICO"],
            "NÚMERO DE DOCUMENTO": [1001, 1002],
            "NOMBRE": ["Ana", "Luis"],
            "FICHA": [3001, 3002],
            "ACTA": [36, 36],
            "ESTADO": ["CERTIFICADOS", "CERTIFICADOS"],
            "MES DE CERTIFICACIÓN": ["JUNIO", "OCTUBRE"],
        }
    )


def _pendientes_sheet() -> pd.DataFrame:
    """Hoja PENDIENTES minima con un motivo compuesto (dos causas en una celda)."""
    return pd.DataFrame(
        {
            "NIVEL": ["SENATIC"],
            "NÚMERO DE DOCUMENTO": [2001],
            "NOMBRE": ["Marta"],
            "FICHA": [4001],
            "ESTADO": ["PENDIENTE"],
            "MOTIVO DE NO CERTIFICACIÓN": ["APE, No anexa T&T"],
        }
    )


def _meta_rows() -> list[list]:
    """Rotulos y valores de la hoja META (fila 1 = rotulos, fila 2 = valores)."""
    return [
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


# ---------------------------------------------------------------------------
# 1. Lectura de las hojas de ACTAS 2026.xlsx
# ---------------------------------------------------------------------------
def test_list_excel_sheets_detects_multiple_sheets():
    content = _multi_sheet_xlsx(
        {
            "CERTIFICADOS": [{"NÚMERO DE DOCUMENTO": "1", "NOMBRE": "Ana"}],
            "PENDIENTES": [{"NÚMERO DE DOCUMENTO": "2", "NOMBRE": "Luis"}],
        }
    )
    sheets = list_excel_sheets(content)
    assert "CERTIFICADOS" in sheets
    assert "PENDIENTES" in sheets


def test_read_certificados_records_reads_that_sheet_and_normalizes_fields():
    content = _actas_xlsx(
        certificados=_certificados_sheet().to_dict(orient="records"),
        pendientes=_pendientes_sheet().to_dict(orient="records"),
        complementaria=[],
        meta=_meta_rows(),
    )

    registros = read_certificados_records(content)

    assert len(registros) == 2
    # Los campos internos van en minusculas y sin tildes (independientes del Excel).
    assert registros[0]["numero de documento"] == "1001"
    assert registros[0]["nivel"] == "TECNÓLOGO"
    assert registros[0]["estado"] == "CERTIFICADOS"
    assert registros[0]["mes de certificacion"] == "JUNIO"
    # No debe leer la hoja PENDIENTES (documento 2001 no aparece).
    assert all(r.get("numero de documento") != "2001" for r in registros)


def test_read_pendientes_records_reads_that_sheet():
    content = _actas_xlsx(
        certificados=_certificados_sheet().to_dict(orient="records"),
        pendientes=_pendientes_sheet().to_dict(orient="records"),
        complementaria=[],
        meta=_meta_rows(),
    )

    registros = read_pendientes_records(content)

    assert len(registros) == 1
    assert registros[0]["numero de documento"] == "2001"
    assert registros[0]["estado"] == "PENDIENTE"
    assert registros[0]["motivo de no certificacion"] == "APE, No anexa T&T"


def test_read_actas_csv_records_normalizes_headers_like_the_excel_sheet():
    """
    Regresion: un CSV de pendientes debe normalizar igual que la hoja de Excel.

    El archivo real "ACTAS 2026(PENDIENTES).csv" llega en codificacion cp1252 y
    con encabezados en mayusculas y con tildes ("NÚMERO DE DOCUMENTO",
    "MOTIVO DE NO CERTIFICACIÓN"). Si esos encabezados no se normalizaran, el
    calculo de indicadores no encontraria las columnas y reportaria 0
    pendientes: un cero falso, no un dato real.
    """
    contenido = (
        "ITEM,NIVEL,FICHA,PROGRAMA,NÚMERO DE DOCUMENTO,NOMBRE,APELLIDOS,ESTADO,"
        "MOTIVO DE NO CERTIFICACIÓN\n"
        "1,SENATIC,4001,ADSO,2001,Marta,Rojas,PENDIENTE,\"APE, No anexa T&T\"\n"
    ).encode("cp1252")

    registros = read_actas_csv_records(contenido)

    assert len(registros) == 1
    # Las claves deben ser los nombres internos (minusculas y sin tildes).
    assert registros[0]["numero de documento"] == "2001"
    assert registros[0]["estado"] == "PENDIENTE"
    assert registros[0]["motivo de no certificacion"] == "APE, No anexa T&T"
    assert registros[0]["nivel"] == "SENATIC"


def test_read_complementaria_records_aggregates_by_channel_position():
    # Columnas: 0-1 presencial, 3-4 virtual, 7-8 campesena, 10-11 full popular.
    filas = [
        ["2026-02-26", 100, None, "2026-03-10", 40, None, None, "2026-04-01", 5, None, "2026-05-01", 7],
        ["2026-07-15", 50, None, None, None, None, None, None, None, None, None, None],
    ]
    content = _actas_xlsx([], [], filas, _meta_rows())

    registros = read_complementaria_records(content)
    total_por_canal: dict[str, int] = {}
    for registro in registros:
        total_por_canal[registro["canal"]] = total_por_canal.get(registro["canal"], 0) + registro["cantidad"]

    assert total_por_canal["presencial"] == 150
    assert total_por_canal["virtual"] == 40
    assert total_por_canal["campesena"] == 5
    assert total_por_canal["fullpopular"] == 7
    # Las cantidades vacias no generan registros.
    assert all(r["cantidad"] for r in registros)


def test_read_meta_sheet_returns_only_documented_metas():
    contenido = _multi_sheet_xlsx({"META": [{"A": "otra cosa"}]})
    assert read_meta_sheet(contenido) == {}

    content = _actas_xlsx([], [], [], _meta_rows())
    metas = read_meta_sheet(content)

    assert metas["superior"] == 943
    assert metas["tecnica"] == 1910
    assert metas["articulacion"] == 1995
    assert metas["complementaria"] == 83726
    # Queda rastro de la fila y columna de origen (trazabilidad).
    assert metas["fila_rotulos"] == 2


# ---------------------------------------------------------------------------
# 2. Clasificacion misional y normalizacion de NIVEL
# ---------------------------------------------------------------------------
def test_classify_nivel_maps_every_documented_level():
    # Educacion Superior -> Tecnologo.
    assert classify_nivel("TECNÓLOGO") == "superior"
    # Tecnica Laboral y Otros -> Tecnico, Auxiliar, Profundizacion Tecnica, SENATIC.
    assert classify_nivel("TÉCNICO") == "tecnica"
    assert classify_nivel("AUXILIAR") == "tecnica"
    assert classify_nivel("PROFUNDIZACIÓN TÉCNICA") == "tecnica"
    assert classify_nivel("SENATIC") == "tecnica"
    # Articulacion con la Media -> Media Tecnica.
    assert classify_nivel("MEDIA TÉCNICA") == "articulacion"


def test_classify_nivel_returns_none_when_there_is_no_documented_rule():
    # OPERARIO no esta en la regla institucional: NO se asigna por defecto.
    assert classify_nivel("OPERARIO") is None
    assert classify_nivel("") is None
    assert classify_nivel(None) is None
    assert classify_nivel("NIVEL DESCONOCIDO") is None


def test_normalize_nivel_handles_writing_variants():
    # Variantes de tildes y plurales deben caer en el mismo valor canonico.
    assert normalize_nivel("TÉCNOLOGO") == normalize_nivel("TECNÓLOGO") == "tecnologo"
    assert normalize_nivel("profundacion tecnica") == "profundizacion tecnica"
    assert normalize_nivel("PROFUNDIZACIÓN TÉCNICA") == "profundizacion tecnica"
    assert normalize_nivel("tecnicos") == "tecnico"


# ---------------------------------------------------------------------------
# 3. Motivos de no certificacion
# ---------------------------------------------------------------------------
def test_split_motivos_separates_causes_in_one_cell():
    motivos = split_motivos("APE, No anexa T&T")
    assert motivos == ["ape", "no anexa t&t"]

    # Sin repeticiones dentro de la misma celda y sin elementos vacios.
    assert split_motivos("APE, APE, ") == ["ape"]
    assert split_motivos(None) == []
    assert split_motivos(float("nan")) == []


# ---------------------------------------------------------------------------
# 4. Tabla de referencia del informe de gestion (Word)
# ---------------------------------------------------------------------------
def _informe_docx() -> bytes:
    """Construye un .docx con la tabla de referencia (encabezado + 3 filas)."""
    from docx import Document

    document = Document()
    document.add_paragraph("Informe de Gestion Administrativa")
    # El informe real escribe la fecha con el mes primero: "Junio 30 de 2026".
    document.add_paragraph("Corte: Junio 30 de 2026")
    table = document.add_table(rows=4, cols=5)
    encabezado = ["INDICADOR", "META ANUAL", "Nº CERTIFICADOS / EJECUCIÓN", "PENDIENTES POR CUMPLIR", "AVANCE %"]
    for columna, texto in enumerate(encabezado):
        table.cell(0, columna).text = texto
    filas = [
        ["Educación Superior", "943", "566", "377", "60"],
        ["Técnica Laboral y Otros", "1910", "572", "1338", "30"],
        ["Articulación con la Media", "1995", "49", "1946", "2"],
    ]
    for indice, fila in enumerate(filas, start=1):
        for columna, texto in enumerate(fila):
            table.cell(indice, columna).text = texto
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_parse_informe_referencia_extracts_reference_table():
    registros = parse_informe_referencia(_informe_docx())

    por_categoria = {r["categoria"]: r for r in registros}
    assert por_categoria["superior"]["meta"] == 943
    assert por_categoria["superior"]["ejecucion"] == 566
    assert por_categoria["tecnica"]["meta"] == 1910
    assert por_categoria["articulacion"]["meta"] == 1995
    # Cada fila conserva su ubicacion (tabla y fila) para poder auditarla.
    assert por_categoria["superior"]["tabla"] == 1
    assert por_categoria["superior"]["fila"] == 2


def test_extract_corte_referencia_reads_declared_date():
    assert extract_corte_referencia(_informe_docx()) == "2026-06-30"
    # Un documento sin fecha declarada no debe inventar una.
    assert extract_corte_referencia(docx_bytes("Sin fecha de corte")) is None


def test_extract_corte_referencia_accepts_day_first_format():
    from docx import Document

    document = Document()
    document.add_paragraph("Fecha de corte: 30 de Septiembre de 2026")
    buffer = BytesIO()
    document.save(buffer)
    assert extract_corte_referencia(buffer.getvalue()) == "2026-09-30"


def test_parse_informe_referencia_without_reference_table_returns_empty():
    assert parse_informe_referencia(docx_bytes("Solo texto, sin tabla")) == []


# ---------------------------------------------------------------------------
# 5. Parsers previos (DF-14A, actas Word, utilidades genericas)
# ---------------------------------------------------------------------------
SAMPLE_DF14A_XML = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Worksheet ss:Name="Hoja1">
    <Table>
      <Row><Cell><Data ss:Type="String">DF-14A_</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">MATRICULADOS_RESUMEN_POR_FICHA</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">23-09-2026</Data></Cell></Row>
      <Row>
        <Cell><Data ss:Type="String">CODIGO_REGIONAL</Data></Cell>
        <Cell><Data ss:Type="String">PROGRAMA</Data></Cell>
        <Cell><Data ss:Type="String">FICHA</Data></Cell>
        <Cell><Data ss:Type="String">POR_CERTIFICAR</Data></Cell>
        <Cell><Data ss:Type="String">CERTIFICADO</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">13</Data></Cell>
        <Cell><Data ss:Type="String">ADSI</Data></Cell>
        <Cell><Data ss:Type="String">2558701</Data></Cell>
        <Cell><Data ss:Type="String">3</Data></Cell>
        <Cell><Data ss:Type="String">12</Data></Cell>
      </Row>
    </Table>
  </Worksheet>
</Workbook>"""


def test_parse_df14a_xml_extracts_header_and_data_rows():
    frame = parse_df14a_xml(SAMPLE_DF14A_XML.encode("utf-8"))

    assert list(frame.columns) == ["CODIGO_REGIONAL", "PROGRAMA", "FICHA", "POR_CERTIFICAR", "CERTIFICADO"]
    assert len(frame) == 1
    assert frame.iloc[0]["FICHA"] == "2558701"
    assert frame.iloc[0]["POR_CERTIFICAR"] == "3"


def test_parse_df14a_xml_returns_empty_for_invalid():
    frame = parse_df14a_xml(b"<not><valid/></not>")
    assert frame.empty


def test_parse_acta_docx_extracts_table_records():
    from docx import Document

    document = Document()
    document.add_paragraph("ACTA DE CERTIFICACIÓN No. 23")
    table = document.add_table(rows=3, cols=4)
    table.cell(0, 0).text = "No."
    table.cell(0, 1).text = "Documento"
    table.cell(0, 2).text = "Nombre"
    table.cell(0, 3).text = "Ficha"
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "1043000100"
    table.cell(1, 2).text = "LAURA SOFÍA PÉREZ"
    table.cell(1, 3).text = "2558701"
    table.cell(2, 0).text = "2"
    table.cell(2, 1).text = "1043000237"
    table.cell(2, 2).text = "CARLOS ANDRÉS RODRÍGUEZ"
    table.cell(2, 3).text = "2558702"
    buffer = BytesIO()
    document.save(buffer)
    result = parse_acta_docx(buffer.getvalue())

    assert result["tables_count"] == 1
    assert result["header"] == ["No.", "Documento", "Nombre", "Ficha"]
    assert len(result["records"]) == 2
    assert result["records"][0]["Documento"] == "1043000100"
    assert result["records"][0]["Ficha"] == "2558701"
    assert any("ACTA DE CERTIFICACIÓN" in p for p in result["paragraphs"])


def test_frame_to_records_strips_nan_values():
    frame = pd.DataFrame(
        [
            {"nombre": "Ana", "ficha": None, "estado": "Certificado"},
            {"nombre": None, "ficha": None, "estado": None},
        ]
    )
    records = frame_to_records(frame)

    assert len(records) == 1
    assert records[0] == {"nombre": "Ana", "estado": "Certificado"}


# ---------------------------------------------------------------------------
# 6. Validacion de columnas obligatorias
# ---------------------------------------------------------------------------
def test_normalize_column_name_handles_accents_and_case():
    assert normalize_column_name("NÚMERO DE DOCUMENTO") == "numero de documento"
    assert normalize_column_name("Ficha ") == "ficha"
    assert normalize_column_name("MES_DE_CERTIFICACIÓN") == "mes de certificacion"


def test_check_required_columns_detects_missing_and_extra():
    missing, extra = check_required_columns(
        "certificados",
        ["NÚMERO DE DOCUMENTO", "NOMBRE", "FICHA", "COLUMNA_EXTRA"],
    )
    assert missing == []
    assert "COLUMNA_EXTRA" in extra


def test_check_required_columns_reports_missing():
    missing, extra = check_required_columns(
        "certificados",
        ["NOMBRE", "FICHA"],
    )
    assert "NÚMERO DE DOCUMENTO" in missing


def test_certificados_sheet_without_required_columns_reports_them():
    # Escenario del spec: faltan columnas obligatorias -> se informan, no se ocultan.
    missing, _ = check_required_columns("certificados", ["NIVEL", "ESTADO"])
    assert set(missing) == {"NÚMERO DE DOCUMENTO", "NOMBRE", "FICHA"}


def test_clean_identification_and_actas_records_ignore_nat_and_deleted_rows():
    from app.services.parsers import clean_identification, _actas_records
    import numpy as np

    # 1. clean_identification debe devolver None para NaT, NaN, 'NaT', 'nan', etc.
    assert clean_identification(pd.NaT) is None
    assert clean_identification("NaT") is None
    assert clean_identification("nan") is None
    assert clean_identification(np.nan) is None
    assert clean_identification("1043966273.0") == "1043966273"

    # 2. DataFrame simulando filas reales seguidas de filas borradas con fechas (que generan NaT)
    data = {
        "NIVEL": ["Tecnólogo", None, None],
        "FICHA": [2999999.0, np.nan, np.nan],
        "PROGRAMA": ["ADSO", None, None],
        "NÚMERO DE DOCUMENTO": [100000001.0, np.nan, np.nan],
        "NOMBRE": ["Aprendiz uno", None, None],
        "FECHA TERMINACION": [pd.Timestamp("2025-01-10"), pd.NaT, pd.NaT],
    }
    df = pd.DataFrame(data)
    records = _actas_records(df)

    # Solo debe retornar 1 registro real, ignorando las filas que solo tienen NaT/NaN
    assert len(records) == 1
    assert records[0]["numero de documento"] == "100000001"
    assert records[0]["ficha"] == "2999999"

