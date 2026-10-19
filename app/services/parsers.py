"""
Lectura y normalizacion de los documentos fuente del proceso de certificacion.

Este modulo concentra la interpretacion de los archivos oficiales:

* ``ACTAS 2026.xlsx`` -> hojas CERTIFICADOS, PENDIENTES, COMPLEMENTARIA y META.
* ``Informe de Gestion Administrativa ... .docx`` -> tabla de referencia con las
  metas institucionales y su ejecucion.

Librerias utilizadas y su proposito:

* **pandas**: lee las hojas de Excel y las convierte en "DataFrames" (tablas en
  memoria). Se usa porque evita escribir a mano el recorrido de celdas y ya
  maneja tipos de dato, celdas vacias y encabezados.
* **xml.etree.ElementTree**: lee el XML SpreadsheetML del DF-14A. Es parte de la
  libreria estandar de Python, por lo que no agrega dependencias.
* **python-docx** (se importa como ``docx``): abre los documentos Word y expone
  sus parrafos y tablas. Solo se importa dentro de la funcion que lo usa para
  que el resto del modulo siga funcionando si la libreria no esta instalada.
* **unicodedata.normalize**: permite quitar tildes para comparar texto escrito de
  formas distintas ("TECNÓLOGO" vs "TECNOLOGO"). Sigue siendo texto del idioma,
  no se pierde informacion del dato original porque se guarda el valor crudo.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from unicodedata import normalize
from xml.etree import ElementTree as ET

import pandas as pd

SS = "{urn:schemas-microsoft-com:office:spreadsheet}"

# Hojas de datos operativos que el sistema reconoce dentro de ACTAS 2026.xlsx.
ACTAS_SHEETS = ("CERTIFICADOS", "PENDIENTES", "COMPLEMENTARIA")

# ---------------------------------------------------------------------------
# Normalizacion de texto (utilidades compartidas)
# ---------------------------------------------------------------------------


def normalize_text(value: Any) -> str:
    """
    Convierte cualquier valor en texto comparable.

    Recibe un valor de cualquier tipo (numero, fecha, ``None``) y devuelve una
    cadena sin tildes, en minusculas, sin espacios repetidos y sin espacios al
    inicio o al final. Se usa para comparar valores que en los documentos
    aparecen escritos de formas distintas.
    """
    if value is None:
        return ""
    text = str(value)
    ascii_text = normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.lower().replace("_", " ").split())


def clean_identification(value: Any) -> str | None:
    """
    Normaliza un numero de documento de identidad.

    Excel entrega las cedulas como numeros decimales (por ejemplo
    ``1043966273.0``). Si se usa ese texto tal cual, el mismo aprendiz obtenido
    de dos hojas distintas no coincidiria al comparar. Aqui se quitan el punto y
    los ceros decimales, y se descartan celdas vacias.

    Devuelve el documento limpio o ``None`` si la celda no tenia dato.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    # Numeros como 1.043966273e+09 o 1043966273.0 se reducen a su parte entera.
    try:
        if "." in text or "e" in text.lower():
            number = float(text)
            if number.is_integer():
                return str(int(number))
    except (TypeError, ValueError):
        pass
    return text


def clean_act_number(value: Any) -> str | None:
    """
    Normaliza el numero de acta.

    En el Excel las actas vienen como ``362025.0`` (que corresponde al acta 36 de
    2025). Se conserva el texto sin el decimal para poder contar actas distintas.
    """
    return clean_identification(value)


# ---------------------------------------------------------------------------
# Clasificacion por NIVEL de formacion
# ---------------------------------------------------------------------------

# Equivalencias entre las variantes de escritura del NIVEL que aparecen en los
# documentos y un unico valor canonico. La clave esta normalizada con
# ``normalize_text``.
NIVEL_ALIASES: dict[str, str] = {
    "tecnologo": "tecnologo",
    "tecnologos": "tecnologo",
    "tecnologa": "tecnologo",
    "tecnico": "tecnico",
    "tecnicos": "tecnico",
    "tecnica": "tecnico",
    "auxiliar": "auxiliar",
    "auxiliares": "auxiliar",
    "senatic": "senatic",
    "senatIC": "senatic",
    # El documento institucional escribe el nivel de las dos formas.
    "profundizacion tecnica": "profundizacion tecnica",
    "profundacion tecnica": "profundizacion tecnica",
    "media tecnica": "media tecnica",
    "operario": "operario",
    "operarios": "operario",
}

# Regla misional acordada con el Centro de Comercio y Servicios:
#   * Educacion Superior           -> Tecnologo
#   * Tecnica Laboral y Otros      -> Auxiliar, Profundizacion Tecnica, SENATIC, Tecnico
#   * Articulacion con la Media    -> Media Tecnica
# Cualquier otro nivel (por ejemplo OPERARIO) NO se asigna por defecto: queda
# como "sin clasificar" para que la persona responsable decida con evidencia.
NIVEL_A_CATEGORIA: dict[str, str] = {
    "tecnologo": "superior",
    "tecnico": "tecnica",
    "auxiliar": "tecnica",
    "senatic": "tecnica",
    "profundizacion tecnica": "tecnica",
    "media tecnica": "articulacion",
}


def normalize_nivel(value: Any) -> str | None:
    """
    Devuelve el NIVEL canonico (sin tildes, en minusculas) o ``None``.

    Parameters
    ----------
    value:
        Texto tal como aparece en la columna NIVEL del Excel.

    Returns
    -------
    str | None
        Uno de los valores de :data:`NIVEL_ALIASES` o ``None`` si la celda esta
        vacia o el valor no esta documentado.
    """
    key = normalize_text(value)
    if not key:
        return None
    return NIVEL_ALIASES.get(key)


def classify_nivel(value: Any) -> str | None:
    """
    Traduce el NIVEL de formacion a la categoria misional del indicador.

    Returns
    -------
    str | None
        ``"superior"``, ``"tecnica"`` o ``"articulacion"``. Devuelve ``None``
        cuando el nivel no permite clasificar con certeza; en ese caso el
        registro se reporta como "sin clasificar" y no se suma a ninguna
        categoria automaticamente.
    """
    canonico = normalize_nivel(value)
    if canonico is None:
        return None
    return NIVEL_A_CATEGORIA.get(canonico)


# ---------------------------------------------------------------------------
# Normalizacion de motivos de no certificacion
# ---------------------------------------------------------------------------


def split_motivos(value: Any) -> list[str]:
    """
    Separa la columna MOTIVO DE NO CERTIFICACION en causas individuales.

    Una misma persona puede tener varios motivos escritos en una sola celda,
    separados por comas (por ejemplo ``"APE, No anexa T&T"``). Cada motivo es una
    *incidencia* distinta, aunque siga siendo *una sola persona* pendiente.

    Devuelve una lista de motivos normalizados, sin elementos vacios ni
    repetidos dentro de la misma celda.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    texto = str(value)
    motivos: list[str] = []
    for parte in texto.split(","):
        limpio = normalize_text(parte).strip(" .;")
        if limpio and limpio not in motivos:
            motivos.append(limpio)
    return motivos


# ---------------------------------------------------------------------------
# Lectura de la hoja META
# ---------------------------------------------------------------------------

# Palabras clave para reconocer cada meta dentro de la hoja META. El orden
# importa: "articulacion" se evalua antes que "tecnico laboral" porque el rotulo
# de Articulacion menciona a "Tecnico laboral y otros" entre parentesis.
_META_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("articulacion con la media", "articulacion"),
    ("educacion superior", "superior"),
    ("total complementaria", "complementaria"),
    ("total titulada", "total_titulada"),
    ("total formacion profesional", "total_formacion_profesional"),
    ("campesena", "campesena"),
    ("fullpopular", "fullpopular"),
    ("full popular", "fullpopular"),
    ("tecnico laboral", "tecnica"),
)


def read_meta_sheet(content: bytes, sheet_name: str = "META") -> dict[str, Any]:
    """
    Lee la hoja META de ``ACTAS 2026.xlsx`` y devuelve las metas documentadas.

    La hoja META no tiene encabezados formales: la primera fila util contiene los
    rotulos y la siguiente los valores. Por eso se lee con ``header=None`` y se
    busca la fila de rotulos.

    Returns
    -------
    dict[str, Any]
        Diccionario con las claves de :data:`_META_KEYWORDS` (por ejemplo
        ``"superior": 943``) mas ``"fila_rotulos"`` y ``"columna"`` para poder
        rastrear de que celda salio cada cifra. Las metas no reconocidas no se
        incluyen: es preferible dejar un dato faltante que inventarlo.
    """
    raw = pd.read_excel(BytesIO(content), sheet_name=sheet_name, header=None)
    fila_rotulos = None
    for indice in range(min(10, len(raw.index))):
        fila = [normalize_text(v) for v in raw.iloc[indice].tolist()]
        if any("educacion superior" in celda for celda in fila):
            fila_rotulos = indice
            break
    if fila_rotulos is None:
        return {}

    resultado: dict[str, Any] = {"fila_rotulos": fila_rotulos + 1}
    fila_valores = raw.iloc[fila_rotulos + 1] if fila_rotulos + 1 < len(raw.index) else None
    for columna, rotulo in enumerate(raw.iloc[fila_rotulos].tolist()):
        texto = normalize_text(rotulo)
        if not texto:
            continue
        for palabra, clave in _META_KEYWORDS:
            if palabra in texto:
                valor = fila_valores.iloc[columna] if fila_valores is not None else None
                numero = _to_int(valor)
                if numero is not None and clave not in resultado:
                    resultado[clave] = numero
                    resultado[f"{clave}_celda"] = f"columna {columna + 1}"
                break
    return resultado


def _to_int(value: Any) -> int | None:
    """Convierte un valor de celda a entero, o ``None`` si no es numerico."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Lectura del informe institucional en Word
# ---------------------------------------------------------------------------

# Rotulos de la tabla de referencia del informe de gestion y su categoria.
_REFERENCIA_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("educacion superior", "superior"),
    ("articulacion con la media", "articulacion"),
    ("total, tecnico laboral", "total_tecnica_laboral"),
    ("total tecnico laboral", "total_tecnica_laboral"),
    ("campesena", "campesena"),
    ("full popular", "fullpopular"),
    ("fullpopular", "fullpopular"),
    ("total, formacion titulada", "total_formacion_titulada"),
    ("total formacion titulada", "total_formacion_titulada"),
    ("complementaria presencial", "complementaria_presencial"),
    ("complementaria virtual", "complementaria_virtual"),
    ("total, fpi", "total_fpi"),
    ("total fpi", "total_fpi"),
    # El informe escribe el indicador como "Técnica Laboral y Otros" (femenino) y
    # la fila de total como "Total Técnico Laboral y Otros". Se aceptan las dos
    # formas de escritura porque el genero de la palabra cambia el texto.
    ("tecnica laboral", "tecnica"),
    ("tecnico laboral", "tecnica"),
)


def parse_informe_referencia(content: bytes) -> list[dict[str, Any]]:
    """
    Extrae la tabla de referencia de indicadores del informe de gestion (Word).

    Parameters
    ----------
    content:
        Bytes del archivo ``.docx``.

    Returns
    -------
    list[dict[str, Any]]
        Un diccionario por fila de la tabla, con el indicador, la meta anual, la
        ejecucion reportada, los pendientes, el avance y la ubicacion exacta
        (tabla y fila) de donde salio el dato. Las filas que no tienen indicador
        o meta se descartan y se informan aparte como advertencia.

    Notas de interpretacion
    ----------------------
    * El informe es un documento de corte: sus cifras de ejecucion corresponden
      a la fecha de corte que declara el propio texto, no al periodo completo
      que analiza la aplicacion. Por eso la aplicacion usa esta tabla
      unicamente como **referencia institucional** (metas y avance reportado).
    * No se completa ningun valor faltante: si el documento no trae una meta, el
      campo queda en ``None``.
    """
    from docx import Document

    document = Document(BytesIO(content))
    nombres_tablas: list[list[list[str]]] = [
        [[celda.text.strip() for celda in fila.cells] for fila in tabla.rows]
        for tabla in document.tables
    ]

    registros: list[dict[str, Any]] = []
    for indice_tabla, tabla in enumerate(nombres_tablas):
        encabezado_idx = _find_reference_header(tabla)
        if encabezado_idx is None:
            continue
        encabezado = tabla[encabezado_idx]
        for indice_fila, fila in enumerate(tabla[encabezado_idx + 1 :], start=encabezado_idx + 2):
            indicador = fila[0].strip() if fila else ""
            if not indicador:
                continue
            valores = {
                "meta": _to_int(_cell(fila, 1)),
                "ejecucion": _to_int(_cell(fila, 2)),
                "pendientes_por_cumplir": _to_int(_cell(fila, 3)),
                "avance_reportado": _to_int(_cell(fila, 4)),
            }
            clave = _match_referencia(indicador)
            registros.append(
                {
                    "tipo": "referencia_institucional",
                    "indicador": indicador,
                    "categoria": clave,
                    **valores,
                    "tabla": indice_tabla + 1,
                    "fila": indice_fila,
                    "fuente": "tabla_referencia_informe_gestion",
                }
            )
    return registros


def _find_reference_header(tabla: list[list[str]]) -> int | None:
    """Ubica la fila de encabezado de la tabla de referencia (INDICADOR / META ANUAL)."""
    for indice, fila in enumerate(tabla[:10]):
        celdas = [normalize_text(c) for c in fila]
        if any("indicador" == c for c in celdas) and any("meta anual" in c for c in celdas):
            return indice
    return None


def _cell(fila: list[str], posicion: int) -> str | None:
    """Devuelve el texto de una celda de la fila o ``None`` si no existe."""
    if posicion < len(fila):
        texto = fila[posicion].strip()
        if texto:
            return texto
    return None


def _match_referencia(indicador: str) -> str | None:
    """Asocia el nombre del indicador del informe con la clave interna de categoria."""
    texto = normalize_text(indicador)
    for palabra, clave in _REFERENCIA_KEYWORDS:
        if palabra in texto:
            return clave
    return None


def extract_corte_referencia(content: bytes) -> str | None:
    """
    Busca en los parrafos del informe la fecha de corte declarada.

    Devuelve la fecha en formato ``YYYY-MM-DD`` o ``None`` si el documento no la
    declara. Se lee del texto (por ejemplo "Junio 30 de 2026") para no fijar la
    fecha en el codigo.
    """
    import re

    from docx import Document

    document = Document(BytesIO(content))
    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11,
        "diciembre": 12,
    }
    letra = r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]+"
    # El informe real escribe la fecha como "Junio 30 de 2026" (mes primero), pero
    # tambien se admite la forma habitual "30 de junio de 2026". Cada patron indica
    # el orden de sus grupos para poder leer dia y mes en ambos casos.
    patrones = (
        (re.compile(rf"(\d{{1,2}})\s+de\s+({letra})\s+de\s+(\d{{4}})"), "dia_mes"),
        (re.compile(rf"({letra})\s+(\d{{1,2}})\s+de\s+(\d{{4}})"), "mes_dia"),
    )
    for parrafo in document.paragraphs:
        for patron, orden in patrones:
            coincidencia = patron.search(parrafo.text)
            if not coincidencia:
                continue
            if orden == "dia_mes":
                dia, mes_texto, anio = coincidencia.groups()
            else:
                mes_texto, dia, anio = coincidencia.groups()
            mes = meses.get(normalize_text(mes_texto))
            if mes:
                return f"{int(anio):04d}-{mes:02d}-{int(dia):02d}"
    return None


# ---------------------------------------------------------------------------
# Lectura de las hojas operativas de ACTAS 2026.xlsx
# ---------------------------------------------------------------------------

# Nombres de columna que se buscan dentro de cada hoja. Se comparan con
# ``normalize_text`` para no depender de tildes, mayusculas ni espacios finales.
_CAMPOS_ACTAS: dict[str, tuple[str, ...]] = {
    "nivel": ("nivel",),
    "numero de documento": ("numero de documento", "documento"),
    "nombre": ("nombre", "nombres"),
    "apellidos": ("apellidos",),
    "programa": ("programa",),
    "ficha": ("ficha",),
    "acta": ("acta", "numero de acta"),
    "estado": ("estado",),
    "mes de certificacion": ("mes de certificacion",),
    "motivo de no certificacion": ("motivo de no certificacion", "motivo"),
    "fecha de evaluacion": ("fecha de evaluacion",),
    "correo": ("correo",),
}


def _indexar_columnas(frame: pd.DataFrame) -> dict[str, str]:
    """Devuelve un mapa ``campo interno -> nombre real de columna`` del DataFrame."""
    indice: dict[str, str] = {}
    for columna in frame.columns:
        normalizada = normalize_text(columna)
        for campo, candidatos in _CAMPOS_ACTAS.items():
            if campo in indice:
                continue
            if normalizada in candidatos:
                indice[campo] = columna
    return indice


def _actas_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convierte una hoja de ACTAS 2026.xlsx en registros con nombres de campo fijos.

    Se usan nombres fijos (en minusculas y sin tildes) para que el resto del
    sistema no dependa de los encabezados exactos del Excel. Las filas
    completamente vacias se descartan para no inventar aprendices.
    """
    indice = _indexar_columnas(frame)
    registros: list[dict[str, Any]] = []
    for _, fila in frame.iterrows():
        registro: dict[str, Any] = {}
        for campo, columna in indice.items():
            valor = fila[columna]
            if campo in {"numero de documento", "acta"}:
                registro[campo] = clean_identification(valor)
            elif campo == "ficha":
                registro[campo] = clean_identification(valor)
            else:
                registro[campo] = None if _es_vacio(valor) else str(valor).strip()
        if any(valor is not None for valor in registro.values()):
            registros.append(registro)
    return registros


def _es_vacio(value: Any) -> bool:
    """Indica si un valor de celda debe considerarse vacio."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def read_certificados_records(content: bytes) -> list[dict[str, Any]]:
    """Lee la hoja CERTIFICADOS y devuelve un registro por fila con datos."""
    return _actas_records(pd.read_excel(BytesIO(content), sheet_name="CERTIFICADOS"))


def read_pendientes_records(content: bytes) -> list[dict[str, Any]]:
    """Lee la hoja PENDIENTES y devuelve un registro por fila con datos."""
    return _actas_records(pd.read_excel(BytesIO(content), sheet_name="PENDIENTES"))


def read_actas_csv_records(content: bytes) -> list[dict[str, Any]]:
    """
    Lee un CSV con la misma estructura de las hojas de personas de ACTAS 2026.xlsx.

    Los CSV del SENA suelen venir en codificacion ``cp1252`` (por eso el archivo
    trae "NÚMERO DE DOCUMENTO" con la letra Ñ/Ú). Se reutiliza el mismo
    normalizador ``_actas_records`` que usan las hojas de Excel para que los
    registros queden con los nombres de campo internos ("numero de documento",
    "estado", ...). Si no se normalizaran, el calculo de indicadores no
    encontraria las columnas y contaria 0 aprendices: un cero falso.
    """
    from app.services.validation import _read_csv

    return _actas_records(_read_csv(content))


def read_complementaria_records(content: bytes, sheet_name: str = "COMPLEMENTARIA") -> list[dict[str, Any]]:
    """
    Lee la hoja COMPLEMENTARIA.

    Esta hoja no lista aprendices: es un registro operativo donde cada fila
    informa una fecha y cuantos certificados se expidieron en un canal
    (presencial, virtual, campesena o full popular). Por eso el resultado no son
    personas, sino *conteos agregados* que deben tratarse aparte de los
    certificados individuales.

    Returns
    -------
    list[dict[str, Any]]
        Registros ``{"canal", "fecha", "cantidad", "fila"}``.
    """
    raw = pd.read_excel(BytesIO(content), sheet_name=sheet_name, header=None)
    # Cada canal ocupa una pareja de columnas: fecha y cantidad.
    canales = ((0, 1, "presencial"), (3, 4, "virtual"), (7, 8, "campesena"), (10, 11, "fullpopular"))
    registros: list[dict[str, Any]] = []
    for indice in range(len(raw.index)):
        for col_fecha, col_cantidad, canal in canales:
            if col_cantidad >= raw.shape[1]:
                continue
            fecha = raw.iat[indice, col_fecha]
            cantidad = _to_int(raw.iat[indice, col_cantidad])
            if cantidad is None:
                continue
            fecha_texto = _to_iso_date(fecha)
            registros.append(
                {
                    "canal": canal,
                    "fecha": fecha_texto,
                    "cantidad": cantidad,
                    "fila": indice + 1,
                }
            )
    return registros


def _to_iso_date(value: Any) -> str | None:
    """
    Convierte una fecha de Excel a ``YYYY-MM-DD``.

    En la hoja COMPLEMENTARIA conviven fechas reales (``datetime``) y textos como
    ``"26/02/2026"``. Se interpretan con formato dia/mes/anio, que es el usado en
    Colombia. Si no se puede interpretar, se devuelve ``None`` en lugar de
    asumir una fecha.
    """
    if value is None or _es_vacio(value):
        return None
    texto = str(value).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    marca = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if marca is None or pd.isna(marca):
        return None
    return marca.date().isoformat()


# ---------------------------------------------------------------------------
# Parsers previos (DF-14A, actas Word y utilidades genericas)
# ---------------------------------------------------------------------------


def parse_df14a_xml(content: bytes) -> pd.DataFrame:
    root = ET.fromstring(content)
    worksheet = None
    for ws in root.iter(SS + "Worksheet"):
        name = ws.get(SS + "Name", "")
        if name and name != "Hoja2" and name != "Hoja3":
            worksheet = ws
            break
    if worksheet is None:
        worksheet = root.find(f".//{SS}Worksheet")
    if worksheet is None:
        return pd.DataFrame()

    table = worksheet.find(SS + "Table")
    if table is None:
        return pd.DataFrame()

    rows = table.findall(SS + "Row")
    if not rows:
        return pd.DataFrame()

    header_idx = _find_header_row(rows)
    headers = _row_values(rows[header_idx]) if header_idx is not None else []
    if not headers:
        return pd.DataFrame()

    data_rows = rows[header_idx + 1 :] if header_idx is not None else rows
    records: list[dict[str, Any]] = []
    for row in data_rows:
        values = _row_values(row)
        if not values or all(v is None or str(v).strip() == "" for v in values):
            continue
        record = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
        records.append(record)
    return pd.DataFrame(records)


def _find_header_row(rows: list[ET.Element]) -> int | None:
    for idx, row in enumerate(rows[:15]):
        values = _row_values(row)
        text_values = {str(v).strip().upper() for v in values if v is not None}
        if "FICHA" in text_values:
            return idx
    return None


def _row_values(row: ET.Element) -> list[Any]:
    values: list[Any] = []
    last_index = 0
    for cell in row.findall(SS + "Cell"):
        index_attr = cell.get(SS + "Index")
        if index_attr and index_attr.isdigit():
            target = int(index_attr) - 1
            while last_index < target:
                values.append(None)
                last_index += 1
        data = cell.find(SS + "Data")
        values.append(data.text if data is not None else None)
        last_index += 1
    return values


def list_excel_sheets(content: bytes) -> list[str]:
    try:
        return pd.ExcelFile(BytesIO(content)).sheet_names
    except Exception:
        return []


def read_actas_sheet(content: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(content), sheet_name=sheet_name)


def read_requisitos(content: bytes) -> pd.DataFrame:
    return pd.read_excel(BytesIO(content))


def parse_acta_docx(content: bytes) -> dict[str, Any]:
    from docx import Document

    document = Document(BytesIO(content))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    table_rows: list[list[str]] = []
    for table in document.tables:
        for row in table.rows:
            table_rows.append([cell.text.strip() for cell in row.cells])

    header = table_rows[0] if table_rows else []
    records: list[dict[str, str]] = []
    for row in table_rows[1:]:
        if not any(row):
            continue
        record = {header[i]: row[i] for i in range(min(len(header), len(row)))}
        records.append(record)

    return {
        "paragraphs": paragraphs,
        "header": header,
        "records": records,
        "tables_count": len(document.tables),
    }


def frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.where(pd.notna(frame), None)
    return [
        {str(key): value for key, value in row.items() if value is not None}
        for row in clean.to_dict(orient="records")
        if any(value is not None for value in row.values())
    ]


def read_actas_full(content: bytes) -> list[dict[str, Any]]:
    """
    Lee todas las hojas reconocidas de ``ACTAS 2026.xlsx`` en una sola pasada.

    Devuelve una lista combinada de registros, donde cada uno tiene la clave
    interna ``"__type__"`` para que el importador sepa a que categoria
    (certificados, pendientes, meta, etc.) pertenece cada dato.
    """
    sheets = list_excel_sheets(content)
    sheet_map = {s.strip().upper(): s for s in sheets}
    resultado: list[dict[str, Any]] = []

    if "CERTIFICADOS" in sheet_map:
        for r in _actas_records(pd.read_excel(BytesIO(content), sheet_name=sheet_map["CERTIFICADOS"])):
            r["__type__"] = "certificados"
            resultado.append(r)

    if "PENDIENTES" in sheet_map:
        for r in _actas_records(pd.read_excel(BytesIO(content), sheet_name=sheet_map["PENDIENTES"])):
            r["__type__"] = "pendientes"
            resultado.append(r)

    if "COMPLEMENTARIA" in sheet_map:
        for r in read_complementaria_records(content, sheet_name=sheet_map["COMPLEMENTARIA"]):
            r["__type__"] = "complementaria"
            resultado.append(r)

    if "META" in sheet_map:
        metas = read_meta_sheet(content, sheet_name=sheet_map["META"])
        if metas:
            metas["__type__"] = "meta"
            resultado.append(metas)

    return resultado
