"""
Calculo de los indicadores de certificacion 2026 del Centro de Comercio y Servicios
(SENA Regional Bolivar).

Este modulo reemplaza las cifras que antes estaban escritas a mano en el codigo
(metas, certificados base, pendientes base y conteo de motivos). Ahora TODO se
obtiene de las fuentes documentales definidas para el proyecto:

* ``ACTAS 2026.xlsx`` -> hojas CERTIFICADOS, PENDIENTES, COMPLEMENTARIA y META.
* ``Informe de Gestion Administrativa ... .docx`` -> unicamente la tabla de
  referencia institucional (metas y avance reportado a la fecha de corte).

Como llegan los datos hasta aqui
-------------------------------
La aplicacion no lee los archivos directamente desde el disco: el usuario los
carga por la interfaz web, el sistema los valida y los guarda en SQLite
(tablas ``import_history`` e ``imported_records``). Cada fila de
``imported_records`` guarda su contenido como texto JSON. Este modulo vuelve a
convertir ese JSON en diccionarios y calcula los indicadores a partir de ellos.

Conceptos importantes para quien mantenga el codigo
---------------------------------------------------
* **Deduplicacion**: una misma persona puede aparecer en varias filas (o venir en
  dos archivos distintos). Se identifica por el numero de documento normalizado y
  se cuenta UNA sola vez.
* **Periodo**: 1 de enero al 30 de septiembre de 2026 (ambos incluidos). La hoja
  CERTIFICADOS guarda el mes como texto ("JUNIO"), no como fecha, asi que se
  compara contra la lista de meses permitidos.
* **Personas vs incidencias**: un aprendiz pendiente puede tener VARIOS motivos.
  Se cuentan por separado los aprendices y las incidencias.
* **Sin clasificar**: si el NIVEL de formacion no esta respaldado por una regla
  documentada (por ejemplo OPERARIO), el registro NO se asigna por defecto a
  ninguna categoria: se reporta aparte.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportedRecord
from app.services import parsers

# ---------------------------------------------------------------------------
# Constantes del periodo y de la clasificacion misional
# ---------------------------------------------------------------------------

PERIODO_INICIO = "2026-01-01"
PERIODO_FIN = "2026-09-30"
PERIODO_LABEL = "Enero - Septiembre 2026"

# Meses (en texto normalizado) que pertenecen al periodo solicitado. La hoja
# CERTIFICADOS escribe el mes con palabras; por eso no se puede comparar como
# fecha. OCTUBRE queda fuera a proposito.
MESES_DEL_PERIODO = {
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
}

# Categorias misionales que se reportan.
# Formato: (clave interna, etiqueta visible, nota sobre como NO sumarla dos veces).
CATEGORIAS: tuple[tuple[str, str, str | None], ...] = (
    ("superior", "Educación Superior (Tecnólogos)", None),
    ("tecnica", "Técnica Laboral y Otros (sin incluir Media Técnica)", None),
    (
        "articulacion",
        "Articulación con la Media",
        "Ya está incluida en 'Total, Técnico Laboral y Otros' "
        "(1910 + 1995 = 3905). No debe sumarse otra vez sobre esa categoría.",
    ),
    ("complementaria", "Formación Complementaria", None),
)

# Canales de la hoja COMPLEMENTARIA.
CANALES_COMPLEMENTARIA = ("presencial", "virtual", "campesena", "fullpopular")


# ---------------------------------------------------------------------------
# Lectura de los registros importados
# ---------------------------------------------------------------------------


def _cargar_registros(session: Session, information_type: str) -> list[dict[str, Any]]:
    """
    Recupera de SQLite los registros importados de un tipo de informacion.

    Parametros
    ----------
    session:
        Sesion activa de SQLAlchemy.
    information_type:
        Tipo interno del dato ("certificados", "pendientes", "meta", ...).

    Devuelve
    --------
    list[dict]
        Un diccionario por registro. Si un ``payload`` estuviera corrupto se
        omite (no se detiene el calculo por un solo registro malo).
    """
    filas = session.scalars(
        select(ImportedRecord)
        .where(ImportedRecord.information_type == information_type)
        .order_by(ImportedRecord.id.asc())
    ).all()
    registros: list[dict[str, Any]] = []
    for fila in filas:
        try:
            contenido = json.loads(fila.payload)
        except (TypeError, ValueError):
            continue
        if isinstance(contenido, dict):
            registros.append(contenido)
    return registros


def _metas_institucionales(session: Session) -> tuple[dict[str, int], str | None]:
    """
    Obtiene las metas anuales desde las fuentes documentales (nunca del codigo).

    Prioridad:
      1. Hoja META de ``ACTAS 2026.xlsx`` (fuente principal de metas).
      2. Tabla de referencia del informe de gestion en Word (respaldo documental).

    Devuelve ``(metas, fuente)``. ``metas`` usa claves internas
    ("superior", "tecnica", "articulacion", "complementaria"). Si no hay ninguna
    fuente disponible, devuelve ``({}, None)``: es preferible informar que falta
    la meta antes que inventarla.
    """
    for registro in _cargar_registros(session, "meta"):
        metas = {
            clave: valor
            for clave, valor in registro.items()
            if clave in {"superior", "tecnica", "articulacion", "complementaria"}
            and isinstance(valor, int)
        }
        if metas:
            return metas, "ACTAS 2026.xlsx (hoja META)"

    # Respaldo: la tabla de referencia del Word trae meta por indicador.
    metas: dict[str, int] = {}
    for fila in _cargar_registros(session, "informe"):
        clave = fila.get("categoria")
        meta = fila.get("meta")
        if not isinstance(meta, int):
            continue
        if clave in {"superior", "tecnica", "articulacion"} and clave not in metas:
            metas[clave] = meta
        elif clave == "complementaria_presencial" and "complementaria" not in metas:
            # El informe reporta la meta de complementaria en la fila presencial
            # (y repite el mismo valor en la virtual).
            metas["complementaria"] = meta
    if metas:
        return metas, "Informe de gestion (tabla de referencia)"
    return {}, None


def _resumen_hoja_actas(
    registros: list[dict[str, Any]],
    estado_valido: str,
    filtrar_por_mes: bool,
    leer_motivos: bool,
) -> dict[str, Any]:
    """
    Agrupa una hoja de personas (CERTIFICADOS o PENDIENTES) por categoria misional.

    Parametros
    ----------
    registros:
        Filas ya normalizadas por :mod:`app.services.parsers`.
    estado_valido:
        Valor de la columna ESTADO que si cuenta ("certificados" o "pendiente").
        Sirve para NO tratar todas las filas de la hoja como validas.
    filtrar_por_mes:
        ``True`` para CERTIFICADOS (solo meses del periodo). PENDIENTES es un
        censo de personas que siguen sin certificar, sin fecha de certificacion.
    leer_motivos:
        ``True`` solo para PENDIENTES: separa la columna MOTIVO DE NO
        CERTIFICACION en incidencias individuales.

    Devuelve
    --------
    dict
        * ``por_categoria``: documentos unicos por categoria misional.
        * ``sin_clasificar``: documentos cuyo NIVEL no tiene regla documentada.
        * ``niveles_sin_clasificar``: conteo de esos valores de NIVEL.
        * ``sin_documento`` / ``fuera_de_periodo``: filas descartadas y por que.
        * ``por_acta``: numero de acta -> aprendices (para el resumen de actas).
        * ``motivos``: incidencias por motivo (solo si ``leer_motivos``).
        * ``documentos_sin_motivo`` / ``documentos_con_varios_motivos``.
    """
    por_categoria: dict[str, set[str]] = {clave: set() for clave, _, _ in CATEGORIAS}
    sin_clasificar: set[str] = set()
    niveles_sin_clasificar: Counter = Counter()
    por_acta: Counter = Counter()
    motivos: Counter = Counter()

    sin_documento = 0
    fuera_de_periodo = 0
    documentos_sin_motivo = 0
    documentos_con_varios_motivos = 0
    vistos: set[str] = set()

    for registro in registros:
        # 1) Solo cuentan las filas con el estado esperado.
        if parsers.normalize_text(registro.get("estado")) != estado_valido:
            continue

        # 2) Filtro de periodo (solo aplica a certificados).
        if filtrar_por_mes:
            mes = parsers.normalize_text(registro.get("mes de certificacion"))
            if mes not in MESES_DEL_PERIODO:
                fuera_de_periodo += 1
                continue

        # 3) Sin documento no se puede deduplicar ni identificar a la persona.
        documento = parsers.clean_identification(registro.get("numero de documento"))
        if not documento:
            sin_documento += 1
            continue

        # 4) Deduplicacion: cada documento se procesa una sola vez.
        if documento in vistos:
            continue
        vistos.add(documento)

        # 5) Clasificacion misional segun el NIVEL de formacion.
        categoria = parsers.classify_nivel(registro.get("nivel"))
        if categoria is None:
            sin_clasificar.add(documento)
            nivel = parsers.normalize_text(registro.get("nivel")) or "(nivel vacio)"
            niveles_sin_clasificar[nivel] += 1
        else:
            por_categoria[categoria].add(documento)

        # 6) Conteo por acta (para saber cuantos aprendices trae cada acta).
        acta = parsers.clean_act_number(registro.get("acta"))
        if acta:
            por_acta[acta] += 1

        # 7) Motivos de no certificacion (una celda puede traer varios).
        if leer_motivos:
            lista_motivos = parsers.split_motivos(registro.get("motivo de no certificacion"))
            if not lista_motivos:
                documentos_sin_motivo += 1
            elif len(lista_motivos) > 1:
                documentos_con_varios_motivos += 1
            for motivo in lista_motivos:
                motivos[motivo] += 1

    return {
        "por_categoria": por_categoria,
        "sin_clasificar": sin_clasificar,
        "niveles_sin_clasificar": niveles_sin_clasificar,
        "sin_documento": sin_documento,
        "fuera_de_periodo": fuera_de_periodo,
        "por_acta": por_acta,
        "motivos": motivos,
        "documentos_sin_motivo": documentos_sin_motivo,
        "documentos_con_varios_motivos": documentos_con_varios_motivos,
        "total_documentos": len(vistos),
    }


def _resumen_complementaria(session: Session) -> dict[str, Any]:
    """
    Suma los certificados de formacion complementaria por canal dentro del periodo.

    La hoja COMPLEMENTARIA no lista personas: cada fila informa una fecha y
    cuantos certificados se expidieron en un canal (presencial, virtual,
    campesena o full popular). Por eso aqui se SUMAN cantidades y no se intenta
    deduplicar aprendices: la fuente no trae numero de documento.

    Las filas sin fecha no se pueden ubicar en el periodo y se informan aparte.
    """
    por_canal: dict[str, int] = {canal: 0 for canal in CANALES_COMPLEMENTARIA}
    por_canal["otro"] = 0
    total = 0
    sin_fecha = 0
    fuera_de_periodo = 0

    registros = _cargar_registros(session, "complementaria")
    for registro in registros:
        cantidad = registro.get("cantidad")
        if not isinstance(cantidad, int):
            continue
        fecha = registro.get("fecha")
        if not fecha:
            sin_fecha += 1
            continue
        if not (PERIODO_INICIO <= str(fecha) <= PERIODO_FIN):
            fuera_de_periodo += 1
            continue
        canal = registro.get("canal")
        por_canal[canal if canal in por_canal else "otro"] += cantidad
        total += cantidad

    return {
        "por_canal": por_canal,
        "total": total,
        "sin_fecha": sin_fecha,
        "fuera_de_periodo": fuera_de_periodo,
        "registros": len(registros),
    }


def _referencia_institucional(session: Session) -> tuple[list[dict[str, Any]], str | None]:
    """
    Devuelve la tabla de referencia del informe de gestion y su fecha de corte.

    Esta tabla se muestra como REFERENCIA (lo que el informe declara a su fecha de
    corte) y no se mezcla con los conteos individuales del Excel, porque ambos
    documentos tienen fechas distintas.
    """
    filas = _cargar_registros(session, "informe")
    corte = None
    for fila in filas:
        if fila.get("corte"):
            corte = fila["corte"]
            break
    return filas, corte


# ---------------------------------------------------------------------------
# Calculo principal
# ---------------------------------------------------------------------------


def compute_indicadores_2026(session: Session) -> dict[str, Any]:
    """
    Calcula los indicadores de certificacion del 1 de enero al 30 de septiembre de 2026.

    Todos los valores salen de los registros importados desde las fuentes
    documentales. Si un dato no se puede calcular, se devuelve ``None`` (no cero)
    y se agrega una advertencia en ``advertencias`` para que la interfaz pueda
    distinguir "no hay datos" de "el valor es cero".

    Formul formulas usadas:
      * % Avance    = certificados / meta * 100
      * Brecha      = max(0, meta - certificados)
      * Efectividad = certificados / (certificados + pendientes) * 100
    """
    metas, fuente_metas = _metas_institucionales(session)

    registros_certificados = _cargar_registros(session, "certificados")
    registros_pendientes = _cargar_registros(session, "pendientes")

    certificados = _resumen_hoja_actas(
        registros_certificados,
        estado_valido="certificados",
        filtrar_por_mes=True,
        leer_motivos=False,
    )
    pendientes = _resumen_hoja_actas(
        registros_pendientes,
        estado_valido="pendiente",
        filtrar_por_mes=False,
        leer_motivos=True,
    )
    # Si la hoja PENDIENTES no se ha importado todavia, no se puede saber cuantos
    # aprendices siguen pendientes. En ese caso se informa ``None`` (no se puede
    # calcular) en lugar de mostrar 0, que haria parecer que no hay pendientes.
    pendientes_disponibles = bool(registros_pendientes)
    complementaria = _resumen_complementaria(session)
    referencia, fecha_corte = _referencia_institucional(session)

    advertencias: list[str] = []

    # ---- Metricas por categoria ------------------------------------------
    metricas: list[dict[str, Any]] = []
    metas_faltantes: list[str] = []
    total_meta = 0
    total_certificados = 0
    total_pendientes = 0
    pendientes_completos = True

    for clave, etiqueta, nota in CATEGORIAS:
        meta = metas.get(clave)

        if clave == "complementaria":
            # Complementaria viene agregada (no hay personas individuales) y la
            # fuente no reporta aprendices pendientes: ese dato queda sin calcular.
            certificados_categoria = complementaria["total"]
            pendientes_categoria: int | None = None
            pendientes_detalle = None
        else:
            certificados_categoria = len(certificados["por_categoria"][clave])
            pendientes_categoria = (
                len(pendientes["por_categoria"][clave]) if pendientes_disponibles else None
            )
            pendientes_detalle = "aprendices unicos pendientes"

        # Meta ausente => no se puede calcular el avance (NO se muestra 0).
        if meta is None:
            metas_faltantes.append(etiqueta)
            avance = None
            brecha = None
        else:
            avance = round((certificados_categoria / meta) * 100, 1) if meta > 0 else None
            brecha = max(0, meta - certificados_categoria)

        # Efectividad: solo tiene sentido si conocemos certificados y pendientes.
        if pendientes_categoria is None:
            efectividad = None
            candidatos = None
        else:
            candidatos = certificados_categoria + pendientes_categoria
            efectividad = (
                round((certificados_categoria / candidatos) * 100, 1)
                if candidatos > 0
                else None
            )

        total_certificados += certificados_categoria
        if meta is not None:
            total_meta += meta
        if pendientes_categoria is None:
            pendientes_completos = False
        else:
            total_pendientes += pendientes_categoria

        metricas.append(
            {
                "category": clave,
                "category_label": etiqueta,
                "nota_doble_conteo": nota,
                "meta": meta,
                "certificados": certificados_categoria,
                "pendientes": pendientes_categoria,
                "pendientes_detalle": pendientes_detalle,
                "avance": avance,
                "brecha": brecha,
                "efectividad": efectividad,
                "formula_avance": {
                    "numerador": certificados_categoria,
                    "denominador": meta,
                    "formula": "certificados_unicos / meta_anual * 100",
                },
                "formula_efectividad": {
                    "numerador": certificados_categoria,
                    "denominador": candidatos,
                    "formula": "certificados_unicos / (certificados_unicos + pendientes_unicos) * 100",
                },
                "warning": (
                    "Meta no disponible en las fuentes: no se puede calcular el avance."
                    if meta is None
                    else None
                ),
            }
        )

    if metas_faltantes:
        advertencias.append(
            "No se encontro la meta de: " + ", ".join(metas_faltantes) + "."
        )
    if not pendientes_disponibles:
        advertencias.append(
            "No se ha cargado la hoja PENDIENTES: no se puede calcular el total de "
            "aprendices pendientes ni la efectividad de cierre."
        )
    elif not pendientes_completos:
        advertencias.append(
            "El total de pendientes NO incluye Formacion Complementaria: la hoja "
            "COMPLEMENTARIA no lista aprendices pendientes individuales."
        )

    # ---- Totales globales -------------------------------------------------
    # Si falta alguna meta, el total no representa la meta institucional completa.
    total_meta_valor: int | None = None if metas_faltantes else total_meta
    avance_global: float | None = (
        round((total_certificados / total_meta_valor) * 100, 1)
        if total_meta_valor
        else None
    )

    # Sin la hoja PENDIENTES el total queda SIN CALCULAR (None), no en cero.
    total_pendientes_valor: int | None = total_pendientes if pendientes_disponibles else None

    # Efectividad global: se calcula con los pendientes que SI se pudieron contar.
    candidatos_global: int | None = (
        total_certificados + total_pendientes if pendientes_disponibles else None
    )
    efectividad_global: float | None = (
        round((total_certificados / candidatos_global) * 100, 1)
        if candidatos_global
        else None
    )

    # ---- Sin clasificar ---------------------------------------------------
    niveles_sin_clasificar = {
        **{f"certificados: {k}": v for k, v in certificados["niveles_sin_clasificar"].items()},
        **{f"pendientes: {k}": v for k, v in pendientes["niveles_sin_clasificar"].items()},
    }
    sin_clasificar = {
        "certificados": len(certificados["sin_clasificar"]),
        "pendientes": len(pendientes["sin_clasificar"]),
        "niveles": niveles_sin_clasificar,
    }
    if sin_clasificar["certificados"] or sin_clasificar["pendientes"]:
        advertencias.append(
            "Hay registros con un NIVEL sin regla de clasificacion documentada "
            "(no se asignaron por defecto a ninguna categoria)."
        )

    if certificados["fuera_de_periodo"]:
        advertencias.append(
            f"{certificados['fuera_de_periodo']} certificados quedaron fuera del periodo "
            "Ene-Sep 2026 y no se contaron."
        )
    if certificados["sin_documento"]:
        advertencias.append(
            f"{certificados['sin_documento']} certificados sin numero de documento no se pudieron contar."
        )
    if complementaria["sin_fecha"]:
        advertencias.append(
            f"{complementaria['sin_fecha']} registros de complementaria sin fecha no se pudieron ubicar en el periodo."
        )

    # ---- Motivos de no certificacion --------------------------------------
    motivos_incidencias = pendientes["motivos"]
    total_incidencias = sum(motivos_incidencias.values())
    motivos = [
        {
            "motivo": motivo,
            "cantidad": cantidad,
            "porcentaje": (
                round((cantidad / total_incidencias) * 100, 1) if total_incidencias else None
            ),
        }
        for motivo, cantidad in motivos_incidencias.most_common()
    ]

    # ---- Actas del periodo (desde la hoja CERTIFICADOS) -------------------
    # La hoja CERTIFICADOS solo informa el numero de acta, no su fecha ni su tipo:
    # por eso esos campos van en ``None`` y la interfaz los muestra como
    # "no disponibles" en lugar de inventarlos.
    ultimas_actas = [
        {"number": acta, "aprendices_count": cantidad, "act_date": None, "act_type": None}
        for acta, cantidad in certificados["por_acta"].most_common(15)
    ]

    if (
        not certificados["total_documentos"]
        and not pendientes["total_documentos"]
        and not complementaria["registros"]
        and not metas
    ):
        advertencias.insert(
            0,
            "No hay documentos importados: cargue ACTAS 2026.xlsx (certificados, "
            "pendientes, complementaria, meta) y el informe de gestion para calcular "
            "los indicadores.",
        )

    datos_suficientes = bool(
        certificados["total_documentos"]
        or pendientes["total_documentos"]
        or complementaria["registros"]
        or metas
    )

    return {
        "periodo": PERIODO_LABEL,
        "periodo_inicio": PERIODO_INICIO,
        "periodo_fin": PERIODO_FIN,
        "fecha_corte_referencia": fecha_corte,
        "fuente_metas": fuente_metas,
        "datos_suficientes": datos_suficientes,
        "advertencias": advertencias,
        "warning": " | ".join(advertencias) if advertencias else None,
        "total_meta": total_meta_valor,
        "total_certificados": total_certificados,
        "total_pendientes": total_pendientes_valor,
        "total_pendientes_completo": pendientes_disponibles and pendientes_completos,
        "total_incidencias_causas": total_incidencias,
        "aprendices_con_causas_multiples": pendientes["documentos_con_varios_motivos"],
        "aprendices_pendientes_sin_motivo": pendientes["documentos_sin_motivo"],
        "avance_global": avance_global,
        "efectividad_global": efectividad_global,
        "formula_avance_global": {
            "numerador": total_certificados,
            "denominador": total_meta_valor,
            "formula": "total_certificados / total_meta_anual * 100",
        },
        "formula_efectividad_global": {
            "numerador": total_certificados,
            "denominador": candidatos_global,
            "formula": "total_certificados / (total_certificados + total_pendientes) * 100",
        },
        "sin_clasificar": sin_clasificar,
        "metricas": metricas,
        "motivos": motivos,
        "complementaria_canales": complementaria["por_canal"],
        "referencia_institucional": referencia,
        "ultimas_actas": ultimas_actas,
    }
