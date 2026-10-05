# Sena Certificacion App

Primer vertical del sistema de informacion para cargar y validar archivos usados en el proceso de certificacion.

## Estado actual

- FastAPI sirve la interfaz HTML/CSS/JavaScript desde el mismo proceso.
- `POST /api/files/validate` valida un archivo en memoria y no modifica la base de datos.
- Se admiten `DF14A`, `Acta de certificacion`, `Requisitos / pendientes` y `Otro archivo`.
- La validacion reconoce `XLSX`, `XLS`, `CSV`, `PDF` y `DOCX` segun el tipo seleccionado.
- El analisis de filas y encabezados se realiza para archivos tabulares cuando el formato puede abrirse.

## Ejecutar en desarrollo

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Luego abre `http://127.0.0.1:8000`.

## Pruebas

```powershell
pytest
```

La persistencia en SQLite, las reglas definitivas de negocio y la extraccion de datos de actas quedan para cuando esten disponibles los archivos reales y sus estructuras.
