# Importamos la clase Path del módulo pathlib para trabajar con rutas de archivos y directorios de manera más conveniente.
from pathlib import Path 
# Importamos el decorador asynccontextmanager del módulo contextlib para crear un contexto asíncrono que se puede usar con la declaración with.
import asyncio
from contextlib import asynccontextmanager 
from datetime import date
from typing import Any

# Importamos varias clases y funciones de FastAPI para crear la aplicación web, manejar dependencias, recibir archivos y formularios, y manejar excepciones HTTP.
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile 
# Importamos la clase FileResponse de fastapi.responses para enviar archivos como respuesta HTTP.
from fastapi.responses import FileResponse, Response
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
    from app.services.sheets_sync import run_background_worker

    worker_task = asyncio.create_task(run_background_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


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
    source: str | None = None

class RequirementConflictResolutionRequest(BaseModel):
    identification: str
    requirement_type: str
    # ``status`` es el nombre historico. ``chosen_status`` es el nombre del
    # contrato nuevo; se acepta cualquiera de los dos.
    status: str | None = None
    chosen_status: str | None = None
    source: str | None = None
    conflict_fingerprint: str | None = None

class ConfirmImportRequest(BaseModel):
    conflict_resolutions: list[ConflictResolutionRequest] = []
    requirement_conflict_resolutions: list[RequirementConflictResolutionRequest] = []
    accept_missing_complementaria: bool = False
    sheets_manual_cleanup_acknowledged: bool = False

class SheetSyncCreateRequest(BaseModel):
    url: str
    information_type: str = "actas_completo"
    interval_seconds: int = 60
    enabled: bool = True

class SheetSyncPatchRequest(BaseModel):
    enabled: bool

class SheetSyncPreviewRequest(BaseModel):
    url: str | None = None
    information_type: str = "actas_completo"
    interval_seconds: int = 60

class SheetSyncConfirmRequest(BaseModel):
    validation_id: str
    conflict_resolutions: list[ConflictResolutionRequest] = []
    requirement_conflict_resolutions: list[RequirementConflictResolutionRequest] = []
    accept_missing_complementaria: bool = False
    sheets_manual_cleanup_acknowledged: bool = False

class SheetSyncResolveRequest(BaseModel):
    conflict_resolutions: list[ConflictResolutionRequest] = []
    requirement_conflict_resolutions: list[RequirementConflictResolutionRequest] = []
    accept_missing_complementaria: bool = False
    sheets_manual_cleanup_acknowledged: bool = False

class SheetSyncNotifiedRequest(BaseModel):
    fingerprint: str | None = None

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
        requirement_resolutions = (
            [
                item.model_dump()
                for item in request.requirement_conflict_resolutions
            ]
            if request is not None
            else None
        )
        accept_missing_complementaria = (
            request.accept_missing_complementaria if request is not None else False
        )
        sheets_manual_cleanup_acknowledged = (
            request.sheets_manual_cleanup_acknowledged if request is not None else False
        )
        return confirm_import(
            validation_id,
            session,
            resolutions,
            accept_missing_complementaria=accept_missing_complementaria,
            sheets_manual_cleanup_acknowledged=sheets_manual_cleanup_acknowledged,
            requirement_conflict_resolutions=requirement_resolutions,
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
    reason: list[str] = Query(default=[]),
    act_number: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> dict:
    return list_learners(
        session,
        search=search,
        status=status,
        missing_requirement=missing_requirement,
        reason=reason,
        act_number=act_number,
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


@app.get("/api/indicadores/certificados-por-mes")
async def certificados_por_mes_endpoint(session: Session = Depends(get_db)) -> dict:
    """Certificados por MES DE CERTIFICACION del consolidado vigente.

    No usa ``Learner.certification_month`` (padron local) ni la fecha de
    importacion. La UI debe etiquetarlo como consolidado ACTAS 2026.
    """
    from app.services.indicadores import compute_certificados_por_mes
    return compute_certificados_por_mes(session)


@app.get("/api/informes/consolidado")
async def informes_consolidado_endpoint(
    year: int | None = Query(default=None, ge=2000, le=2100),
    session: Session = Depends(get_db),
) -> dict:
    """Dataset consolidado de informe v1 desde el lote vigente de ACTAS 2026.

    Reutiliza el motor de indicadores (B1-B5). No escribe en BD. Si no hay
    lote vigente responde de forma segura con totales vacios/null.
    """
    from app.services.informes import consolidate_report_dataset
    return consolidate_report_dataset(session, year=year)


@app.get("/api/informes/consolidado/resumen")
async def informes_consolidado_resumen_endpoint(
    year: int | None = Query(default=None, ge=2000, le=2100),
    session: Session = Depends(get_db),
) -> dict:
    """Metadatos + KPIs del dataset consolidado (version liviana)."""
    from app.services.informes import consolidate_report_dataset
    data = consolidate_report_dataset(session, year=year)
    return {
        "generated_at": data["generated_at"],
        "periodo": data["periodo"],
        "periodo_inicio": data["periodo_inicio"],
        "periodo_fin": data["periodo_fin"],
        "source": data["source"],
        "import_id": data["import_id"],
        "file_name": data["file_name"],
        "advertencias": data["advertencias"],
        "datos_suficientes": data["datos_suficientes"],
        "resumen_ejecutivo": data["resumen_ejecutivo"],
    }


@app.get("/api/informes/export")
async def informes_export_endpoint(
    report_type: str = Query(default="consolidado", alias="type"),
    format: str = Query(default="xlsx", pattern="^(pdf|xlsx|csv|docx)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    scope: str = Query(default="consolidado", pattern="^(consolidado|filtrado)$"),
    detail: str = Query(default="completo", pattern="^(completo|ejecutivo)$"),
    search: str = Query(default=""),
    status: str = Query(default=""),
    session: Session = Depends(get_db),
) -> Response:
    """Exporta un informe estructurado en PDF, XLSX o CSV."""
    from app.services.informes import export_report_csv, export_report_pdf, export_report_xlsx
    try:
        if format == "csv":
            content = export_report_csv(
                session,
                report_type=report_type,
                year=year,
                scope=scope,
                detail=detail,
                search=search,
                status=status,
            )
            media_type = "text/csv; charset=utf-8"
            filename = f"informe_{report_type}.csv"
        elif format == "pdf":
            content = export_report_pdf(
                session,
                report_type=report_type,
                year=year,
                scope=scope,
                detail=detail,
                search=search,
                status=status,
            )
            media_type = "application/pdf"
            filename = f"informe_{report_type}.pdf"
        elif format == "docx":
            from app.services.report_word import generate_report_docx
            content = generate_report_docx(year=year, quarter=2, cutoff=None)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"informe_gestion_{year or date.today().year}_T2.docx"
        else:
            content = export_report_xlsx(
                session,
                report_type=report_type,
                year=year,
                scope=scope,
                detail=detail,
                search=search,
                status=status,
            )
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = (
                "informe_consolidado.xlsx"
                if report_type in {"consolidado", "general"}
                else f"informe_{report_type}.xlsx"
            )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/informes/formats")
async def informes_formats_endpoint(
    report_type: str = Query(default="consolidado", alias="type"),
) -> dict:
    from app.services.informes import REPORT_TYPES, available_report_formats
    try:
        formats = available_report_formats(report_type)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "type": report_type,
        "name": REPORT_TYPES[report_type],
        "formats": formats,
    }


@app.get("/api/informes/catalog")
async def informes_catalog_endpoint() -> list[dict]:
    from app.services.informes import report_catalog
    return report_catalog()


@app.get("/api/informes/word")
async def informes_word_endpoint(
    year: int | None = Query(default=None, ge=2000, le=2100),
    quarter: int = Query(default=2, ge=1, le=4),
    cutoff: date | None = Query(default=None),
    session: Session = Depends(get_db),
) -> Response:
    from app.services.report_word import generate_report_docx
    try:
        from app.services.informes import consolidate_report_dataset
        dataset = consolidate_report_dataset(session, year=year)
        summary = {
            "Actas registradas": dataset.get("resumen_ejecutivo", {}).get("actas", "N/D"),
            "Aprendices vinculados": dataset.get("resumen_ejecutivo", {}).get("aprendices", "N/D"),
            "Periodo": dataset.get("periodo", "N/D"),
        }
        content = generate_report_docx(year=year, quarter=quarter, cutoff=cutoff, summary=summary)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    filename = f"informe_gestion_{year or date.today().year}_T{quarter}.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ---------------------------------------------------------------------------
# Sincronizacion automatica desde Google Sheets
# ---------------------------------------------------------------------------
@app.get("/api/sheets/sync")
async def sheets_sync_status_endpoint(session: Session = Depends(get_db)) -> dict:
    from app.services.sheets_sync import get_config, config_to_status

    return config_to_status(get_config(session))


@app.get("/api/sheets/sync/pending-conflicts")
async def sheets_sync_pending_conflicts_endpoint(
    session: Session = Depends(get_db),
) -> dict:
    """Lote detenido por conflictos CERTIFICADOS/PENDIENTES, listo para resolver."""
    from app.services.sheets_sync import pending_conflicts_payload

    return pending_conflicts_payload(session)


@app.post("/api/sheets/sync/resolve")
async def sheets_sync_resolve_endpoint(
    request: SheetSyncResolveRequest,
    session: Session = Depends(get_db),
) -> dict:
    """Resuelve el lote pendiente y completa la importación automática."""
    from app.services.sheets_sync import resolve_pending

    resolutions = [item.model_dump() for item in request.conflict_resolutions]
    requirement_resolutions = [
        item.model_dump() for item in request.requirement_conflict_resolutions
    ]
    try:
        return resolve_pending(
            session,
            resolutions,
            accept_missing_complementaria=request.accept_missing_complementaria,
            sheets_manual_cleanup_acknowledged=request.sheets_manual_cleanup_acknowledged,
            requirement_conflict_resolutions=requirement_resolutions,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/sheets/sync/notified")
async def sheets_sync_notified_endpoint(
    request: SheetSyncNotifiedRequest | None = None,
    session: Session = Depends(get_db),
) -> dict:
    """Marca que el toast nativo ya se mostró para evitar notificaciones repetidas."""
    from app.services.sheets_sync import mark_notified

    fingerprint = request.fingerprint if request is not None else None
    return mark_notified(session, fingerprint)


@app.post("/api/sheets/sync")
async def sheets_sync_create_endpoint(
    request: SheetSyncCreateRequest,
    session: Session = Depends(get_db),
) -> dict:
    from app.services.sheets_sync import save_config, config_to_status

    try:
        config = save_config(
            session,
            request.url,
            request.information_type,
            request.interval_seconds,
            request.enabled,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return config_to_status(config)


@app.patch("/api/sheets/sync")
async def sheets_sync_patch_endpoint(
    request: SheetSyncPatchRequest,
    session: Session = Depends(get_db),
) -> dict:
    from app.services.sheets_sync import update_enabled, config_to_status

    config = update_enabled(session, request.enabled)
    if config is None:
        raise HTTPException(status_code=404, detail="No hay configuracion de sincronizacion.")
    return config_to_status(config)


@app.post("/api/sheets/sync/run")
async def sheets_sync_run_endpoint(session: Session = Depends(get_db)) -> dict:
    from app.services.sheets_sync import run_sync, get_config, config_to_status

    config = get_config(session)
    if config is None:
        raise HTTPException(status_code=404, detail="No hay configuracion de sincronizacion.")
    try:
        config = run_sync(session)
    except Exception as error:  # noqa: BLE001
        try:
            session.rollback()
        except Exception:
            pass
        config = get_config(session)
        if config is None:
            raise HTTPException(status_code=500, detail=str(error)) from error
        if config.last_status != "error":
            config.last_status = "error"
            config.last_message = str(error)
            try:
                session.commit()
            except Exception:
                session.rollback()
    return config_to_status(config)


@app.post("/api/sheets/sync/preview")
async def sheets_sync_preview_endpoint(
    request: SheetSyncPreviewRequest,
    session: Session = Depends(get_db),
) -> dict:
    from app.services.sheets_sync import prepare_sync

    try:
        return prepare_sync(
            session,
            request.url,
            request.information_type,
            request.interval_seconds,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/sheets/sync/confirm")
async def sheets_sync_confirm_endpoint(
    request: SheetSyncConfirmRequest,
    session: Session = Depends(get_db),
) -> dict:
    from app.services.sheets_sync import confirm_sync

    resolutions = [item.model_dump() for item in request.conflict_resolutions]
    requirement_resolutions = [
        item.model_dump() for item in request.requirement_conflict_resolutions
    ]
    try:
        return confirm_sync(
            session,
            request.validation_id,
            resolutions,
            accept_missing_complementaria=request.accept_missing_complementaria,
            sheets_manual_cleanup_acknowledged=request.sheets_manual_cleanup_acknowledged,
            requirement_conflict_resolutions=requirement_resolutions,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/sheets/sync")
async def sheets_sync_delete_endpoint(session: Session = Depends(get_db)) -> dict:
    from app.services.sheets_sync import delete_config, config_to_status

    delete_config(session)
    return config_to_status(None)


# ---------------------------------------------------------------------------
# Parche de actividad para el heatmap de la UI v2
# ---------------------------------------------------------------------------
# ``build_activity_heatmap`` agrega actividad real desde
# ``RequirementStatusHistory`` (cambios de requisitos) e ``ImportHistory``
# (importaciones confirmadas). ``learners_for_activity_date`` devuelve el
# detalle de aprendices e importaciones de una celda concreta.
# El frontend lo consume desde ``app/static/ui-enhancements.js``.
@app.get("/api/activity/heatmap")
async def activity_heatmap(
    year: int = Query(default=2026, ge=2000, le=2100),
    session: Session = Depends(get_db),
) -> dict:
    return build_activity_heatmap(session, year=year)


@app.get("/api/activity/day/{day}")
async def activity_day(
    day: date,
    session: Session = Depends(get_db),
) -> dict:
    return learners_for_activity_date(session, day)
