"""
Modulo de servicios para la gestion de aprendices (Learner).
Contiene la logica de negocio para:
- Listado paginado de aprendices con busqueda y filtros
- Obtencion del detalle completo de un aprendiz (info basica, requisitos, actas, fechas, historial)
- Construccion de vistas provisionales para requisitos, actas e historial
- Sincronizacion y carga de aprendices a partir de registros importados (DF14A)
- Listado de valores disponibles para filtros
"""

from __future__ import annotations

import json  # Para serializar/deserializar payloads de registros importados
import hashlib  # Para generar identificadores automaticos cuando falta el documento
from datetime import date, datetime  # Para manejo de fechas en vistas
from unicodedata import normalize  # Para normalizar textos y buscar sin tildes
from typing import Any  # Para anotaciones genericas de diccionarios

from sqlalchemy import and_, func, or_, select  # Construccion de consultas SQLAlchemy
from sqlalchemy.orm import Session, joinedload  # Sesion y carga ansiosa de relaciones

from app.models import Act, ActLearner, ImportHistory, ImportedRecord, Learner, Requirement  # Modelos ORM


def list_learners(
    session: Session,
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    program: str | None = None,
    group_code: str | None = None,
    training_type: str | None = None,
) -> dict[str, Any]:
    """
    Lista paginada de aprendices con soporte de busqueda textual y filtros.
    - Si la tabla learners esta vacia, sincroniza automaticamente desde los registros DF14A importados.
    - search: filtra por nombre, documento, ficha o programa (insensible a mayusculas).
    - status, program, group_code, training_type: filtros adicionales por campos especificos.
    - page/page_size: control de paginacion.
    Retorna diccionario con items, total de registros, pagina actual, tamanio y cantidad de paginas.
    """
    learner_count = session.scalar(select(func.count()).select_from(Learner)) or 0
    df14a_records_count = session.scalar(
        select(func.count()).select_from(ImportedRecord).where(
            func.lower(ImportedRecord.information_type) == "df14a"
        )
    ) or 0
    # Sincronizacion resiliente: si no hay aprendices, o hay registros DF14A importados sin
    # que se hayan volcado aun a la tabla Learner, reconstruimos. Esto corrige casos de
    # importaciones anteriores donde el upsert fallo por diferencias de mayusculas/minusculas
    # o errores silenciosos.
    if learner_count == 0 or (df14a_records_count > 0 and learner_count < df14a_records_count):
        sync_learners_from_imports(session)
        session.commit()
        learner_count = session.scalar(select(func.count()).select_from(Learner)) or 0
    filters = []
    # Filtro de busqueda de texto completo sobre 4 campos principales
    if search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Learner.name.ilike(term),
                Learner.identification.ilike(term),
                Learner.group_code.ilike(term),
                Learner.program.ilike(term),
            )
        )
    # Filtros especificos por campo (coincidencia parcial con ilike)
    if status:
        filters.append(Learner.certification_status.ilike(f"%{status}%"))
    if program:
        filters.append(Learner.program.ilike(f"%{program}%"))
    if group_code:
        filters.append(Learner.group_code.ilike(f"%{group_code}%"))
    if training_type:
        filters.append(Learner.training_type.ilike(f"%{training_type}%"))
    query = select(Learner).order_by(Learner.name.asc(), Learner.id.asc())
    count_query = select(func.count()).select_from(Learner)
    # Aplicar filtros tanto a la consulta de datos como a la de conteo total
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))
    total = session.scalar(count_query) or 0
    learners = session.scalars(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [learner_result(learner) for learner in learners],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def learner_result(learner: Learner) -> dict[str, Any]:
    """
    Convierte un objeto Learner ORM a un diccionario plano para el listado.
    Incluye campos basicos: id, documento, nombre, programa, ficha, tipo formacion,
    estado de certificacion y fechas. Las fechas se serializan a ISO 8601.
    """
    return {
        "id": learner.id,
        "identification": learner.identification,
        "name": learner.name,
        "program": learner.program,
        "group_code": learner.group_code,
        "training_type": learner.training_type,
        "certification_status": learner.certification_status,
        "termination_date": learner.termination_date.isoformat() if learner.termination_date else None,
        "start_date": learner.start_date.isoformat() if learner.start_date else None,
    }


def get_learner_detail(session: Session, learner_id: int) -> dict[str, Any] | None:
    """
    Obtiene el detalle completo de un aprendiz por su ID.
    Usa joinedload para cargar ansiosamente las relaciones requirements y acts.
    Retorna una estructura agrupada en secciones:
      - basic_info: informacion basica del aprendiz
      - requirements: estado de los 5 requisitos con valores provisionales si faltan
      - acts: listado de actas asociadas al aprendiz
      - history: historial de actualizaciones/importaciones
      - dates: inicio y terminacion del programa
    Retorna None si el aprendiz no existe.
    """
    learner = session.scalar(
        select(Learner)
        .options(
            joinedload(Learner.requirements),
            joinedload(Learner.acts).joinedload(ActLearner.act),
        )
        .where(Learner.id == learner_id)
    )
    if learner is None:
        return None
    return {
        "basic_info": {
            "id": learner.id,
            "identification": learner.identification,
            "name": learner.name,
            "program": learner.program,
            "group_code": learner.group_code,
            "training_type": learner.training_type,
            "certification_status": learner.certification_status,
            "termination_date": learner.termination_date.isoformat() if learner.termination_date else None,
            "start_date": learner.start_date.isoformat() if learner.start_date else None,
            "tracking_notes": learner.tracking_notes,
        },
        "requirements": build_requirements_view(learner),
        "acts": build_acts_view(learner),
        "history": build_history_view(session, learner),
        "dates": build_dates_view(learner),
    }


def build_requirements_view(learner: Learner) -> dict[str, Any]:
    """
    Construye la vista provisional de requisitos para un aprendiz.
    Si existe un registro Requirement asociado, usa sus valores; de lo contrario
    devuelve "Pendiente" por defecto para todos los requisitos excepto Saber TyT,
    cuyo estado se infiere a partir del tipo de formacion (tecnico/tecnologo aplica,
    auxiliar/operario no aplica).
    Campos: learning_outcome, documentation, productive_stage, clearance, saber_tyt,
    overall_status y observations.
    """
    stored = learner.requirements[0] if learner.requirements else None
    default_status = "Pendiente"
    saber_tyt_default = _infer_saber_tyt_applies(learner.training_type)
    return {
        "learning_outcome": stored.learning_outcome if stored and stored.learning_outcome else default_status,
        "documentation": stored.documentation_status if stored and stored.documentation_status else default_status,
        "productive_stage": stored.productive_stage_status if stored and stored.productive_stage_status else default_status,
        "clearance": stored.clearance_status if stored and stored.clearance_status else default_status,
        "saber_tyt": stored.saber_tyt_status if stored and stored.saber_tyt_status else saber_tyt_default,
        "overall_status": stored.status if stored and stored.status else default_status,
        "observations": stored.observations if stored else None,
    }


def _infer_saber_tyt_applies(training_type: str | None) -> str:
    """
    Inferencia heuristica provisional de si Saber TyT aplica al aprendiz.
    Basado en el tipo de formacion: si contiene "tecnico" o "tecnologo" (con o sin tilde)
    marca como Pendiente (debe presentar), de lo contrario No aplica.
    Esta regla se podra refinar cuando se obtenga la fuente oficial.
    """
    if not training_type:
        return "Pendiente"
    normalized = training_type.lower()
    if "tecnico" in normalized or "tecnologo" in normalized or "técnico" in normalized or "tecnólogo" in normalized:
        return "Pendiente"
    return "No aplica"


def build_acts_view(learner: Learner) -> list[dict[str, Any]]:
    """
    Construye el listado de actas asociadas a un aprendiz a traves de la tabla puente ActLearner.
    Devuelve informacion resumida de cada acta: numero, fecha, tipo, archivo, estado de revision
    y observaciones (del vinculo o del acta global).
    """
    if not learner.acts:
        return []
    return [
        {
            "id": link.act.id,
            "number": link.act.number,
            "act_date": link.act.act_date.isoformat() if link.act.act_date else None,
            "act_type": link.act.act_type,
            "original_file": link.act.original_file,
            "review_status": link.act.review_status,
            "observations": link.observations or link.act.observations,
        }
        for link in learner.acts
        if link.act is not None
    ]


def build_history_view(session: Session, learner: Learner) -> list[dict[str, Any]]:
    """
    Construye el historial de actualizaciones del aprendiz a partir de los
    registros importados de tipo DF14A. Identifica el aprendiz por su numero
    de documento dentro del payload JSON de cada ImportedRecord.
    Retorna lista de eventos con fecha, descripcion del evento y archivo fuente.
    """
    records = session.scalars(
        select(ImportedRecord)
        .join(ImportHistory, ImportHistory.id == ImportedRecord.import_id)
        .where(func.lower(ImportedRecord.information_type) == "df14a")
        .order_by(ImportHistory.imported_at.desc())
    ).all()
    history: list[dict[str, Any]] = []
    for record in records:
        payload = json.loads(record.payload)
        identification = _extract_identification(payload)
        # Solo incluir entradas cuyo documento coincida con el aprendiz consultado
        if identification and identification == learner.identification:
            imported_at = record.import_history.imported_at if record.import_history else None
            history.append(
                {
                    "date": imported_at.strftime("%d/%m/%Y") if imported_at else None,
                    "event": f"Actualizacion {record.import_history.information_type if record.import_history else 'DF14A'}",
                    "source": record.import_history.file_name if record.import_history else None,
                }
            )
    return history


def _extract_identification(payload: dict[str, Any]) -> str | None:
    """
    Extrae y normaliza el numero de documento de un payload de registro importado.
    Prueba multiples variantes de nombres de columna (documento, NIS, cedula, etc.)
    y limpia el prefijo de tipo de documento cuando viene como TI_12345 o CC_12345.
    """
    normalized = {_normalize_key(str(key)): value for key, value in payload.items()}
    raw = _first_value(
        normalized,
        "documento",
        "nis",
        "numero documento",
        "n de identificacion",
        "no de identificacion",
        "numero de identificacion",
        "identificacion",
        "cedula",
    )
    if raw is None:
        return None
    cleaned = str(raw).strip()
    # Manejar formato TIPO_NUMERO (ej: TI_1028865527) extrayendo solo la parte numerica
    if "_" in cleaned:
        prefix, suffix = cleaned.split("_", 1)
        if suffix.isdigit():
            return suffix
    return cleaned


def build_dates_view(learner: Learner) -> dict[str, Any]:
    """
    Vista compacta con las fechas relevantes del aprendiz:
    fecha de inicio del programa y fecha de terminacion estimada.
    """
    return {
        "start_date": learner.start_date.isoformat() if learner.start_date else None,
        "termination_date": learner.termination_date.isoformat() if learner.termination_date else None,
    }


def list_learner_filters(session: Session) -> dict[str, list[dict[str, Any]]]:
    """
    Devuelve los valores unicos disponibles para cada filtro del listado de aprendices.
    Sirve para poblar los desplegables de la UI: estados, programas, fichas, tipos de formacion.
    Los valores se devuelven ordenados alfabeticamente y filtrando nulos/vacios.
    """
    statuses = session.scalars(
        select(Learner.certification_status).where(Learner.certification_status.isnot(None)).distinct()
    ).all()
    programs = session.scalars(
        select(Learner.program).where(Learner.program.isnot(None)).distinct()
    ).all()
    group_codes = session.scalars(
        select(Learner.group_code).where(Learner.group_code.isnot(None)).distinct()
    ).all()
    training_types = session.scalars(
        select(Learner.training_type).where(Learner.training_type.isnot(None)).distinct()
    ).all()
    return {
        "statuses": [{"value": value, "label": value} for value in sorted(statuses) if value],
        "programs": [{"value": value, "label": value} for value in sorted(programs) if value],
        "group_codes": [{"value": value, "label": value} for value in sorted(group_codes) if value],
        "training_types": [{"value": value, "label": value} for value in sorted(training_types) if value],
    }


def sync_learners_from_imports(session: Session) -> int:
    """
    Sincronizacion robusta: toma todos los ImportedRecord de tipo DF14A
    (case-insensitive, contempla variaciones "df14a", "DF14A", etc.)
    y los convierte en registros Learner (insert o update por documento).
    Retorna la cantidad de registros creados o actualizados.
    """
    records = session.scalars(
        select(ImportedRecord)
        .where(func.lower(ImportedRecord.information_type) == "df14a")
        .order_by(ImportedRecord.id.asc())
    ).all()
    return upsert_learners_from_records(session, [json.loads(record.payload) for record in records])


def upsert_learners_from_records(session: Session, records: list[dict[str, Any]]) -> int:
    """
    Realiza un upsert (insertar o actualizar) masivo de aprendices a partir de una
    lista de diccionarios sin procesar. La coincidencia se realiza por numero de
    documento (identification). Se actualizan solo los campos que realmente cambiaron.
    Retorna cantidad de filas afectadas (creadas + modificadas).
    """
    prepared_rows = []
    for record in records:
        prepared = _prepare_learner_row(record)
        if prepared is not None:
            prepared_rows.append(prepared)
    if not prepared_rows:
        return 0

    identifications = [row["identification"] for row in prepared_rows]
    existing = session.scalars(
        select(Learner).where(Learner.identification.in_(identifications))
    ).all()
    existing_by_identification = {learner.identification: learner for learner in existing}

    updated = 0
    for row in prepared_rows:
        learner = existing_by_identification.get(row["identification"])
        # Caso 1: aprendiz nuevo -> insertar
        if learner is None:
            session.add(Learner(**row))
            updated += 1
            continue
        # Caso 2: aprendiz existente -> actualizar campos modificados
        changed = False
        for field, value in row.items():
            if getattr(learner, field) != value:
                setattr(learner, field, value)
                changed = True
        if changed:
            updated += 1
    session.flush()
    return updated


def _prepare_learner_row(record: dict[str, Any]) -> dict[str, Any] | None:
    """
    Normaliza un diccionario crudo de un registro importado (DF14A) a la estructura
    del modelo Learner. Prueba multiples variantes de nombres de columnas para cada
    campo (ej: DOCUMENTO, NIS, cedula para el documento) y genera identificadores
    automaticos si falta el documento.
    Retorna None si ni el nombre ni el documento estan presentes.
    """
    normalized = {_normalize_key(str(key)): value for key, value in record.items()}
    # Campos del DF14A con sus posibles nombres de columna
    # Se amplian los candidatos para cubrir variantes reales de reportes del SENA.
    name = _first_value(
        normalized,
        "nombres",
        "nombre completo",
        "nombre",
        "aprendiz",
        "aprendices",
        "nombre aprendiz",
        "nombres apellidos",
        "nombres y apellidos",
        "primer nombre",
        "segundo nombre",
        "primer apellido",
        "segundo apellido",
        "nombres del aprendiz",
        "apellidos del aprendiz",
        "apellidos",
        "razon social",
    )
    identification = _first_value(
        normalized,
        "documento",
        "documento de identidad",
        "documento identidad",
        "num documento",
        "no documento",
        "nis",
        "numero documento",
        "n de identificacion",
        "no de identificacion",
        "numero de identificacion",
        "identificacion",
        "identificacion del aprendiz",
        "cedula",
        "cedula de ciudadania",
        "cedula ciudadania",
        "tarjeta de identidad",
        "tarjeta identidad",
        "ti",
        "cc",
        "pasaporte",
    )
    program = _first_value(
        normalized,
        "programa",
        "programa de formacion",
        "programa formacion",
        "nombre del programa",
        "nombre programa",
        "programa de formacion titulada",
        "titulada",
        "codigo programa",
        "nombre programa de formacion",
    )
    group_code = _first_value(
        normalized,
        "ficha",
        "numero de ficha",
        "numero ficha",
        "no ficha",
        "codigo ficha",
        "grupo",
        "grupo de formacion",
        "codigo grupo",
        "ficha de caracterizacion",
        "ficha del aprendiz",
    )
    training_type = _first_value(
        normalized,
        "modalidad",
        "tipo formacion",
        "tipo de formacion",
        "nivel de formacion",
        "nivel formacion",
        "tipo de programa",
        "tipo programa",
        "modalidad de formacion",
        "etapa",
        "etapa de formacion",
        "tipo de acuerdo",
        "formacion titulada",
    )
    certification_status = _first_value(
        normalized,
        "estado aspirante",
        "estado certificacion",
        "estado de certificacion",
        "estado",
        "estado del aprendiz",
        "estado aprendiz",
        "estado certificado",
        "estatus",
        "situacion academica",
        "situacion del aprendiz",
        "resultado",
        "estado de la ficha",
        "estado_aspirante",
    )
    tracking_notes = _first_value(
        normalized,
        "correo electronico",
        "observaciones",
        "novedades",
        "seguimiento",
        "correo",
        "email",
        "notas",
        "comentarios",
        "descripcion",
        "detalle",
        "motivo retiro",
        "motivo de retiro",
    )

    # Si no hay ni nombre ni documento, no hay como identificar al aprendiz
    if not name and not identification:
        return None

    return {
        "identification": _clean_identification(identification) if identification else _auto_identification(record),
        "name": name or "Aprendiz sin nombre",
        "program": program,
        "group_code": group_code,
        "training_type": training_type,
        "certification_status": certification_status,
        "tracking_notes": tracking_notes,
    }


def _first_value(normalized: dict[str, Any], *candidates: str) -> str | None:
    """
    Busca el primer valor no vacio dentro de un diccionario normalizado, probando
    varios nombres candidatos. Ignora None, strings vacios y "nan" (valores nulos de Excel).
    """
    for candidate in candidates:
        value = normalized.get(_normalize_key(candidate))
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value and text_value.lower() != "nan":
            return text_value
    return None


def _normalize_key(value: str) -> str:
    """
    Normaliza una cadena para usarla como clave de busqueda:
    - Elimina tildes (NFKD -> ASCII)
    - Convierte a minusculas
    - Reemplaza guiones/guiones bajos por espacios
    - Colapsa espacios multiples
    """
    normalized = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.lower().replace("_", " ").replace("-", " ").split())


def _auto_identification(record: dict[str, Any]) -> str:
    """
    Genera un identificador unico automatico cuando falta el numero de documento.
    Se basa en un hash SHA1 del contenido completo del registro, con prefijo AUTO-.
    """
    fingerprint = json.dumps(record, ensure_ascii=True, sort_keys=True, default=str)
    return f"AUTO-{hashlib.sha1(fingerprint.encode('utf-8')).hexdigest()[:12]}"


def _clean_identification(value: str) -> str:
    """
    Limpia un numero de documento: si viene en formato TIPO_NUMERO (ej: TI_123456)
    y la segunda parte es puramente numerica, devuelve solo la parte numerica.
    En otros casos devuelve el valor original limpio.
    """
    cleaned = str(value).strip()
    if "_" in cleaned:
        prefix, suffix = cleaned.split("_", 1)
        if suffix.isdigit():
            return suffix
    return cleaned
