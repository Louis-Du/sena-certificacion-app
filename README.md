# Sena Certificacion App

Primer vertical del sistema de informacion para cargar y validar archivos usados en el proceso de certificacion.

## Estado actual

- FastAPI sirve la interfaz HTML/CSS/JavaScript desde el mismo proceso.
- `POST /api/files/validate` valida un archivo en memoria y no modifica la base de datos.
- `GET /api/learners` devuelve el listado de aprendices guardados en SQLite.
- Se admiten `DF14A`, `Acta de certificacion`, `Requisitos / pendientes` y `Otro archivo`.
- La validacion reconoce `XLSX`, `XLS`, `CSV`, `XML`, `PDF` y `DOCX` segun el tipo seleccionado.
- El analisis de filas y encabezados se realiza para archivos tabulares cuando el formato puede abrirse.
- Los contadores, las reglas por tipo y las decisiones administrativas pendientes
  estan documentados en [`docs/validation_rules.md`](docs/validation_rules.md).

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

Los campos de dominio se mantienen opcionales cuando su formato o regla todavia no
ha sido confirmado. La importacion continua guardando el registro original como JSON
y, para archivos DF14A, actualiza el listado base de aprendices en SQLite.

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

### Ejecucion

Las pruebas se ejecutan con el interprete del entorno virtual. En Windows (PowerShell):

```powershell
# 1. Dependencias de la aplicacion y de las pruebas (una sola vez)
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 2. Navegador para las pruebas E2E (una sola vez)
.\.venv\Scripts\python.exe -m playwright install chromium

# 3. Unitarias, integracion y regresion (rapidas, sin navegador)
.\.venv\Scripts\python.exe -m pytest -m "not e2e"

# 4. Solo E2E con Playwright
.\.venv\Scripts\python.exe -m pytest -m e2e

# 5. Todo
.\.venv\Scripts\python.exe -m pytest
```

Tambien pueden ejecutarse por archivo, por ejemplo:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_learner_detail.py
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_e2e_acts.py
.\.venv\Scripts\python.exe -m pytest tests/e2e --headed   # ver el navegador
```

Aislamiento: `tests/conftest.py` fija `DATABASE_URL=sqlite:///:memory:` antes de importar
la app, las pruebas usan bases SQLite temporales y cada prueba E2E arranca su propio
servidor `uvicorn` en un puerto libre con una base temporal. Nunca se usa
`data/sena_certificacion.db`. Si `playwright` no esta instalado, los archivos E2E se omiten.

## Preparar demo portable para Windows

La demo se construye con PyInstaller en modo carpeta (`one-folder`). Esta opcion no
requiere Python instalado en el equipo de presentacion y conserva los archivos
estaticos dentro del paquete. SQLite se crea o utiliza en la carpeta de la demo, por
lo que los datos pueden conservarse entre ejecuciones.

Desde PowerShell en la raiz del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_demo.ps1
```

El ejecutable queda en
`dist\SenaCertificacionDemo\SenaCertificacionDemo.exe`. Para presentarlo, entrega la
carpeta completa `dist\SenaCertificacionDemo` y ejecuta el `.exe`; luego abre
`http://127.0.0.1:8000` en el navegador. El lanzador intenta abrir esa direccion
automaticamente. La consola permanece visible para mostrar el estado del servidor y
se cierra al terminar la aplicacion. Si el inicio falla, la consola queda abierta
para mostrar el error. Si el puerto 8000 ya esta ocupado, el lanzador selecciona
automaticamente otro puerto local disponible y abre el navegador en esa direccion.

### Pruebas realizadas

#### Pruebas unitarias

Archivo: [`tests/test_learners.py`](./tests/test_learners.py)

| Caso | Resultado esperado | Resultado obtenido |
|---|---|---|
| Interpretar columnas reales de un DF14A (`DOCUMENTO`, `NOMBRES`, `FICHA`, `PROGRAMA`, `ESTADO_ASPIRANTE`) | Convertir la fila al modelo `Learner` con los valores correctos | Superado |
| Normalizar identificaciones con prefijo, por ejemplo `TI_1028865527` | Guardar únicamente `1028865527` | Superado |
| Buscar por nombre | Devolver únicamente los aprendices coincidentes | Superado |
| Buscar por programa | Devolver todos los registros del programa buscado | Superado |
| Buscar por ficha | Devolver los aprendices asociados a la ficha | Superado |
| Filtrar aprendices por estado `Por certificar` | Devolver únicamente el estado registrado solicitado y su cantidad | Superado |
| Consultar un aprendiz por certificar | No modificar sus requisitos al consultar el filtro | Superado |

#### Pruebas de integración

| Caso | Resultado esperado | Resultado obtenido |
|---|---|---|
| Consultar `GET /api/learners` | Responder HTTP 200 con aprendices provenientes de SQLite | Superado |
| Paginar aprendices | Devolver página, tamaño, total y número de páginas correctos | Superado |
| Consultar una página de 5 registros | Devolver 5 registros y metadatos coherentes | Superado |
| Sincronizar registros DF14A históricos cuando `learners` está vacío | Crear aprendices a partir de `ImportedRecord` | Superado |
| Confirmar una importación DF14A | Guardar o actualizar aprendices en SQLite | Superado |
| Confirmar una segunda importación con los mismos registros | Marcar registros como actualizados, sin duplicarlos | Superado |

#### Pruebas de regresión

Archivo: [`tests/test_import_flow.py`](./tests/test_import_flow.py)

| Caso | Resultado esperado | Resultado obtenido |
|---|---|---|
| Validar un archivo sin confirmar | No crear registros en el historial | Superado |
| Detectar filas duplicadas | Reportar estado `warning` y el número de duplicados | Superado |
| Obtener vista previa de importación | Informar registros nuevos y actualizados | Superado |
| Confirmar importación | Crear historial y registros importados | Superado |
| Actualizar una importación existente | Reutilizar el registro y contar la actualización | Superado |
| Actualizar el listado de aprendices después de confirmar | Reflejar los datos confirmados en `/api/learners` | Superado |

### Resultado de la suite

Ultima ejecucion (entorno virtual limpio, Chromium headless):

```text
134 passed, 1 warning in 80s     (93 sin E2E en ~4 s + 41 E2E)
```

La unica advertencia corresponde a la compatibilidad futura entre `Starlette
TestClient` y `httpx` (el aviso sugiere `httpx2`); no afecta el resultado funcional.

Comportamientos que NO estan definidos funcionalmente y por eso solo se documentan:

- `history` del detalle del aprendiz permanece vacio: `ImportHistory`/`ImportedRecord` no
  tienen relacion con `Learner`.
- Importar un archivo de tipo "Acta de certificacion" solo registra la importacion; no crea
  un `Act` (las actas se registran manualmente en la pestaña Actas).
- Al reimportar un aprendiz con datos modificados, el resumen cuenta el registro como
  "nuevo" (la llave es un hash del contenido); el aprendiz si se actualiza sin duplicarse.
- La interfaz de actas no tiene controles para editar ni eliminar actas (solo la API).
- `_upgrade_sqlite_schema` solo agrega `import_history.error_count`, `import_history.user_name`
  y `requirements.requirement_type`; otros cambios de esquema en bases antiguas no se migran.

### Verificación manual de interfaz

También se verificó la vista `/#aprendices` en el navegador:

- Se cargaron 1.059 aprendices desde SQLite.
- Se visualizaron 25 registros en la primera página.
- Se calcularon 43 páginas.
- El buscador devolvió resultados por nombre.
- La tabla mostró nombre, documento, programa, ficha y estado.
- Los botones de paginación y actualización respondieron correctamente.

La persistencia en SQLite, las reglas definitivas de negocio y la extracción de datos
de actas quedan sujetas a la disponibilidad de archivos reales y sus estructuras.
