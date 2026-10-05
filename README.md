# Sena Certificacion App

Primer vertical del sistema de informacion para cargar y validar archivos usados en el proceso de certificacion.

## Estado actual

- FastAPI sirve la interfaz HTML/CSS/JavaScript desde el mismo proceso.
- `POST /api/files/validate` valida un archivo en memoria y no modifica la base de datos.
- Se admiten `DF14A`, `Acta de certificacion`, `Requisitos / pendientes` y `Otro archivo`.
- La validacion reconoce `XLSX`, `XLS`, `CSV`, `PDF` y `DOCX` segun el tipo seleccionado.
- El analisis de filas y encabezados se realiza para archivos tabulares cuando el formato puede abrirse.

## Modelo inicial de datos

La base de datos ya separa la informacion de negocio de los registros genericos de
una importacion:

- `Learner`: identificacion, nombre, programa, ficha, tipo de formacion, estado de
	certificacion, fechas y notas de seguimiento.
- `Requirement`: requisitos asociados a un aprendiz, incluyendo resultado de
	aprendizaje, documentacion, etapa productiva, paz y salvo, Saber TyT y estado.
- `Act`: numero, fecha, tipo, archivo original, estado de revision y observaciones.
- `ActLearner`: relacion entre actas y aprendices, porque un acta puede relacionar
	varios aprendices y un aprendiz puede aparecer en varias actas.
- `ImportHistory`: archivo, tipo, fecha, cantidades, advertencias, errores, estado
	y usuario opcional.

Los campos de dominio se mantienen opcionales cuando su formato o regla todavía no
ha sido confirmado. La importacion continua guardando el registro original como JSON
hasta revisar archivos reales y definir el mapeo de columnas del DF14A y de las actas.

## Ejecutar en desarrollo

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Luego abre `http://127.0.0.1:8000`.

## Ejecutar con Docker

Requiere Docker Desktop con el motor Docker activo. Desde la raiz del proyecto:

```powershell
docker compose up --build
```

Luego abre `http://127.0.0.1:8000`. El codigo local se monta dentro del contenedor y
Uvicorn recarga la aplicacion cuando detecta cambios.

Para detener el servicio:

```powershell
docker compose down
```

Para ejecutar las pruebas dentro del mismo entorno:

```powershell
docker compose run --rm backend pytest
```

El volumen `app_data` queda reservado para conservar la futura base de datos SQLite.

## Pruebas

```powershell
pytest
```

La persistencia en SQLite, las reglas definitivas de negocio y la extraccion de datos de actas quedan para cuando esten disponibles los archivos reales y sus estructuras.
