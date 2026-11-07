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
  documentada (por ejemplo NIVEL_DESCONOCIDO), el registro NO se asigna por
  defecto a ninguna categoria: se reporta aparte. OPERARIO se trata como AUXILIAR.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Act, ImportHistory, ImportedRecord, Learner
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

# Orden y etiqueta visible de los meses del corte. Se usan para el grafico de
# certificados por mes y para no depender del orden en que lleguen las filas.
MESES_ORDEN: tuple[tuple[str, str], ...] = (
    ("enero", "Enero"),
    ("febrero", "Febrero"),
    ("marzo", "Marzo"),
    ("abril", "Abril"),
    ("mayo", "Mayo"),
    ("junio", "Junio"),
    ("julio", "Julio"),
    ("agosto", "Agosto"),
    ("septiembre", "Septiembre"),
)

# Tipos internos que forman el consolidado institucional ACTAS 2026. El lote
# vigente se identifica por ``ImportHistory.source_type == 'actas_completo'``.
CONSOLIDATED_SOURCE_TYPE = "actas_completo"
CONSOLIDATED_INFORMATION_TYPES = frozenset(
    {"certificados", "pendientes", "complementaria", "meta"}
)

# Categorias que representan PERSONAS con certificacion titulada. La formacion
# complementaria es un universo distinto (certificados agregados, no personas) y
# se mantiene fuera de la efectividad global.
CATEGORIAS_PERSONAS = frozenset({"superior", "tecnica", "articulacion"})

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


def _lote_vigente(session: Session) -> int | None:
    """Id del ultimo lote exitoso de ACTAS 2026 (snapshot vigente).

    La reimportacion de ACTAS 2026 no borra lotes anteriores: los deja como
    historicos. El calculo de indicadores SOLO lee el ultimo lote confirmado de
    tipo ``actas_completo``. Si la base viene de una version anterior sin
    ``source_type``, se usa la etiqueta visible historica como respaldo.
    """
    from app.services.validation import TYPE_LABELS

    return session.scalar(
        select(ImportHistory.id)
        .where(
            ImportHistory.status == "completed",
            (
                (ImportHistory.source_type == CONSOLIDATED_SOURCE_TYPE)
                | (
                    (ImportHistory.source_type.is_(None))
                    & (ImportHistory.information_type == TYPE_LABELS[CONSOLIDATED_SOURCE_TYPE])
                )
            ),
        )
        .order_by(ImportHistory.id.desc())
        .limit(1)
    )


def _cargar_registros(
    session: Session,
    information_type: str,
    batch_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Recupera de SQLite los registros importados de un tipo de informacion.

    Si ``batch_id`` se entrega, solo devuelve las filas del lote vigente y las
    actualizaciones posteriores hechas por fuentes alternativas (por ejemplo el
    CSV que corrige un certificado ya existente). Los lotes ANTERIORES quedan
    historicos y se excluyen; por eso se usa ``import_id >= batch_id`` y no una
    union de todo el historial.
    Si no, mantiene compatibilidad con datos sembrados o cargas antiguas: usa el
    ultimo lote que contenga ese tipo, en lugar de unir todos los historicos.
    
    Un ``payload`` corrupto se omite para no detener el calculo por una fila mala.
    """
    if batch_id is not None:
        limite_inferior = batch_id
    else:
        limite_inferior = session.scalar(
            select(ImportedRecord.import_id)
            .where(ImportedRecord.information_type == information_type)
            .order_by(ImportedRecord.id.desc())
            .limit(1)
        )
        if limite_inferior is None:
            return []

    filas = session.scalars(
        select(ImportedRecord)
        .where(
            ImportedRecord.information_type == information_type,
            ImportedRecord.import_id >= limite_inferior,
        )
        .order_by(ImportedRecord.id.asc())
    ).all()
    registros: list[dict[str, Any]] = []
    # Defensa ante filas duplicadas por clave: conserva la version mas reciente
    # (mayor id) para no sumar dos veces la misma persona/periodo.
    unicas: dict[str, ImportedRecord] = {}
    for fila in filas:
        unicas[fila.record_key or str(fila.id)] = fila
    for fila in sorted(unicas.values(), key=lambda item: item.id):
        try:
            contenido = json.loads(fila.payload)
        except (TypeError, ValueError):
            continue
        if isinstance(contenido, dict):
            registros.append(contenido)
    return registros


def _metas_institucionales(
    session: Session, batch_id: int | None = None
) -> tuple[dict[str, int], str | None]:
    """
    Obtiene las metas anuales desde las fuentes documentales (nunca del codigo).

    Prioridad:
      1. Hoja META del LOTE VIGENTE de ``ACTAS 2026.xlsx`` (fuente principal).
      2. Solo si no hay lote vigente, la tabla de referencia del informe de
         gestion en Word (respaldo documental).

    Dentro del lote se elige UNA sola fila META (la ultima), nunca se suman dos.
    Si la meta esta incompleta se devuelve lo que exista y el llamador expone la
    advertencia; las categorias sin meta quedan en ``None``, no en cero.

    Devuelve ``(metas, fuente)`` con claves internas ("superior", "tecnica",
    "articulacion", "complementaria"). Si no hay fuente, ``({}, None)``.
    """
    registros_meta = _cargar_registros(session, "meta", batch_id)
    for registro in reversed(registros_meta):
        metas = {
            clave: valor
            for clave, valor in registro.items()
            if clave in {"superior", "tecnica", "articulacion", "complementaria"}
            and isinstance(valor, int)
        }
        if metas:
            return metas, "ACTAS 2026.xlsx (hoja META)"

    # El lote vigente manda: si existe pero no trae META, no se rescata una meta
    # vieja de otro lote (seria mezclar snapshots). Solo sin lote se usa el Word.
    if batch_id is not None:
        return {}, None

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
        # 1) Solo cuentan las filas con el estado esperado. Se aceptan las
        # variantes documentadas en parsers (Certificado/CERTIFICADOS/etc.).
        if parsers.normalize_certification_status(registro.get("estado")) != estado_valido:
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
            lista_motivos = parsers.normalize_motivo_fragments(
                registro.get("motivo de no certificacion")
            )
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


def _resumen_complementaria(
    session: Session, batch_id: int | None = None
) -> dict[str, Any]:
    """
    Suma los certificados de formacion complementaria por canal dentro del periodo.

    La hoja COMPLEMENTARIA no lista personas: cada fila informa una fecha y
    cuantos certificados se expidieron en un canal. Por eso aqui se SUMAN
    cantidades y NO se mezclan con el conteo de personas ni con la efectividad.
    Solo se lee el lote vigente (o el ultimo lote del tipo si no hay snapshot).
    """
    por_canal: dict[str, int] = {canal: 0 for canal in CANALES_COMPLEMENTARIA}
    por_canal["otro"] = 0
    total = 0
    sin_fecha = 0
    fuera_de_periodo = 0

    registros = _cargar_registros(session, "complementaria", batch_id)
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


def _acta_clave(value: Any) -> str:
    """Clave tolerante para cruzar el numero de acta del consolidado con la BD.

    El consolidado puede traer ``"41"`` y el modulo de actas ``"041"`` o
    ``"Acta 41"``; se comparan sin espacios, mayusculas ni ceros a la izquierda.
    """
    texto = str(value or "").strip().upper()
    if texto.startswith("ACTA "):
        texto = texto[5:].strip()
    if texto.isdigit():
        return str(int(texto))
    return texto


def _documento(registro: dict[str, Any]) -> str | None:
    """Documento normalizado de una fila del consolidado."""
    return parsers.clean_identification(registro.get("numero de documento"))


def _es_certificado_vigente(registro: dict[str, Any]) -> bool:
    """Fila contable como certificado: estado valido y mes dentro del corte."""
    return (
        parsers.normalize_certification_status(registro.get("estado")) == "certificados"
        and parsers.normalize_text(registro.get("mes de certificacion"))
        in MESES_DEL_PERIODO
    )


def _es_pendiente_vigente(registro: dict[str, Any]) -> bool:
    """Fila contable como pendiente: estado valido (sin fecha de certificacion)."""
    return parsers.normalize_certification_status(registro.get("estado")) == "pendiente"


def _resoluciones_conflicto(
    session: Session, documentos: set[str]
) -> dict[str, str]:
    """Resoluciones manuales guardadas en el aprendiz para documentos en conflicto.

    La fuente de verdad es ``Learner.conflict_resolution``. Para bases anteriores
    se reconoce ademas la nota historica "Conflicto resuelto: ..." que escribia
    la importacion, de modo que una resolucion previa no se pierde.
    """
    if not documentos:
        return {}
    learners = session.scalars(
        select(Learner).where(Learner.identification.in_(documentos))
    ).all()
    resoluciones: dict[str, str] = {}
    for learner in learners:
        estado = parsers.normalize_certification_status(
            getattr(learner, "conflict_resolution", None)
        )
        if estado not in {"certificados", "pendiente"}:
            notas = learner.tracking_notes or ""
            if "Conflicto resuelto: Certificado" in notas:
                estado = "certificados"
            elif "Conflicto resuelto: Pendiente" in notas:
                estado = "pendiente"
        if estado in {"certificados", "pendiente"}:
            resoluciones[learner.identification] = estado
    return resoluciones


def _separar_conflictos(
    session: Session,
    registros_certificados: list[dict[str, Any]],
    registros_pendientes: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    set[str],
    dict[str, str],
]:
    """Aplica la regla unica de verdad cuando un documento esta en ambas hojas.

    Regla (B3):
      * Resolucion "CERTIFICADOS" -> cuenta como certificado y se descarta del
        universo de pendientes.
      * Resolucion "PENDIENTE" -> cuenta como pendiente y se descarta del
        universo de certificados.
      * Sin resolucion -> se excluye de AMBOS universos y se informa en
        advertencias. Nunca se suma dos veces a la misma persona.

    La deteccion usa solo filas que efectivamente contarian (estado valido y,
    para certificados, mes dentro del periodo). Un certificado fuera de periodo
    no convierte en conflicto a un pendiente vigente.
    """
    documentos_certificados = {
        documento
        for registro in registros_certificados
        if _es_certificado_vigente(registro)
        if (documento := _documento(registro))
    }
    documentos_pendientes = {
        documento
        for registro in registros_pendientes
        if _es_pendiente_vigente(registro)
        if (documento := _documento(registro))
    }
    conflictos = documentos_certificados & documentos_pendientes
    resoluciones = _resoluciones_conflicto(session, conflictos)

    certificados_filtrados: list[dict[str, Any]] = []
    for registro in registros_certificados:
        documento = _documento(registro)
        if documento in conflictos and resoluciones.get(documento) != "certificados":
            continue
        certificados_filtrados.append(registro)

    pendientes_filtrados: list[dict[str, Any]] = []
    for registro in registros_pendientes:
        documento = _documento(registro)
        if documento in conflictos and resoluciones.get(documento) != "pendiente":
            continue
        pendientes_filtrados.append(registro)

    return certificados_filtrados, pendientes_filtrados, conflictos, resoluciones


def compute_certificados_por_mes(
    session: Session, batch_id: int | None = None
) -> dict[str, Any]:
    """Certificados del CONSOLIDADO agrupados por mes de certificacion.

    No usa ``Learner.certification_month`` ni la fecha de importacion: lee las
    filas CERTIFICADOS del lote vigente de ACTAS 2026 y cuenta personas unicas
    por el mes declarado en la hoja. Solo se incluyen los meses del corte
    Ene-Sep 2026; lo que queda fuera se informa aparte y no infla el total.
    """
    lote = batch_id if batch_id is not None else _lote_vigente(session)
    registros_certificados = _cargar_registros(session, "certificados", lote)
    registros_pendientes = _cargar_registros(session, "pendientes", lote)
    certificados, _, conflictos, resoluciones = _separar_conflictos(
        session, registros_certificados, registros_pendientes
    )

    por_mes = {mes: 0 for mes, _ in MESES_ORDEN}
    vistos: set[str] = set()
    fuera_de_periodo = 0
    sin_mes = 0
    sin_documento = 0

    for registro in certificados:
        if parsers.normalize_certification_status(registro.get("estado")) != "certificados":
            continue
        documento = _documento(registro)
        if not documento:
            sin_documento += 1
            continue
        mes = parsers.normalize_text(registro.get("mes de certificacion"))
        if not mes:
            sin_mes += 1
            continue
        if mes not in MESES_DEL_PERIODO:
            fuera_de_periodo += 1
            continue
        if documento in vistos:
            continue
        vistos.add(documento)
        por_mes[mes] += 1

    meses = [
        {"mes": mes, "etiqueta": etiqueta, "certificados": por_mes[mes]}
        for mes, etiqueta in MESES_ORDEN
    ]
    sin_resolver = conflictos - set(resoluciones)
    return {
        "periodo": PERIODO_LABEL,
        "periodo_inicio": PERIODO_INICIO,
        "periodo_fin": PERIODO_FIN,
        "universo": "consolidado",
        "fuente": "ACTAS 2026 · hoja CERTIFICADOS (lote vigente)",
        "lote_id": lote,
        "meses": meses,
        "total": sum(por_mes.values()),
        "documentos_unicos": len(vistos),
        "fuera_de_periodo": fuera_de_periodo,
        "sin_mes": sin_mes,
        "sin_documento": sin_documento,
        "conflictos_sin_resolver": len(sin_resolver),
    }



def compute_indicadores_2026(session: Session) -> dict[str, Any]:
    """
    Calcula los indicadores de certificacion del 1 de enero al 30 de septiembre de 2026.

    Universos separados (no se mezclan sin etiqueta)
    ------------------------------------------------
    * **Personas / titulada**: filas de CERTIFICADOS y PENDIENTES del lote
      vigente de ACTAS 2026, en las categorias superior, tecnica y articulacion.
    * **Formacion complementaria**: agregados de la hoja COMPLEMENTARIA. No son
      personas y no entran en la efectividad global.

    Reglas exactas
    --------------
    * ``% Avance`` por categoria = certificados / meta * 100 (la complementaria
      usa sus propios certificados agregados y su propia meta).
    * ``Brecha`` = max(0, meta - certificados).
    * ``Efectividad global`` = ``certificados_personas / (certificados_personas +
      pendientes_personas) * 100``. Si falta PENDIENTES o no hay denominador,
      devuelve ``None`` y se advierte; nunca usa complementaria como denominador.
    * Conflicto CERTIFICADOS/PENDIENTES: si el usuario lo resolvio se respeta;
      si sigue sin resolver, la persona se excluye de ambos universos y se
      lista en advertencias. Nunca cuenta dos veces.

    Solo se lee el lote vigente (ultimo ``actas_completo`` confirmado). Los lotes
    anteriores quedan historicos y no entran al calculo. Si no existe lote, se
    conserva compatibilidad con registros sembrados/cargas antiguas usando el
    ultimo import que contenga cada tipo.

    Si un dato no se puede calcular se devuelve ``None`` (no cero) y se agrega
    una advertencia en ``advertencias`` para distinguir "no hay datos" de "cero".
    """
    lote_id = _lote_vigente(session)
    metas, fuente_metas = _metas_institucionales(session, lote_id)

    registros_certificados = _cargar_registros(session, "certificados", lote_id)
    registros_pendientes = _cargar_registros(session, "pendientes", lote_id)

    # B3: resolver el conflicto antes de contar, no solo avisar en la UI.
    (
        registros_certificados,
        registros_pendientes,
        conflictos_cert_pend,
        resoluciones_conflicto,
    ) = _separar_conflictos(session, registros_certificados, registros_pendientes)

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
    complementaria = _resumen_complementaria(session, lote_id)
    referencia, fecha_corte = _referencia_institucional(session)

    advertencias: list[str] = []

    # ---- Metricas por categoria ------------------------------------------
    metricas: list[dict[str, Any]] = []
    metas_faltantes: list[str] = []
    total_meta = 0
    total_certificados = 0
    total_certificados_personas = 0
    total_certificados_complementaria = 0
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
        if clave in CATEGORIAS_PERSONAS:
            total_certificados_personas += certificados_categoria
        elif clave == "complementaria":
            total_certificados_complementaria += certificados_categoria
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
                "universo": (
                    "personas" if clave in CATEGORIAS_PERSONAS else "complementaria"
                ),
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
    if lote_id is not None and fuente_metas is None:
        advertencias.append(
            "El lote vigente de ACTAS 2026 no trae una fila META reconocible: "
            "no se puede calcular el avance sobre la meta institucional."
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

    # ---- Conflictos CERTIFICADOS/PENDIENTES (B3) -------------------------
    # El conteo ya se hizo sobre las listas filtradas. Aqui solo se informa que
    # decision se aplico a cada documento para que el numero sea contrastable.
    conflictos_sin_resolver = conflictos_cert_pend - set(resoluciones_conflicto)
    if conflictos_cert_pend:
        advertencias.append(
            f"Inconsistencia de coherencia: {len(conflictos_cert_pend)} aprendiz(ces) figuran "
            "simultáneamente como certificados y pendientes. No se cuentan dos veces: "
            "se aplica la resolución guardada y lo no resuelto se excluye de ambos totales."
        )
    if conflictos_sin_resolver:
        advertencias.append(
            f"{len(conflictos_sin_resolver)} conflicto(s) sin resolver se excluyeron de "
            "certificados y pendientes (documentos: "
            + ", ".join(sorted(conflictos_sin_resolver))
            + ")."
        )
    if resoluciones_conflicto:
        advertencias.append(
            f"Se aplicaron {len(resoluciones_conflicto)} resolución(es) manuales de "
            "conflicto al cálculo de indicadores."
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

    # Efectividad global SOLO sobre personas/titulada. La complementaria es otro
    # universo y no puede ser denominador de esta razon.
    candidatos_global: int | None = (
        total_certificados_personas + total_pendientes
        if pendientes_disponibles
        else None
    )
    efectividad_global: float | None = (
        round((total_certificados_personas / candidatos_global) * 100, 1)
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
        cantidad = certificados["fuera_de_periodo"]
        plural = "" if cantidad == 1 else "s"
        verbo = "quedó" if cantidad == 1 else "quedaron"
        verbo_contar = "contó" if cantidad == 1 else "contaron"
        advertencias.append(
            f"{cantidad} certificado{plural} {verbo} fuera del periodo Ene-Sep 2026 "
            f"y no se {verbo_contar}."
        )
    if certificados["sin_documento"]:
        advertencias.append(
            f"{certificados['sin_documento']} certificados sin numero de documento no se pudieron contar."
        )
    if complementaria["sin_fecha"]:
        advertencias.append(
            f"{complementaria['sin_fecha']} registros de complementaria sin fecha no se pudieron ubicar en el periodo."
        )

    # ---- Coherencia cruzada: ya resuelta antes de contar (B3) -------------
    # No se vuelve a calcular aqui: ``conflictos_cert_pend`` y
    # ``resoluciones_conflicto`` vienen del filtro aplicado a los totales.

    # ---- Motivos de no certificacion --------------------------------------
    # ``cantidad`` conserva el significado historico: personas unicas que
    # registran la causa (una persona suma una vez por causa, no una vez por
    # incidencia repetida). La suma de todas las causas es el total de
    # asociaciones persona-causa ("incidencias") y puede superar a las personas
    # pendientes porque una persona puede tener varias causas.
    motivos_incidencias = pendientes["motivos"]
    total_incidencias = sum(motivos_incidencias.values())
    pendientes_unicos_total = (
        pendientes["total_documentos"] if pendientes_disponibles else None
    )
    motivos = [
        {
            "motivo": motivo,
            "cantidad": cantidad,
            "personas": cantidad,
            "porcentaje": (
                round((cantidad / total_incidencias) * 100, 1) if total_incidencias else None
            ),
            "porcentaje_personas": (
                round((cantidad / pendientes_unicos_total) * 100, 1)
                if pendientes_unicos_total
                else None
            ),
        }
        for motivo, cantidad in motivos_incidencias.most_common()
    ]
    porcentaje_sin_motivo = (
        round((pendientes["documentos_sin_motivo"] / pendientes_unicos_total) * 100, 1)
        if pendientes_unicos_total
        else None
    )

    # ---- Actas del periodo (desde la hoja CERTIFICADOS) -------------------
    # La hoja CERTIFICADOS solo informa el numero de acta, no su fecha ni su tipo.
    # Si el acta ya existe en el modulo de Actas, se completan fecha/tipo y se
    # expone ``act_id`` para enlazar al detalle; si no, quedan en ``None`` para
    # que la interfaz no invente datos.
    actas_por_clave: dict[str, Act] = {}
    if certificados["por_acta"]:
        # La tabla de actas es pequena (registro manual/importacion); se cruza por
        # clave tolerante para emparejar "041" del consolidado con "41" de la BD.
        for acta_db in session.scalars(select(Act)).all():
            clave = _acta_clave(acta_db.number)
            if clave and clave not in actas_por_clave:
                actas_por_clave[clave] = acta_db

    actas_periodo = []
    for acta, cantidad in certificados["por_acta"].most_common():
        acta_db = actas_por_clave.get(_acta_clave(acta))
        act_date = (
            acta_db.act_date.isoformat()
            if acta_db is not None and acta_db.act_date
            else None
        )
        act_type = acta_db.act_type if acta_db is not None else None
        actas_periodo.append(
            {
                "number": acta,
                "aprendices_count": cantidad,
                "act_date": act_date,
                "act_type": act_type,
                "act_id": acta_db.id if acta_db is not None else None,
                "metadata_completa": bool(act_date and act_type),
            }
        )
    # ``ultimas_actas`` se conserva para la tabla resumida de la interfaz.
    ultimas_actas = actas_periodo[:15]

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
        "lote_vigente_id": lote_id,
        "lote_vigente_alcance": (
            "consolidado ACTAS 2026 (último lote confirmado)"
            if lote_id is not None
            else "compatibilidad: último import por tipo (sin lote actas_completo)"
        ),
        "total_meta": total_meta_valor,
        # ``total_certificados`` conserva el total de todas las categorias
        # (personas + complementaria) para el avance global contra la meta.
        # Para efectividad y lectura de personas use los campos explicitos.
        "total_certificados": total_certificados,
        "total_certificados_alcance": "personas + formacion complementaria",
        "certificados_personas": total_certificados_personas,
        "total_certificados_personas": total_certificados_personas,
        "certificados_complementaria": total_certificados_complementaria,
        "total_pendientes": total_pendientes_valor,
        "pendientes_personas": total_pendientes_valor,
        # Total de documentos unicos de PENDIENTES, incluidos los que no se
        # pudieron clasificar por NIVEL. Se usa como denominador de causas para
        # no comparar contra una base distinta a la que se conto.
        "pendientes_unicos_total": pendientes_unicos_total,
        "total_pendientes_completo": pendientes_disponibles and pendientes_completos,
        "total_incidencias_causas": total_incidencias,
        "aprendices_con_causas_multiples": pendientes["documentos_con_varios_motivos"],
        "aprendices_pendientes_sin_motivo": pendientes["documentos_sin_motivo"],
        "porcentaje_pendientes_sin_motivo": porcentaje_sin_motivo,
        "avance_global": avance_global,
        "efectividad_global": efectividad_global,
        "universo_efectividad": "personas titulada (sin formacion complementaria)",
        "formula_avance_global": {
            "numerador": total_certificados,
            "denominador": total_meta_valor,
            "formula": "total_certificados (personas + complementaria) / total_meta_anual * 100",
        },
        "formula_efectividad_global": {
            "numerador": total_certificados_personas,
            "denominador": candidatos_global,
            "formula": (
                "certificados_personas / (certificados_personas + pendientes_personas) * 100"
            ),
        },
        "sin_clasificar": sin_clasificar,
        "certificados_fuera_de_periodo": certificados["fuera_de_periodo"],
        "certificados_sin_documento": certificados["sin_documento"],
        "metricas": metricas,
        "motivos": motivos,
        "complementaria_canales": complementaria["por_canal"],
        "referencia_institucional": referencia,
        "ultimas_actas": ultimas_actas,
        # Listado completo de actas del periodo (no solo las 15 de la UI).
        "actas_periodo": actas_periodo,
        "actas_periodo_total": len(actas_periodo),
        "actas_sin_metadatos": sum(
            1 for acta in actas_periodo if not acta["metadata_completa"]
        ),
        "actas_con_detalle": sum(1 for acta in ultimas_actas if acta["act_id"]),
        "conflictos_certificados_pendientes": len(conflictos_cert_pend),
        "resoluciones_conflicto": dict(resoluciones_conflicto),
        "conflictos": {
            "detectados": len(conflictos_cert_pend),
            "resueltos": len(resoluciones_conflicto),
            "sin_resolver": len(conflictos_sin_resolver),
            "documentos_sin_resolver": sorted(conflictos_sin_resolver),
            "resoluciones": dict(resoluciones_conflicto),
        },
        # B5: el mismo corte mensual que expone el endpoint dedicado, desde el
        # consolidado vigente y no desde el padron local.
        "certificados_por_mes": compute_certificados_por_mes(session, lote_id),
    }
