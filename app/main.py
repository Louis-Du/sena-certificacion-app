"""
Punto de entrada principal de la API FastAPI para Sena Certificacion App.
Define la instancia FastAPI, sirve los archivos estaticos del frontend y registra
todos los endpoints REST organizados por dominio:
  1. Informacion y validacion de archivos
  2. Importaciones (previsualizacion, confirmacion, historial)
  3. Aprendices (listado, filtros, detalle completo con requisitos/actas/historial)
  4. Actas (CRUD, vinculacion manual con aprendices, opciones de catalogo)
"""

from datetime import date  # Tipo de fecha para filtros y campos de actas
from pathlib import Path  # Manejo de rutas del sistema de archivos

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile  # Decoradores y tipos FastAPI
from fastapi.responses import FileResponse  # Respuesta para servir el HTML del frontend
from fastapi.staticfiles import StaticFiles  # Montaje de carpeta de archivos estaticos
from pydantic import BaseModel  # Esquemas de validacion para cuerpos de peticion JSON
from sqlalchemy.orm import Session  # Sesion SQLAlchemy para operaciones BD

from app.database import get_db, init_db  # Dependencia de sesion BD e inicializacion de tablas
from app.services.acts import (  # Servicios del dominio Actas
    create_act,
    delete_act,
    get_act_detail,
    link_learner_to_act,
    list_act_options,
    list_acts,
    unlink_learner_from_act,
    update_act,
)
from app.services.imports import (  # Servicios del dominio Importaciones
    confirm_import,
    get_staged,
    import_preview,
    list_imports,
    stage_file,
)
from app.services.learners import get_learner_detail, list_learner_filters, list_learners  # Servicios Aprendices
from app.services.validation import TYPE_LABELS  # Etiquetas de tipos de informacion para UI


# Directorio base de la aplicacion (carpeta app/)
BASE_DIR = Path(__file__).resolve().parent

# Instancia principal de la aplicacion FastAPI
app = FastAPI(title="Sena Certificacion App", version="0.1.0")
# Sirve el frontend (HTML/CSS/JS) desde /static
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# Inicializa las tablas de la base de datos y ejecuta migraciones SQLite al arrancar
init_db()


# ================== ESQUEMAS PYDANTIC ==================

class ActUpdateRequest(BaseModel):
    """
    Esquema para el cuerpo PATCH de actualizacion de un acta.
    Todos los campos son opcionales; solo los campos proporcionados se actualizaran.
    """
    number: str | None = None
    act_date: date | None = None
    act_type: str | None = None
    review_status: str | None = None
    observations: str | None = None


class ActLearnerLinkRequest(BaseModel):
    """
    Esquema para vincular manualmente un aprendiz a un acta.
    Requiere el ID del aprendiz; las observaciones son opcionales.
    """
    learner_id: int
    observations: str | None = None


# ================== ENDPOINTS PUBLICOS / FRONTEND ==================

@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """
    Sirve la pagina principal del frontend (single page application).
    Excluido de la documentacion OpenAPI.
    """
    return FileResponse(BASE_DIR / "static" / "index.html")


# ================== ENDPOINTS: INFORMACION Y VALIDACION ==================

@app.get("/api/information-types")
async def information_types() -> dict[str, list[dict[str, str]]]:
    """
    Devuelve el catalogo de tipos de informacion importables con su etiqueta legible.
    Ej: df14a -> DF14A, acta -> Acta de certificacion, etc.
    """
    return {"items": [{"value": value, "label": label} for value, label in TYPE_LABELS.items()]}


@app.post("/api/files/validate")
async def validate_upload(
    information_type: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """
    Valida un archivo subido sin guardarlo aun en BD.
    Recibe multipart/form-data con el tipo de informacion y el archivo.
    Retorna resultado de validacion y un validation_id temporal para la confirmacion posterior.
    """
    content = await file.read()
    staged = stage_file(file.filename or "archivo", content, information_type)
    response = staged.result.as_dict()
    response["validation_id"] = staged.validation_id
    return response


# ================== ENDPOINTS: IMPORTACIONES ==================

@app.get("/api/imports/{validation_id}/preview")
async def import_preview_endpoint(
    validation_id: str,
    session: Session = Depends(get_db),
) -> dict:
    """
    Previsualiza los resultados de una importacion pendiente (por validation_id).
    Muestra: cantidad de registros nuevos vs actualizados, warnings y estado.
    Lanza 404 si la validacion ya expiro y 400 si el archivo tenia errores fatales.
    """
    staged = get_staged(validation_id)
    if staged is None:
        raise HTTPException(status_code=404, detail="La validacion ya no esta disponible.")
    if staged.result.status == "error":
        raise HTTPException(status_code=400, detail="El archivo tiene errores que impiden la importacion.")
    try:
        return import_preview(staged, session)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"No fue posible preparar la importacion: {error}") from error


@app.post("/api/imports/{validation_id}/confirm")
async def confirm_import_endpoint(
    validation_id: str,
    session: Session = Depends(get_db),
) -> dict:
    """
    Confirma y ejecuta la importacion asociada a un validation_id.
    Inserta/actualiza ImportedRecord, crea ImportHistory y, si es DF14A, sincroniza Learner.
    Lanza 404 si el validation_id no existe o 400 si el estado es invalido.
    """
    try:
        return confirm_import(validation_id, session)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/imports/history")
async def import_history(session: Session = Depends(get_db)) -> dict:
    """
    Devuelve el historial completo de importaciones confirmadas, ordenado por
    fecha descendente (mas reciente primero).
    """
    return {"items": list_imports(session)}


# ================== ENDPOINTS: APRENDICES ==================

@app.get("/api/learners")
async def learners(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status: str | None = Query(default=None, max_length=100),
    program: str | None = Query(default=None, max_length=200),
    group_code: str | None = Query(default=None, max_length=50),
    training_type: str | None = Query(default=None, max_length=100),
    session: Session = Depends(get_db),
) -> dict:
    """
    Listado paginado de aprendices.
    - search: busqueda textual por nombre, documento, ficha o programa
    - page/page_size: paginacion (min 1, max 100 por pagina)
    - status / program / group_code / training_type: filtros especificos parciales
    Si la tabla learners esta vacia, realiza una migracion desde ImportedRecord DF14A.
    """
    return list_learners(
        session,
        search=search,
        page=page,
        page_size=page_size,
        status=status,
        program=program,
        group_code=group_code,
        training_type=training_type,
    )


@app.get("/api/learners/filters")
async def learner_filters(session: Session = Depends(get_db)) -> dict:
    """
    Devuelve los valores unicos existentes para cada filtro del listado de aprendices.
    Sirve para poblar los selectores/desplegables de la UI:
    statuses, programs, group_codes (fichas), training_types.
    """
    return list_learner_filters(session)


@app.get("/api/learners/{learner_id}")
async def learner_detail(learner_id: int, session: Session = Depends(get_db)) -> dict:
    """
    Obtiene el detalle completo de un aprendiz por ID.
    Secciones incluidas:
      - basic_info: datos personales, programa, ficha, estado, fechas
      - requirements: 5 requisitos con estados (estructura provisional)
      - acts: actas asociadas al aprendiz
      - history: historial de importaciones/actualizaciones del registro
      - dates: fechas de inicio y terminacion
    Retorna 404 si el aprendiz no existe.
    """
    detail = get_learner_detail(session, learner_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Aprendiz no encontrado.")
    return detail


# ================== ENDPOINTS: ACTAS ==================

@app.get("/api/acts")
async def acts_list(
    search: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    review_status: str | None = Query(default=None, max_length=50),
    act_type: str | None = Query(default=None, max_length=100),
    act_date_from: date | None = Query(default=None),
    act_date_to: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    """
    Listado paginado de actas de certificacion/seguimiento.
    - search: busca por numero, nombre de archivo u observaciones
    - review_status: filtra por estado (pending/reviewed/approved/rejected)
    - act_type: tipo de acta (certificacion, seguimiento, comite, otro)
    - act_date_from / act_date_to: rango de fechas inclusive
    Orden: fecha del acta descendente (NULLS al final).
    """
    return list_acts(
        session,
        search=search,
        page=page,
        page_size=page_size,
        review_status=review_status,
        act_type=act_type,
        act_date_from=act_date_from,
        act_date_to=act_date_to,
    )


@app.get("/api/acts/options")
async def act_options() -> dict:
    """
    Devuelve los catalogos de opciones para poblar los selectores del modulo de actas:
    estados de revision y tipos de acta, cada uno con value y label.
    """
    return list_act_options()


@app.get("/api/acts/{act_id}")
async def act_detail(act_id: int, session: Session = Depends(get_db)) -> dict:
    """
    Obtiene el detalle completo de un acta incluyendo la lista de aprendices
    actualmente vinculados a traves de la tabla puente ActLearner.
    Retorna 404 si el acta no existe.
    """
    detail = get_act_detail(session, act_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Acta no encontrada.")
    return detail


@app.post("/api/acts")
async def acts_create(
    number: str | None = Form(default=None, max_length=100),
    act_date: date | None = Form(default=None),
    act_type: str | None = Form(default=None, max_length=100),
    review_status: str = Form(default="pending", max_length=50),
    observations: str | None = Form(default=None),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    """
    Crea un nuevo registro de acta y sube el archivo asociado.
    Endpoint multipart/form-data. El archivo se almacena fisicamente en
    uploads/acts/ con un nombre UUID unico (evita colisiones).
    Campos:
      - number: numero de acta (opcional, se podria extraer en el futuro)
      - act_date: fecha del acta (YYYY-MM-DD)
      - act_type: tipo de acta del catalogo
      - review_status: estado inicial (default: pending)
      - observations: notas libres
      - file: archivo PDF/DOCX del acta (requerido)
    Retorna el acta creada. Commit transaccion si todo es OK; rollback ante error.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo esta vacio.")
    try:
        result = create_act(
            session,
            number=number,
            act_date=act_date,
            act_type=act_type,
            original_file_name=file.filename or "acta",
            file_content=content,
            review_status=review_status,
            observations=observations,
        )
        session.commit()
        return result
    except Exception as error:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"No fue posible cargar el acta: {error}") from error


@app.patch("/api/acts/{act_id}")
async def acts_update(
    act_id: int,
    payload: ActUpdateRequest,
    session: Session = Depends(get_db),
) -> dict:
    """
    Actualiza los metadatos de un acta existente (PATCH parcial).
    Solo actualiza los campos no nulos del cuerpo JSON. No modifica el archivo.
    Retorna 404 si el acta no existe.
    """
    result = update_act(
        session,
        act_id,
        number=payload.number,
        act_date=payload.act_date,
        act_type=payload.act_type,
        review_status=payload.review_status,
        observations=payload.observations,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Acta no encontrada.")
    session.commit()
    return result


@app.delete("/api/acts/{act_id}")
async def acts_delete(act_id: int, session: Session = Depends(get_db)) -> dict:
    """
    Elimina un acta y su archivo fisico asociado.
    La eliminacion en cascada por FK se encarga de borrar los vinculos ActLearner.
    Retorna 404 si no existe el acta.
    """
    deleted = delete_act(session, act_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Acta no encontrada.")
    session.commit()
    return {"ok": True, "message": "Acta eliminada correctamente."}


@app.post("/api/acts/{act_id}/learners")
async def acts_link_learner(
    act_id: int,
    payload: ActLearnerLinkRequest,
    session: Session = Depends(get_db),
) -> dict:
    """
    Vincula manualmente un aprendiz existente a un acta.
    Si el vinculo ya existia, actualiza sus observaciones.
    Retorna 404 si el acta o el aprendiz no existen.
    """
    result = link_learner_to_act(
        session,
        act_id,
        payload.learner_id,
        observations=payload.observations,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Acta o aprendiz no encontrado.")
    session.commit()
    return result


@app.delete("/api/acts/{act_id}/learners/{learner_id}")
async def acts_unlink_learner(
    act_id: int,
    learner_id: int,
    session: Session = Depends(get_db),
) -> dict:
    """
    Desvincula un aprendiz de un acta (elimina el registro ActLearner).
    Retorna 404 si el vinculo no existia.
    """
    removed = unlink_learner_from_act(session, act_id, learner_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Vinculo no encontrado.")
    session.commit()
    return {"ok": True, "message": "Aprendiz desvinculado del acta."}
