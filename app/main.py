# Importamos la clase Path del módulo pathlib para trabajar con rutas de archivos y directorios de manera más conveniente.
from pathlib import Path 
# Importamos el decorador asynccontextmanager del módulo contextlib para crear un contexto asíncrono que se puede usar con la declaración with.
from contextlib import asynccontextmanager 
from datetime import date
from typing import Any

# Importamos varias clases y funciones de FastAPI para crear la aplicación web, manejar dependencias, recibir archivos y formularios, y manejar excepciones HTTP.
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile 
# Importamos la clase FileResponse de fastapi.responses para enviar archivos como respuesta HTTP.
from fastapi.responses import FileResponse
# Importamos la clase StaticFiles de fastapi.staticfiles para servir archivos estáticos desde un directorio específico.
from fastapi.staticfiles import StaticFiles
# Importamos la clase BaseModel de pydantic para definir modelos de datos que se validan automáticamente.
from pydantic import BaseModel
# Importamos la clase Session de sqlalchemy.orm para manejar sesiones de base de datos.
from sqlalchemy.orm import Session

# Importamos varias funciones y clases de nuestro propio módulo app para manejar la base de datos, modelos, servicios y validaciones.
from app.database import SessionLocal, get_db, init_db
from app.models import Act
from app.services.imports import (
    confirm_import,
    get_staged,
    import_preview,
    list_imports,
    stage_file,
)
from app.services.activity import build_activity_heatmap, learners_for_activity_date
from app.services.acts import (
    REVIEW_STATUSES,
    act_options,
    create_act,
    delete_act,
    get_act_detail,
    link_learner_to_act,
    list_acts,
    unlink_learner_from_act,
    update_act,
)
from app.services.learners import (
    get_learner_detail,
    learners_with_pending,
    list_learners,
    renormalize_persisted_learners,
)
from app.services.requirements import (
    REQUIREMENT_STATUSES,
    REQUIREMENT_TYPES,
    list_requirements,
    save_requirement,
)
from app.services.validation import TYPE_LABELS


BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    try:
        with SessionLocal() as session:
            renormalize_persisted_learners(session)
            session.commit()
    except Exception:
        pass
    yield


app = FastAPI(title="Sena Certificacion App", version="0.1.0", lifespan=lifespan) # El parámetro lifespan se establece en la función lifespan definida anteriormente el cual inicializa la base de datos al iniciar la aplicación.
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static") # Montamos un directorio de archivos estáticos en la ruta /static para servir archivos como imágenes, CSS o JavaScript. 

# Definimos varios modelos de datos usando Pydantic para validar y documentar las solicitudes y respuestas de la API.
class RequirementRequest(BaseModel):
    requirement_type: str
    status: str
    observations: str | None = None

# Definimos un modelo de datos para crear un acta, que incluye campos como número, fecha, tipo, archivo original, estado de revisión y observaciones.
class ActCreateRequest(BaseModel):
    number: str
    act_date: date
    act_type: str | None = None
    original_file: str = "Registro manual"
    review_status: str = "pending"
    observations: str | None = None

# Definimos un modelo de datos para actualizar un acta, que permite modificar campos opcionales como número, fecha, tipo, archivo original, estado de revisión y observaciones.
class ActUpdateRequest(BaseModel):
    number: str | None = None
    act_date: date | None = None
    act_type: str | None = None
    original_file: str | None = None
    review_status: str | None = None
    observations: str | None = None

# Definimos un modelo de datos para asociar un aprendiz a un acta, que incluye el ID del aprendiz y observaciones opcionales.
class ActLearnerRequest(BaseModel):
    learner_id: int
    observations: str | None = None

class ConflictResolutionRequest(BaseModel):
    identification: str
    status: str

class ConfirmImportRequest(BaseModel):
    conflict_resolutions: list[ConflictResolutionRequest] = []
    accept_missing_complementaria: bool = False

# Esta ruta devuelve el archivo index.html ubicado en el directorio static cuando se accede a la raíz del sitio web. Se utiliza FileResponse para enviar el archivo como respuesta HTTP.
@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")

# Esta ruta devuelve una lista de tipos de informacion y las categorias simplificadas para la carga de archivos.
@app.get("/api/information-types")
async def information_types() -> dict[str, Any]:
    # Las tres fuentes principales determinan por si mismas el tipo de
    # procesamiento, por eso ya no hay selectores de subtipos redundantes. La
    # carga de requisitos se conserva como opcion secundaria y los documentos de
    # referencia y el CSV alternativo dejan de ofrecerse, aunque sus tipos
    # internos siguen disponibles para datos historicos y compatibilidad.
    categories = [
        {
            "id": "actas_oficiales",
            "name": "Actas oficiales",
            "description": "Documentos PDF o DOCX con la información oficial del acta y sus aprendices",
            "types": ["acta"],
            "formats": ["PDF", "DOCX"],
        },
        {
            "id": "df14a",
            "name": "DF14A",
            "description": "Archivo institucional con la información de los aprendices",
            "types": ["df14a"],
            "formats": ["XML", "XLSX", "XLS", "CSV"],
        },
        {
            "id": "actas_2026",
            "name": "ACTAS 2026 / seguimiento",
            "description": "Excel con las hojas de seguimiento y los datos de los indicadores",
            "types": ["actas_completo"],
            "formats": ["XLSX", "XLS"],
        },
        {
            "id": "requisitos_aprendices",
            "name": "Requisitos de aprendices",
            "description": "Carga secundaria: matriz de requisitos por aprendiz",
            "types": ["requisitos"],
            "formats": ["XLSX", "XLS", "CSV"],
            "secondary": True,
        },
    ]
    return {
        "items": [{"value": value, "label": label} for value, label in TYPE_LABELS.items()],
        "categories": categories,
    }

# Esta ruta permite subir un archivo y validarlo según el tipo de información especificado. Se recibe el tipo de información como un formulario y el archivo como un archivo cargado. Se llama a la función stage_file para procesar el archivo y se devuelve un diccionario con los resultados de la validación y un ID de validación.
@app.post("/api/files/validate")
async def validate_upload(
    information_type: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    content = await file.read()
    staged = stage_file(file.filename or "archivo", content, information_type)
    response = staged.result.as_dict()
    response["validation_id"] = staged.validation_id
    return response

# Esta ruta devuelve una vista previa de la importación de un archivo previamente validado. Se recibe un ID de validación como parámetro y se busca el archivo en estado "staged". Si el archivo no está disponible o tiene errores, se devuelve un error HTTP. Si todo está bien, se llama a la función import_preview para preparar la importación y se devuelve un diccionario con los datos a importar.
@app.get("/api/imports/{validation_id}/preview")
async def import_preview_endpoint(
    validation_id: str,
    session: Session = Depends(get_db),
) -> dict:
    staged = get_staged(validation_id)
    if staged is None:
        raise HTTPException(status_code=404, detail="La validacion ya no esta disponible.")
    if staged.result.status == "error":
        raise HTTPException(status_code=400, detail="El archivo tiene errores que impiden la importacion.")
    try:
        return import_preview(staged, session)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"No fue posible preparar la importacion: {error}") from error

# Esta ruta confirma la importación de un archivo previamente validado y preparado. Se recibe un ID de validación como parámetro y se llama a la función confirm_import para realizar la importación en la base de datos. Si ocurre algún error, se devuelve un error HTTP con el mensaje correspondiente.
@app.post("/api/imports/{validation_id}/confirm")
async def confirm_import_endpoint(
    validation_id: str,
    request: ConfirmImportRequest | None = None,
    session: Session = Depends(get_db),
) -> dict:
    try:
        resolutions = (
            [item.model_dump() for item in request.conflict_resolutions]
            if request is not None
            else None
        )
        accept_missing_complementaria = (
            request.accept_missing_complementaria if request is not None else False
        )
        return confirm_import(
            validation_id,
            session,
            resolutions,
            accept_missing_complementaria=accept_missing_complementaria,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

# Esta ruta devuelve el historial de importaciones realizadas en la aplicación. Se llama a la función list_imports para obtener una lista de importaciones desde la base de datos y se devuelve un diccionario con los elementos.
@app.get("/api/imports/history")
async def import_history(session: Session = Depends(get_db)) -> dict:
    return {"items": list_imports(session)}

# Esta ruta devuelve una lista de aprendices según los parámetros de búsqueda, estado, página y tamaño de página especificados. Se llama a la función list_learners para obtener los aprendices desde la base de datos y se devuelve un diccionario con los elementos.
@app.get("/api/learners")
async def learners(
    search: str = Query(default="", max_length=100),
    status: str = Query(default="", max_length=100),
    missing_requirement: list[str] = Query(default=[]),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> dict:
    return list_learners(
        session,
        search=search,
        status=status,
        missing_requirement=missing_requirement,
        page=page,
        page_size=page_size,
    )

# Esta ruta devuelve una lista de aprendices que tienen requisitos pendientes. Se llama a la función learners_with_pending para obtener los aprendices desde la base de datos y se devuelve un diccionario con los elementos.
@app.get("/api/learners/with-pending-requirements")
async def learners_with_pending_requirements(session: Session = Depends(get_db)) -> dict:
    return {"items": learners_with_pending(session)}


@app.get("/api/learners/{learner_id}/requirements")
async def learner_requirements(learner_id: int, session: Session = Depends(get_db)) -> dict:
    items = list_requirements(session, learner_id)
    if items is None:
        raise HTTPException(status_code=404, detail="Aprendiz no encontrado.")
    return {
        "items": items,
        "requirement_types": REQUIREMENT_TYPES,
        "statuses": sorted(REQUIREMENT_STATUSES),
    }


@app.post("/api/learners/{learner_id}/requirements", status_code=201)
async def create_learner_requirement(
    learner_id: int,
    request: RequirementRequest,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return save_requirement(session, learner_id, request.requirement_type, request.status, request.observations)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.patch("/api/learners/{learner_id}/requirements/{requirement_id}")
async def update_learner_requirement(
    learner_id: int,
    requirement_id: int,
    request: RequirementRequest,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return save_requirement(
            session,
            learner_id,
            request.requirement_type,
            request.status,
            request.observations,
            requirement_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/learners/{learner_id}")
async def learner_detail(learner_id: int, session: Session = Depends(get_db)) -> dict:
    detail = get_learner_detail(session, learner_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Aprendiz no encontrado.")
    return detail


@app.get("/api/acts")
async def acts(
    search: str = Query(default="", max_length=200),
    review_status: str | None = Query(default=None, max_length=50),
    number: str = Query(default="", max_length=100),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    try:
        return {
            "items": list_acts(
                session,
                search,
                review_status,
                number=number,
                date_from=date_from,
                date_to=date_to,
            )
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/acts/options")
async def acts_options() -> dict:
    return act_options()


@app.get("/api/acts/{act_id}")
async def act_detail_endpoint(act_id: int, session: Session = Depends(get_db)) -> dict:
    result = get_act_detail(session, act_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Acta no encontrada.")
    return result


@app.post("/api/acts", status_code=201)
async def create_act_endpoint(
    request: ActCreateRequest,
    session: Session = Depends(get_db),
) -> dict:
    if not request.number.strip() or not request.original_file.strip():
        raise HTTPException(status_code=422, detail="Número y archivo original son obligatorios.")
    try:
        return create_act(
            session,
            request.number,
            request.act_date,
            request.act_type,
            request.original_file,
            request.review_status,
            request.observations,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.patch("/api/acts/{act_id}")
async def update_act_endpoint(
    act_id: int,
    request: ActUpdateRequest,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return update_act(session, act_id, request.model_dump(exclude_unset=True))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/acts/{act_id}", status_code=204)
async def delete_act_endpoint(act_id: int, session: Session = Depends(get_db)) -> None:
    try:
        delete_act(session, act_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/acts/{act_id}/learners", status_code=201)
async def link_act_learner(
    act_id: int,
    request: ActLearnerRequest,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return link_learner_to_act(session, act_id, request.learner_id, request.observations)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/acts/{act_id}/learners/{learner_id}", status_code=204)
async def unlink_act_learner(
    act_id: int,
    learner_id: int,
    session: Session = Depends(get_db),
) -> None:
    if session.get(Act, act_id) is None:
        raise HTTPException(status_code=404, detail="Acta no encontrada.")
    try:
        unlink_learner_from_act(session, act_id, learner_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/indicadores")
async def indicadores_endpoint(session: Session = Depends(get_db)) -> dict:
    from app.services.indicadores import compute_indicadores_2026
    return compute_indicadores_2026(session)

@app.get("/api/activity/heatmap")
async def activity_heatmap(
    year: int = 2026,
    session: Session = Depends(get_db),
) -> dict:
    return build_activity_heatmap(session, year=year)


@app.get("/api/activity/day/{day}")
async def activity_day(
    day: date,
    session: Session = Depends(get_db),
) -> dict:
    return learners_for_activity_date(session, day)

