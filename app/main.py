from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.services.validation import TYPE_LABELS, validate_file


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Sena Certificacion App", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


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
    result = validate_file(file.filename or "archivo", content, information_type)
    return result.as_dict()