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

import re
from datetime import date
from io import BytesIO
from pathlib import Path
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
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    # En PDFs, una misma celda puede partir el numero en varias lineas
    # ("10474177\n32"). Si al quitar los espacios queda un numero puro, se usa
    # esa forma para que coincida con la identificacion de las otras fuentes.
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d{5,15}", compact):
        return compact
    # Documentos escritos con separador de miles ("1.043.000.100") se reducen a
    # digitos para que coincidan con la identificacion de las otras fuentes.
    # Solo se aplica cuando hay al menos dos grupos de miles o cinco digitos en
    # total, para no confundir un decimal corto (por ejemplo "1.234").
    thousands = re.fullmatch(r"(\d{1,3})((?:[.\s]\d{3})+)", compact)
    if thousands:
        digits = re.sub(r"[.\s]", "", compact)
        if len(digits) >= 5:
            return digits
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


def heal_fragmented_text(text: str, is_name: bool = False) -> str:
    """
    Intenta corregir texto fragmentado por el extractor de PDF.

    Une fragmentos de palabras que quedaron separados por espacios (ej.
    "OPERACION ES" -> "OPERACIONES", "DOCUMENT AL" -> "DOCUMENTAL"). No une
    conectores comunes del español como "de", "la", "y".
    """
    if not text:
        return text

    # Limpieza inicial de ruidos comunes en PDF (puntos y espacios flotantes al inicio/fin)
    text = re.sub(r"\s+\.", ".", text)
    text = re.sub(r"^[.\s]+", "", text)
    text = re.sub(r"[.\s]+$", "", text)

    words = text.split()
    if not words:
        return text

    # Conectores y palabras cortas que NO deben unirse al anterior
    connectors = {
        "de", "del", "la", "las", "los", "el", "y", "e", "en", "para",
        "con", "por", "si", "no", "su", "sus", "sin", "sobre"
    }
    # Sufijos y fragmentos terminales comunes en cortes de linea de PDF
    suffixes = {
        "es", "al", "iva", "ica", "as", "tiva", "ora", "dor", "cion",
        "ion", "os", "ez", "za", "erly", "na", "ria", "rio", "ico",
        "ero", "era", "ment", "ante", "ente", "ista", "ismo",
        # Sufijos adicionales frecuentes en programas y nombres
        "zacion", "zaciones", "nal", "nales", "ro", "ra", "rro", "rra",
        "ros", "ras", "rros", "rras", "miento", "mientos", "ciones",
        "sion", "siones", "tivo", "tivos", "tivas", "dora", "dores",
        "doras", "dad", "dades", "icos", "icas", "logia", "logico",
        "logica", "logicos", "logicas",
        # Cortes a mitad de raiz frecuentes
        "nes", "ales", "on", "acion", "aciones", "dez", "tez",
        "ble", "bles", "encia", "encias", "ancia", "ancias",
        "tor", "tores", "tora", "toras", "tura", "turas",
        "lez", "rez", "quez", "chez", "pez", "gues", "guez",
    }

    healed = [words[0]]
    for i in range(1, len(words)):
        word = words[i]
        prev = healed[-1]
        lower_word = word.lower().strip(".,")

        should_join = False
        if lower_word in connectors:
            should_join = False
        # Manejo de 'a', 'o', 'u' (vocales que pueden ser conector en frases pero fragmento en nombres o al final)
        elif lower_word in {"a", "o", "u"}:
            prev_lower = prev.lower()
            last_char = prev_lower[-1]
            # Si la palabra previa ya termina en vocal (a, e, o, u) o es un descriptor
            # clasificador como "programa", "nivel", "grupo", "curso", "fase":
            # "Programa A", "Nivel A", "Grupo A", "Curso A", "Fase A", etc. NO deben unirse.
            if last_char in {"a", "e", "o", "u"} or prev_lower in {
                "programa", "nivel", "grupo", "curso", "fase", "modulo",
                "bloque", "categoria", "tipo", "clase", "grado", "seccion"
            }:
                should_join = False
            elif is_name:
                # En nombres de personas, las consonantes finales seguidas de 'a' u 'o'
                # corresponden a fragmentos (ej. "ESPINOS A", "CARCAM O", "ALEJANDR A", "FERNAND A").
                should_join = True
            elif i == len(words) - 1:
                # En programas al final: si termina en 'i' (tecnologi a) o consonante truncada
                # (logistic a, administrac a, espinos a), se une.
                if last_char == "i" and len(prev_lower) >= 4:
                    should_join = True
                elif prev_lower.endswith((
                    "ndr", "nd", "str", "ntr", "mbr", "rbr", "ldr", "ncl", "mpl",
                    "rcam", "sayonar", "brocher", "espinos"
                )):
                    should_join = True
                elif len(prev_lower) >= 4 and last_char in {"m", "b", "c", "p", "t", "v", "s", "r"}:
                    should_join = True
                else:
                    should_join = False
            else:
                # En posición intermedia de programas
                if last_char == "i" and len(prev_lower) >= 4:
                    should_join = True
                elif prev_lower.endswith((
                    "ndr", "nd", "str", "ntr", "mbr", "rbr", "ldr", "ncl", "mpl",
                    "rcam", "sayonar", "brocher", "espinos"
                )):
                    should_join = True
                elif len(prev_lower) >= 4 and last_char in {"m", "b", "c", "p", "t", "v"}:
                    should_join = True
                else:
                    should_join = False
        # Heuristica: unir si es una sola letra (ej. "INTEGRACIO N", "HOTELERO S")
        elif len(lower_word) == 1 and lower_word.isalpha():
            should_join = True
        # Heuristica: unir si es un sufijo conocido fragmentado
        elif lower_word in suffixes:
            # Excepcion para 'al': solo unir si parece fragmento
            if lower_word == "al":
                # Si es la ultima palabra, probablemente es fragmento (Document Al)
                if i == len(words) - 1:
                    should_join = True
                else:
                    # Si la siguiente palabra es un conector, tambien es probable fragmento
                    # (Gestion Document Al . y Administrativa)
                    next_word = words[i+1].lower().strip(".,")
                    if next_word in connectors:
                        should_join = True
                    else:
                        should_join = False
            else:
                should_join = True
        # Heuristica adicional: si la palabra previa es larga y no termina en vocal,
        # 'n' o 's', y la actual es muy corta (2-3 letras) y no es conector.
        elif len(prev) >= 4 and len(lower_word) <= 3 and lower_word not in connectors:
            last_char = prev[-1].lower()
            if last_char not in {"a", "e", "i", "o", "u", "n", "s", "r", "l", "d", "z"}:
                should_join = True

        if should_join:
            healed[-1] = prev + word.strip(".,")
        else:
            healed.append(word)

    return " ".join(healed).strip(" .")


def normalize_program_name(value: Any) -> str | None:
    """
    Devuelve el nombre del programa en una sola linea legible.

    Los PDF y algunas celdas de Excel entregan el programa partido por saltos de
    linea ("OPERACIONES\\nCOMERCIALES") o con espacios repetidos. Aqui esos
    saltos y espacios se reemplazan por un unico espacio, se recorta el texto y
    se intenta sanar fragmentaciones de palabras.

    Solo se unifica el espaciado del texto tal como viene en la fuente: no se
    corrigen palabras ni se inventan nombres de programa que no existan en el
    documento. Devuelve ``None`` si no hay un valor util.
    """
    if value is None:
        return None
    text = str(value)
    if text.strip().lower() in {"nan", "nat", "none"}:
        return None
    # Colapsar espacios y sanar fragmentos
    clean = " ".join(text.split()).strip(" .")
    res = heal_fragmented_text(clean, is_name=False)
    return res.strip(" .") if res else None


def normalize_learner_name(value: Any) -> str | None:
    """
    Normaliza el nombre del aprendiz sanando posibles fragmentaciones.
    """
    if value is None:
        return None
    text = str(value)
    if text.strip().lower() in {"nan", "nat", "none"}:
        return None
    # Colapsar espacios y sanar fragmentos
    clean = " ".join(text.split()).strip(" .")
    res = heal_fragmented_text(clean, is_name=True)
    return res.strip(" .") if res else None


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
    # OPERARIO se clasifica igual que AUXILIAR (regla de negocio #33).
    "operario": "auxiliar",
    "operarios": "auxiliar",
}

# Regla misional acordada con el Centro de Comercio y Servicios:
#   * Educacion Superior           -> Tecnologo
#   * Tecnica Laboral y Otros      -> Auxiliar, Profundizacion Tecnica, SENATIC, Tecnico
#   * Articulacion con la Media    -> Media Tecnica
# OPERARIO se trata como AUXILIAR (regla de negocio #33).
# Cualquier otro nivel no documentado (por ejemplo NIVEL_DESCONOCIDO) NO se
# asigna por defecto: queda como "sin clasificar" para que la persona
# responsable decida con evidencia.
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
#
# Las claves de las columnas de evidencias coinciden con el ``requirement_type``
# que usa el importador (ver ``app.services.requirements``) para que cada celda
# leida se convierta directamente en un requisito del aprendiz. Los encabezados
# reales traen signos finales (":", ".") y saltos de linea internos, por eso cada
# campo lista sus variantes ya normalizadas.
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
    # Seguimiento de certificacion (datos de contacto del instructor).
    "instructor": ("instructor de seguimiento", "instructor"),
    "telefono": ("telefono", "celular"),
    # Checklist de evidencias / paz y salvos: cada columna es un requisito.
    "biblioteca": ("biblioteca",),
    "bienestar": ("bienestar del aprendiz",),
    "almacen": ("almacen",),
    "etapa_productiva": (
        "formato de evaluacion de la etapa productiva:",
        "formato de evaluacion de la etapa productiva",
    ),
    "documento_identidad": ("copia del documento de identidad vigente",),
    "saber_tyt": (
        "evidencia de la presentacion de las pruebas saber t y t. ( solo tgo)",
        "evidencia de la presentacion de las pruebas saber t y t",
    ),
    "ape": (
        "comprobante de inscripcion en la ape- agencia publica de empleo",
        "comprobante de inscripcion en la ape agencia publica de empleo",
    ),
    "carnet": (
        "comprobante de destruccion de carnet.",
        "comprobante de destruccion de carnet",
    ),
    "certificado_empresa": ("certificado de la empresa",),
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
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "nat", "none"}


def read_certificados_records(content: bytes) -> list[dict[str, Any]]:
    """Lee la hoja CERTIFICADOS y devuelve un registro por fila con datos."""
    return _actas_records(pd.read_excel(BytesIO(content), sheet_name="CERTIFICADOS"))


def read_pendientes_records(content: bytes) -> list[dict[str, Any]]:
    """Lee la hoja PENDIENTES y devuelve un registro por fila con datos."""
    return _actas_records(pd.read_excel(BytesIO(content), sheet_name="PENDIENTES"))


def read_csv_frame(content: bytes) -> pd.DataFrame:
    """Lee un CSV probando codificaciones habituales del SENA.

    Los archivos del SENA pueden venir en UTF-8 o en cp1252. Se intenta primero
    UTF-8 y, si falla, se prueban las codificaciones de Windows. Las lineas con
    problemas de formato se omiten solo cuando pandas no puede continuar; el
    objetivo es no detener toda la validacion por una fila mal escapada.
    """
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(BytesIO(content), encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
        except pd.errors.ParserError as error:
            try:
                return pd.read_csv(BytesIO(content), encoding=encoding, on_bad_lines="skip")
            except Exception as inner:
                last_error = inner
    if last_error is not None:
        raise last_error
    raise ValueError("No se pudo decodificar el archivo CSV.")


def normalize_column_name(value: str) -> str:
    """Normaliza un encabezado para compararlo sin tildes, mayusculas ni guiones."""
    ascii_value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("_", " ").replace("-", " ").split())


def detect_csv_certificacion_type(frame: pd.DataFrame) -> tuple[str, str]:
    """Distingue si un CSV alternativo contiene certificados o pendientes.

    La regla se apoya en el contenido declarado por el archivo (columna MOTIVO o
    ESTADO) y, solo si no hay evidencia, conserva ``certificados`` como valor
    explicito para que la validacion muestre las columnas faltantes. No inventa
    un estado ni modifica los datos.
    """
    col_names = [normalize_column_name(str(c)) for c in frame.columns]
    has_motivo = any("motivo" in c for c in col_names)
    has_mes = any("mes" in c for c in col_names)

    estado_col = next((c for c in frame.columns if normalize_column_name(str(c)) == "estado"), None)
    estados: set[str] = set()
    if estado_col is not None:
        estados = {normalize_text(v) for v in frame[estado_col].dropna().unique()}

    if has_motivo or any("pendiente" in e for e in estados):
        return "pendientes", "Listado de pendientes"
    if has_mes or any("certificado" in e for e in estados):
        return "certificados", "Listado de certificados"
    return "certificados", "Listado de certificados"


def read_actas_csv_records(content: bytes) -> list[dict[str, Any]]:
    """
    Lee un CSV con la misma estructura de las hojas de personas de ACTAS 2026.xlsx.

    Los CSV del SENA suelen venir en codificacion ``cp1252``. Se reutiliza el
    mismo normalizador ``_actas_records`` que usan las hojas de Excel para que
    los registros queden con los nombres de campo internos ("numero de
    documento", "estado", ...). Si no se normalizaran, el calculo de indicadores
    no encontraria las columnas y contaria 0 aprendices: un cero falso.
    """
    return _actas_records(read_csv_frame(content))


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


# ---------------------------------------------------------------------------
# Actas oficiales (PDF / DOCX): extraccion de datos del acta y de sus aprendices
# ---------------------------------------------------------------------------
#
# La extraccion es deliberadamente conservadora: solo devuelve los datos que se
# pueden leer con evidencia en el documento. Cuando un campo no se puede
# interpretar con fiabilidad se deja en ``None`` y se explica en ``warnings``;
# nunca se genera un numero de acta, una fecha, una identificacion ni un nombre.

_MESES_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# "ACTA DE CERTIFICACIÓN No. 23", "ACTA ORDINARIA N° 101-2026" o "ACTA 41".
_ACTA_NUMBER_RE = re.compile(
    r"\bACTA\b[^\n]{0,80}?\b(?:N(?:o|ro)?\.?\s*|[Nn][°º]\s*)"
    r"([0-9][0-9A-Za-z\-/]*)"
    r"|\bACTA\b(?:\s+(?:DE\s+)?(?:CERTIFICACI[OÓ]N|ORDINARIA|EXTRAORDINARIA))?\s+"
    r"([0-9][0-9A-Za-z\-/]*)",
    re.IGNORECASE,
)
_ACTA_ASUNTO_RE = re.compile(r"Asunto\s*:\s*(.+)", re.IGNORECASE)
_FECHA_TEXTO_RE = re.compile(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)\s+de\s+(\d{4})")
_FECHA_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# Numero de documento tal como suele aparecer en los documentos: digitos
# corridos ("1043000100") o con separador de miles ("1.043.000.100").
_DOCUMENTO_PATTERN = r"(?:[0-9]{1,3}(?:\.[0-9]{3}){1,4}|[0-9]{5,15})"

# Nombre de una persona: al menos dos palabras capitalizadas. Se admiten
# conectores en minuscula ("de", "del", "la", "los", "y") para nombres como
# "Laura de los Ángeles Pérez". Exigir dos palabras evita confundir frases del
# documento ("programa 2500001 para los aprendices") con un aprendiz.
_ACTA_NOMBRE_TOKEN = r"[A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’.\-]*"
_ACTA_NOMBRE_CONECTOR = r"(?:de|del|la|las|los|y|e)"
_ACTA_NOMBRE = (
    rf"{_ACTA_NOMBRE_TOKEN}"
    rf"(?:\s+(?:{_ACTA_NOMBRE_CONECTOR}\s+)*{_ACTA_NOMBRE_TOKEN})+"
)

# Aprendices listados en texto: "- C.C. 1001001001 - GOMEZ PEREZ LAURA SOFIA" o
# "1001001001 GOMEZ PEREZ LAURA SOFIA" (PDF sin separador explicito).
_ACTA_APRENDIZ_TEXTO_RE = re.compile(
    r"(?:[-•*]\s*)?(?:C\.?\s?C\.?|T\.?\s?I\.?|CC|TI|CE|PAS)?\s*:?\s*"
    rf"({_DOCUMENTO_PATTERN})\s*(?:[-–:]\s*|\s+)"
    rf"({_ACTA_NOMBRE})"
)

# Algunos documentos listan primero el nombre y despues el documento (por
# ejemplo cuando la columna DOCUMENTOS esta a la derecha del nombre).
_ACTA_APRENDIZ_NOMBRE_PRIMERO_RE = re.compile(
    rf"({_ACTA_NOMBRE})\s+({_DOCUMENTO_PATTERN})(?:\s|$)"
)

# Encabezados reconocidos en las tablas de un acta. Se comparan normalizados
# (sin tildes, minusculas y sin guiones) para tolerar variantes de redaccion.
_ACTA_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "documento": (
        "documento",
        "documentos",
        "no documento",
        "no. documento",
        "nro documento",
        "numero de documento",
        "numero documento",
        "numero de documentos",
        "documento de identidad",
        "documento del aprendiz",
        "documento aprendiz",
        "identificacion",
        "numero de identificacion",
        "identificacion del aprendiz",
        "cedula",
        "cedula de ciudadania",
        "c c",
        "cc",
        "t i",
        "ti",
    ),
    "nombre": (
        "nombre",
        "nombres",
        "nombre completo",
        "nombres completos",
        "nombre aprendiz",
        "nombres y apellidos",
        "apellidos y nombres",
        "aprendiz",
    ),
    "apellidos": ("apellidos", "apellido"),
    "ficha": ("ficha", "codigo ficha", "codigo de ficha", "grupo", "numero de ficha"),
    "programa": ("programa", "programa de formacion", "programa formacion"),
    "resultado": ("resultado", "estado", "condicion", "observaciones"),
}

# Encabezados que mencionan la palabra "documento" pero no contienen el numero
# de identificacion (por ejemplo "TIPO DE DOCUMENTO" con valores CC/TI).
_ACTA_HEADER_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "documento": ("tipo de documento", "tipo documento", "clase de documento"),
}


def extract_acta_number(text: str) -> str | None:
    """Devuelve el numero de acta legible en el texto, o ``None`` si no aparece."""
    match = _ACTA_NUMBER_RE.search(text or "")
    if not match:
        return None
    value = match.group(1) or match.group(2) or ""
    return value.strip().rstrip(".") or None


def parse_fecha_documento(text: str) -> str | None:
    """Convierte una fecha legible ("02 de octubre de 2026" o ISO) a ``YYYY-MM-DD``."""
    if not text:
        return None
    match = _FECHA_TEXTO_RE.search(text)
    if match:
        day, month_name, year = match.groups()
        month = _MESES_ES.get(normalize_text(month_name))
        if not month:
            return None
        try:
            return date(int(year), month, int(day)).isoformat()
        except ValueError:
            return None
    match = _FECHA_ISO_RE.search(text)
    if match:
        try:
            return date(*(int(part) for part in match.groups())).isoformat()
        except ValueError:
            return None
    return None


def _compact_header(value: str) -> str:
    """Version sin espacios del encabezado.

    En PDFs las columnas suelen ser angostas y el encabezado se parte en varias
    lineas ("DOCUM\\nENTO", "FICH\\nA"). Al quitar los espacios se recupera la
    palabra completa para compararla con los alias conocidos.
    """
    return re.sub(r"\s+", "", normalize_column_name("" if value is None else str(value)))


def _map_acta_header(header: list[str]) -> dict[str, int]:
    """Asocia cada campo del acta con la columna de la tabla que lo contiene."""
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for index, cell in enumerate(header):
        normalized = normalize_column_name("" if cell is None else str(cell))
        if not normalized:
            continue
        compact = _compact_header(cell)
        for field_name, aliases in _ACTA_HEADER_ALIASES.items():
            if field_name in mapping:
                continue
            exclusions = _ACTA_HEADER_EXCLUSIONS.get(field_name, ())
            if any(
                exclusion in normalized or _compact_header(exclusion) == compact
                for exclusion in exclusions
            ):
                continue
            if any(
                alias == normalized
                or (len(alias) > 3 and alias in normalized)
                or _compact_header(alias) == compact
                for alias in aliases
            ):
                # Una misma columna no puede ser a la vez nombre y apellidos.
                if index in used and field_name != "nombre":
                    continue
                mapping[field_name] = index
                used.add(index)
                break
    return mapping


def _find_acta_header(
    rows: list[list[str]], max_rows: int = 30
) -> tuple[int, dict[str, int]] | None:
    """Ubica la fila de encabezado de la tabla de aprendices.

    Muchos documentos oficiales agregan filas de titulo antes del encabezado
    real (por ejemplo el nombre del centro, el asunto o el desarrollo del acta).
    Se revisan las primeras filas en lugar de asumir que la primera es el
    encabezado.
    """
    for index, row in enumerate(rows[:max_rows]):
        mapping = _map_acta_header(row)
        if {"documento", "nombre"} <= set(mapping):
            return index, mapping
    return None


def _learners_from_rows(
    rows: list[list[str]], mapping: dict[str, int]
) -> list[dict[str, str]]:
    """Extrae aprendices de las filas de datos usando un mapeo de columnas."""
    learners: list[dict[str, str]] = []
    for row in rows:
        if not any(str(cell).strip() for cell in row if cell is not None):
            continue
        learner: dict[str, str] = {}
        for field_name, index in mapping.items():
            if index < len(row):
                raw = "" if row[index] is None else str(row[index])
                # Colapsa saltos de linea y espacios repetidos dentro de la celda.
                value = " ".join(raw.split())
                if value:
                    learner[field_name] = value
        document = clean_identification(learner.get("documento"))
        name = normalize_learner_name(learner.get("nombre"))
        if not document or not name:
            # Sin identificacion o sin nombre no se puede asociar a una persona
            # con certeza; se omite en lugar de inventar una relacion.
            continue
        learner["documento"] = document
        if learner.get("ficha"):
            ficha = clean_identification(learner["ficha"])
            if ficha:
                learner["ficha"] = ficha
        # Si nombre y apellidos vienen en columnas separadas se conserva el
        # nombre completo en el orden en que aparecen en el documento.
        if learner.get("apellidos") and learner.get("nombre"):
            if mapping.get("apellidos", 0) < mapping.get("nombre", 0):
                full_raw = f"{learner['apellidos']} {learner['nombre']}".strip()
            else:
                full_raw = f"{learner['nombre']} {learner['apellidos']}".strip()
            name = normalize_learner_name(full_raw) or name
        learner["nombre"] = name
        learner.pop("apellidos", None)
        learners.append(learner)
    return learners


def _extract_table_learners(
    rows: list[list[str]], mapping: dict[str, int] | None = None
) -> tuple[list[dict[str, str]], dict[str, int] | None]:
    """Extrae aprendices de una tabla y conserva el mapeo para tablas siguientes.

    Las tablas de un acta pueden continuar en otra pagina sin repetir el
    encabezado. En ese caso se reutiliza el ultimo mapeo reconocido.
    """
    found = _find_acta_header(rows)
    if found is not None:
        header_index, current = found
        return _learners_from_rows(rows[header_index + 1 :], current), current
    if mapping is not None:
        return _learners_from_rows(rows, mapping), mapping
    return [], mapping


def _learners_from_table(rows: list[list[str]]) -> list[dict[str, str]]:
    """Extrae aprendices de una tabla cuyo encabezado identifica documento y nombre."""
    if len(rows) < 2:
        return []
    learners, _ = _extract_table_learners(rows)
    return learners


def _select_table_learners(
    results: list[tuple[list[dict[str, str]], dict[str, int] | None]]
) -> list[dict[str, str]]:
    """Prefiere las tablas con columnas de contexto (ficha o programa).

    Un acta puede incluir una tabla de asistencia de coordinadores ademas de la
    tabla de aprendices. Si alguna tabla trae ficha o programa, se usan solo esas
    tablas para no asociar asistentes que no son aprendices. Cuando ninguna
    tabla trae esas columnas se conservan todas las que identifican documento y
    nombre, para no perder actas con una estructura minima.
    """
    rich = any(
        mapping is not None and ({"ficha", "programa"} & set(mapping))
        for _, mapping in results
    )
    selected: list[dict[str, str]] = []
    for table_learners, mapping in results:
        if rich and not (mapping is not None and ({"ficha", "programa"} & set(mapping))):
            continue
        selected.extend(table_learners)
    return selected


def _learners_from_text(text: str) -> list[dict[str, str]]:
    """Extrae aprendices de texto corrido (util en PDF sin tablas nativas)."""
    learners: list[dict[str, str]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _ACTA_APRENDIZ_TEXTO_RE.search(line)
        if match:
            document = clean_identification(match.group(1))
            name = normalize_learner_name(match.group(2).strip(" -–\t."))
            if document and name:
                learners.append({"documento": document, "nombre": name})
                continue
        # Si el documento aparece despues del nombre (columna DOCUMENTOS a la
        # derecha), se reconoce la pareja nombre + identificacion.
        match = _ACTA_APRENDIZ_NOMBRE_PRIMERO_RE.search(line)
        if not match:
            continue
        name = normalize_learner_name(match.group(1).strip(" -–\t.,"))
        document = clean_identification(match.group(2))
        if document and name:
            learners.append({"documento": document, "nombre": name})
    return learners


def _dedupe_learners(learners: list[dict[str, str]]) -> list[dict[str, str]]:
    """Evita repetir a la misma persona dentro del mismo documento."""
    result: list[dict[str, str]] = []
    seen: dict[str, dict[str, str]] = {}
    for learner in learners:
        document = learner.get("documento")
        if not document:
            continue
        current = seen.get(document)
        if current is None:
            seen[document] = learner
            result.append(learner)
            continue
        for key, value in learner.items():
            if value and not current.get(key):
                current[key] = value
    return result


def extract_acta_data(file_name: str, content: bytes) -> dict[str, Any]:
    """Lee un acta oficial (PDF o DOCX) y devuelve sus datos interpretables.

    Reutiliza ``python-docx`` para DOCX y PyMuPDF para PDF. En PDF se intentan
    primero las tablas nativas y, si no las hay, se leen las lineas de texto. El
    resultado incluye una lista de ``warnings`` con lo que no pudo extraerse.
    """
    extension = Path(file_name).suffix.lower()
    text_parts: list[str] = []
    learners: list[dict[str, str]] = []
    tables_count = 0
    paragraph_count = 0

    if extension == ".docx":
        from docx import Document

        document = Document(BytesIO(content))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        paragraph_count = len(paragraphs)
        text_parts.extend(paragraphs)
        tables_count = len(document.tables)
        mapping: dict[str, int] | None = None
        table_results: list[tuple[list[dict[str, str]], dict[str, int] | None]] = []
        for table in document.tables:
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            table_learners, mapping = _extract_table_learners(rows, mapping)
            table_results.append((table_learners, mapping))
        learners.extend(_select_table_learners(table_results))
        if not learners:
            learners.extend(_learners_from_text("\n".join(paragraphs)))
    elif extension == ".pdf":
        import fitz

        document = fitz.open(stream=content, filetype="pdf")
        try:
            if document.page_count == 0:
                raise ValueError("El PDF no contiene paginas.")
            mapping = None
            table_results = []
            for page in document:
                text_parts.append(page.get_text("text"))
                find_tables = getattr(page, "find_tables", None)
                if find_tables is None:
                    continue
                # Los PDF oficiales no siempre traen lineas dibujadas. Se intenta
                # primero la deteccion por lineas (mas fiable cuando existen) y
                # luego por posicion del texto. El mapeo de columnas se conserva
                # entre paginas porque la tabla puede continuar sin repetir el
                # encabezado.
                page_learners: list[dict[str, str]] = []
                for strategy in ("lines", "text"):
                    try:
                        tables = find_tables(strategy=strategy)
                    except Exception:
                        continue
                    tables_count += len(tables.tables)
                    for table in tables:
                        table_learners, mapping = _extract_table_learners(
                            table.extract(), mapping
                        )
                        page_learners.extend(table_learners)
                        table_results.append((table_learners, mapping))
                    if page_learners:
                        break
        finally:
            document.close()
        learners = _select_table_learners(table_results)
        if not learners:
            learners.extend(_learners_from_text("\n".join(text_parts)))
    else:
        raise ValueError("El acta debe estar en formato PDF o DOCX.")

    full_text = "\n".join(text_parts)
    number = extract_acta_number(full_text)
    act_date = parse_fecha_documento(full_text)
    asunto = _ACTA_ASUNTO_RE.search(full_text)
    act_type = asunto.group(1).strip() if asunto else None
    missing_documents = sum(1 for learner in learners if not learner.get("documento"))
    with_document = sum(1 for learner in learners if learner.get("documento"))
    learners = _dedupe_learners(learners)
    duplicate_learners = with_document - len(learners)
    # El programa se guarda en una sola linea: en los PDF la columna suele venir
    # partida por el ancho de la celda ("OPERACIONES\nCOMERCIALES").
    for learner in learners:
        name = normalize_learner_name(learner.get("nombre"))
        if name:
            learner["nombre"] = name
        program = normalize_program_name(learner.get("programa"))
        if program:
            learner["programa"] = program
        else:
            learner.pop("programa", None)

    warnings: list[str] = []
    if not full_text.strip():
        warnings.append(
            "El documento no contiene texto legible. Si es un PDF escaneado, "
            "requiere reconocimiento optico de caracteres (OCR) antes de importarlo."
        )
    if not number:
        warnings.append("No se pudo identificar el numero del acta en el documento.")
    if not act_date:
        warnings.append("No se pudo identificar la fecha del acta.")
    if missing_documents:
        warnings.append(
            f"{missing_documents} aprendiz(es) sin numero de documento confiable; "
            "no se asociaran al acta."
        )
    if duplicate_learners:
        warnings.append(
            f"{duplicate_learners} aprendiz(es) duplicado(s) en el documento; "
            "se conservo una sola asociacion por documento."
        )
    if not learners:
        if tables_count:
            warnings.append(
                "Se encontraron tablas en el acta, pero ninguna con encabezados "
                "reconocibles de documento y nombre. Verifique que la tabla de "
                "aprendices tenga esas columnas."
            )
        warnings.append("El acta no aporta aprendices con numero de documento.")

    return {
        "file_name": file_name,
        "format": extension.lstrip("."),
        "number": number,
        "act_date": act_date,
        "act_type": act_type,
        "learners": learners,
        "paragraph_count": paragraph_count,
        "tables_count": tables_count,
        "warnings": warnings,
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
