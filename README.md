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

## Sincronizacion automatica desde Google Sheets

En la vista **Cargar informacion**, el boton **Google Sheets** de la barra
superior despliega un buscador para pegar la URL de una hoja compartida como
"Cualquier persona con el enlace" -> Lector. El sistema descarga el XLSX publico,
calcula el hash SHA-256 y muestra una revision previa con los conflictos
CERTIFICADOS/PENDIENTES antes de importar. La importacion solo se ejecuta al
confirmar y reutiliza el flujo existente (`stage_file` + `confirm_import`).

Con la sincronizacion habilitada (`enabled=true`), el worker de fondo corre
dentro del proceso de la aplicacion (tambien dentro del `.exe`) cada
`interval_seconds`, 60 segundos por defecto. Cada ciclo:

1. Descarga el XLSX publico y calcula su SHA-256.
2. Si el hash coincide con el ultimo importado, deja `last_status="unchanged"`
   sin notificar.
3. Si cambio, valida el archivo y calcula la vista previa.
4. Si no hay conflictos, importa automaticamente como antes.
5. Si hay documentos en CERTIFICADOS y PENDIENTES a la vez **sin un desempate
   previo**, deja el lote en `conflict_pending` y **no importa**.
6. Si todos los cruces ya tienen un desempate guardado, los reaplica en
   silencio e importa el lote sin abrir de nuevo el flujo de intervencion.

### Desempate condicional (`conflict_resolution`)

`conflict_resolution` no es un estado permanente: solo vale mientras el
documento siga en la interseccion CERTIFICADOS/PENDIENTES.

- Si en una revision posterior aparece solo en CERTIFICADOS, se toma ese estado
  y se limpia `conflict_resolution`.
- Si aparece solo en PENDIENTES, se toma ese estado y se limpia
  `conflict_resolution`.
- Si ya no aparece en ninguna hoja, no se fuerza el estado viejo: aplican las
  reglas normales de importacion y se limpia el desempate.
- `last_conflict_resolution` conserva la ultima decision manual como historial.
  Si el documento vuelve a aparecer en ambas hojas, esa decision se reaplica en
  silencio (sin nuevo toast ni bloqueo), salvo que el usuario la cambie.
- Resolver en la aplicacion **nunca** modifica Google Sheets. La hoja solo se
  lee/descarga; cualquier correccion del registro duplicado es manual.

### Persistencia del lote en conflicto

El lote detenido se guarda en `SheetSyncConfig` y sobrevive reinicios de la
aplicacion:

- `last_status="conflict_pending"`
- `pending_validation_id` (lote staged)
- `pending_conflict_count`
- `pending_conflict_fingerprint` (SHA-256 de los documentos en conflicto)
- `pending_hash`, `pending_file_name` y el contenido XLSX del lote
- `pending_conflicts_json` y `pending_preview_json` (resumen serializado)
- `notified_at` (ultima notificacion nativa del conjunto)

`last_hash` **no** se actualiza mientras el conflicto este pendiente, de modo
que el worker no descarta el lote ni lo reimporta solo. El mismo conjunto de
documentos conserva su huella aunque cambie el orden de las filas o el resto del
archivo; por eso no se repite el toast en cada ciclo de 60 segundos.

### Aviso al usuario

- **Toast nativo del sistema**: titulo "Conflicto de certificacion detectado" y
  cuerpo con el numero de aprendices. Se emite una sola vez por huella. Al hacer
  clic se enfoca la ventana y se abre el modal de resolucion.
- En escritorio se usa el bridge JS -> Python de pywebview
  (`DesktopNotificationBridge` en `demo.py`). En Windows se prefiere
  `windows-toasts` (permite capturar el clic) y `plyer` como respaldo. En
  navegador se usa la Notification API si esta disponible.
- **Banner global**: barra fija superior visible en todas las vistas con el
  texto de conflictos pendientes, boton **Resolver ahora** y boton
  **Mas tarde**. "Mas tarde" solo oculta el banner durante la sesion actual; el
  estado del backend y el lote no se borran. El banner hace polling ligero cada
  12 segundos a `GET /api/sheets/sync`, no bloquea la app y no aparece si no hay
  conflictos.
- El flujo de resolucion no depende de `history.replaceState`: si un bloqueador
  como Malwarebytes Browser Guard lanza "Breaking Browser Locker Behavior
  detected", la navegacion interna y el modal de resolucion siguen funcionando.

### Resolucion

**Resolver ahora** (o el clic en el toast) carga el lote pendiente con la misma
UI de coherencia (`renderCoherenceConflicts`) y exige elegir CERTIFICADOS o
PENDIENTE para cada aprendiz. Al confirmar se aplican `conflict_resolutions`,
se importa el lote, se actualiza `last_hash` y se limpian
`conflict_pending`/`pending_*`/`notified_at`; el banner desaparece. Si el usuario
cierra sin resolver, el lote sigue pendiente y el worker no lo reimporta.

El panel de conflictos solo contiene la lista de aprendices y la eleccion
Certificado/Pendiente. Al pulsar **Confirmar importacion**, si el lote tuvo
conflictos de coherencia, se abre el modal flotante **"Antes de confirmar"**
antes de enviar el POST. El modal advierte que la decision aplica solo dentro de
la app, que la aplicacion solo lee Google Sheets y los archivos de origen, que el
cruce permanecera en la hoja mientras no se corrija manualmente y que, si la
hoja deja el cruce, la app tomara el estado de la unica lista vigente. Incluye
una casilla opcional ("Ya corregi o elimine el registro duplicado en Google
Sheets") que solo se registra en el historial local como trazabilidad
(`sheets_manual_cleanup_acknowledged`) y no dispara ninguna escritura remota.
Los lotes sin conflictos se confirman directamente, sin este modal.

### Endpoints

Endpoints disponibles bajo `/api/sheets/sync`:

- `GET` estado actual, incluidos `conflict_pending`, `pending_conflict_count`,
  `pending_conflict_summary` y `notification_pending`
- `POST` registrar/actualizar URL y activar
- `PATCH` `{ "enabled": true/false }`
- `POST /preview` descarga y valida sin importar (para revisar conflictos)
- `POST /confirm` confirma la importacion revisada; acepta el acuse
  `sheets_manual_cleanup_acknowledged` solo para trazabilidad
- `POST /run` sincronizacion automatica inmediata
- `GET /pending-conflicts` detalle del lote pendiente (conflictos + preview)
- `POST /resolve` body
  `{ "conflict_resolutions": [...], "sheets_manual_cleanup_acknowledged": true }`;
  resuelve e importa el lote pendiente. El acuse es opcional y solo documental.
- `POST /notified` body `{ "fingerprint": "..." }`; registra que el toast del SO
  ya se mostro para esa huella
- `DELETE` eliminar configuracion

El flujo manual del boton **Google Sheets** usa `/preview` y `/confirm` para
mostrar la misma revision de importacion que la carga de archivos. Si el lote
manual coincide con el pendiente, se reutiliza el staged guardado y la
confirmacion limpia el estado pendiente.

### Criterios de aceptacion verificados

| Criterio | Prueba |
|---|---|
| El worker corre con intervalo de 60 s y compara SHA-256 | `tests/test_sheets_sync.py` |
| Un conflicto deja `conflict_pending` sin importar ni actualizar `last_hash` | `test_run_conflict_pending_persists_recoverable_state` |
| El mismo conflicto no repite notificacion en cada ciclo | `test_same_pending_conflict_does_not_renotify_or_change_hash` |
| Cambiar el archivo sin cambiar el conjunto de conflictos no re-notifica | `test_new_sheet_content_with_same_conflicts_keeps_notification_mark` |
| `GET /pending-conflicts` expone preview y conflictos | `test_pending_conflicts_endpoint_and_notification_mark` |
| `POST /resolve` importa, limpia el estado y oculta el banner | `test_resolve_pending_imports_lot_and_clears_state` |
| Cerrar sin resolver mantiene el lote pendiente | `test_resolve_requires_every_conflict_resolution` |
| La resolucion funciona tras reiniciar la app (lote recuperado de SQLite) | `test_resolution_recovers_staged_lot_after_restart` |
| El mismo cruce ya resuelto se reutiliza sin volver a interrumpir | `test_next_scan_reuses_saved_resolution_without_intervencion` |
| Si el documento deja la interseccion, manda la hoja y se limpia el desempate | `test_document_leaving_intersection_clears_tiebreak_and_follows_sheet` |
| Si el cruce reaparece, se reaplica la ultima decision sin toast | `test_document_leaving_intersection_clears_tiebreak_and_follows_sheet` |
| Un conflicto nuevo solo pide decision por el documento nuevo | `test_new_conflict_after_resolved_one_only_requests_the_new_document` |
| El panel solo pide el estado; la advertencia larga vive en el modal de confirmacion | `test_conflict_panel_only_contains_the_state_decision` |
| El modal "Antes de confirmar" advierte que solo se lee Sheets y que la correccion es manual | `test_second_confirmation_modal_has_required_warning_and_actions` |
| El POST de importacion espera la segunda confirmacion cuando hubo conflictos | `test_import_post_waits_for_second_confirmation_when_conflicts_exist` |
| El acuse de correccion manual queda solo como trazabilidad local | `test_resolve_records_manual_sheets_cleanup_acknowledgement` |
| El bridge nativo deduplica por huella y el `.exe` declara dependencias | `tests/test_desktop_launcher.py` |

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
