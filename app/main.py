from pathlib import Path
from datetime import date

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import Act
from app.services.imports import (
    confirm_import,
    get_staged,
    import_preview,
    list_imports,
    stage_file,
)
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
from app.services.learners import get_learner_detail, list_learners
from app.services.requirements import (
    REQUIREMENT_STATUSES,
    REQUIREMENT_TYPES,
    list_requirements,
    pending_learners,
    save_requirement,
)
from app.services.validation import TYPE_LABELS


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Sena Certificacion App", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
init_db()


class RequirementRequest(BaseModel):
    requirement_type: str
    status: str
    observations: str | None = None


class ActCreateRequest(BaseModel):
    number: str
    act_date: date
    act_type: str | None = None
    original_file: str = "Registro manual"
    review_status: str = "pending"
    observations: str | None = None


class ActUpdateRequest(BaseModel):
    number: str | None = None
    act_date: date | None = None
    act_type: str | None = None
    original_file: str | None = None
    review_status: str | None = None
    observations: str | None = None


class ActLearnerRequest(BaseModel):
    learner_id: int
    observations: str | None = None


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/information-types")
async def information_types() -> dict[str, list[dict[str, str]]]:
    return {"items": [{"value": value, "label": label} for value, label in TYPE_LABELS.items()]}


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


@app.post("/api/imports/{validation_id}/confirm")
async def confirm_import_endpoint(
    validation_id: str,
    session: Session = Depends(get_db),
) -> dict:
    try:
        return confirm_import(validation_id, session)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/imports/history")
async def import_history(session: Session = Depends(get_db)) -> dict:
    return {"items": list_imports(session)}


@app.get("/api/learners")
async def learners(
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db),
) -> dict:
    return list_learners(session, search=search, page=page, page_size=page_size)


@app.get("/api/learners/with-pending-requirements")
async def learners_with_pending_requirements(session: Session = Depends(get_db)) -> dict:
    return {"items": pending_learners(session)}


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
    session: Session = Depends(get_db),
) -> dict:
    try:
        return {"items": list_acts(session, search, review_status)}
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