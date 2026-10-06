from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.services.imports import (
    confirm_import,
    get_staged,
    import_preview,
    list_imports,
    stage_file,
)
from app.services.learners import list_learners
from app.services.validation import TYPE_LABELS


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Sena Certificacion App", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
init_db()


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