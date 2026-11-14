# Rediseño de «Resolver conflicto» — Requisitos y evidencias (ACTAS 2026)

## 1. Resumen

El consolidado **ACTAS 2026** trae dos fuentes para el mismo hecho:

- las columnas de evidencias (`X`, `N.A`, `Pendiente` o vacío);
- la columna **MOTIVO DE NO CERTIFICACIÓN**, escrita en texto libre.

El rediseño reemplaza el comportamiento anterior («clic = Cumplido, no clic =
Pendiente») por una decisión **explícita y excluyente** entre tres estados:
**Pendiente**, **Cumplido** y **No aplica**. No tocar una opción deja el
conflicto **sin resolver** y bloquea la confirmación, salvo que exista una regla
automática o una decisión guardada vigente.

El objetivo es que la persona pueda revisar lotes de 200 o más conflictos sin
perder trazabilidad: filtros, grupos por confianza, acciones por lote, barra de
progreso, resumen previo a la confirmación y auditoría por cada decisión.

---

## 2. Problema anterior

| Situación anterior | Riesgo |
| --- | --- |
| Un clic marcaba el requisito como Cumplido y otro clic lo devolvía a Pendiente. | La decisión dependía de un gesto accidental y no dejaba claro el estado final. |
| No hacer clic equivalía a Pendiente. | Se inventaba una decisión que nadie tomó. |
| Una celda vacía se interpretaba como Pendiente. | Se creaban conflictos donde el motivo no hablaba del requisito. |
| El modal mostraba una lista plana. | Con 200+ conflictos era imposible priorizar ni aplicar criterios comunes. |
| La decisión no distinguía origen ni huella. | Una reimportación podía reutilizar una decisión vieja sobre un hecho distinto. |

### Principios de diseño

1. **Tres estados explícitos.** Cada requisito en conflicto tiene exactamente
   tres botones: `Pendiente`, `Cumplido`, `No aplica`. El estado seleccionado se
   anuncia con `aria-pressed` y una clase visual.
2. **No tocar no decide.** Un conflicto sin decisión humana, sin decisión
   guardada vigente y sin regla automática queda «Sin resolver».
3. **El motivo no se inventa.** Solo se crea un conflicto cuando el motivo
   menciona el requisito o cuando la regla de Saber TyT lo justifica.
4. **La columna y el motivo se muestran juntos.** La persona ve el contraste
   real antes de decidir.
5. **Toda decisión se audita.** Estado final, origen, huella del contraste,
   lote y momento de importación.
6. **Una decisión vieja no se reaplica a un hecho nuevo.** Si cambia la huella,
   el conflicto se reabre.

---

## 3. Alcance

Incluido:

- detección de incongruencias entre columnas de evidencia y motivo;
- agrupación por confianza;
- sugerencias visibles, nunca decisiones implícitas;
- acciones por lote sobre los conflictos visibles;
- progreso y resumen por regla, manual y sin resolver;
- auditoría en el historial de requisitos (RF-19);
- reaplicación y reapertura por huella;
- integración con el flujo de Google Sheets y con la importación de ACTAS 2026.

Fuera de alcance:

- rediseñar el resto de la aplicación;
- escribir o corregir filas en Google Sheets;
- cambiar las reglas de negocio de certificación;
- convertir automáticamente un vacío en Pendiente sin motivo o sin regla.

---

## 4. Modelo de decisión

### 4.1 Estados finales

| Estado | Significado | Uso típico |
| --- | --- | --- |
| `Pendiente` | El requisito no está cumplido. | El motivo dice que falta o la persona lo confirma. |
| `Cumplido` | El requisito está cumplido. | La columna trae `X` y la persona decide que la columna manda. |
| `No aplica` | El requisito no corresponde al aprendiz. | Saber TyT en un nivel distinto de TGO, o decisión humana. |

`Sin información` **no es una decisión**. Es el estado que describe una celda
vacía y solo puede quedar como estado del requisito cuando el conflicto no
existe o cuando la persona no intervino en un caso que no bloquea.

### 4.2 Llave del conflicto

La UI y el backend identifican cada conflicto con:

```text
{documento}|{tipo_requisito}
```

Ejemplo: `1001003001|saber_tyt`.

Esto permite que un mismo aprendiz tenga varias decisiones en el mismo lote sin
que se pisen entre sí.

### 4.3 Huella del contraste

La huella es un SHA-1 corto (20 caracteres) calculado con:

```text
tipo_requisito | evidencia_raw | evidence_status | motivo | nivel
```

Se normaliza cada componente con `parsers.normalize_text` antes de calcularla.
La huella permite:

- reaplicar una decisión guardada solo si el hecho sigue siendo el mismo;
- reabrir el conflicto si cambió la columna, el motivo o el nivel;
- rechazar una decisión enviada desde un modal abierto con datos viejos.

Las decisiones anteriores a la existencia de la huella (bases antiguas) se
conservan por compatibilidad y se consideran vigentes.

---

## 5. Detección de conflictos

### 5.1 Estado de una celda de evidencia

`evidence_status()` traduce la celda así:

| Celda | Estado |
| --- | --- |
| `X`, `x`, `SI`, `Cumplido`, `Aprobado` | `Cumplido` |
| `N.A`, `N.A.`, `NA`, `No aplica` | `No aplica` |
| `Pendiente` u otro texto explícito | `Pendiente` |
| Vacía, `NaN`, `None`, `null` | `Sin información` |

Una celda vacía **nunca** se convierte en `Pendiente` por omisión.

### 5.2 Asociación del motivo con un requisito

El motivo se parte en causas atómicas con `normalize_motivo_fragments()` y cada
causa se compara con palabras clave:

| Causa reconocida | Requisito |
| --- | --- |
| `T&T`, `TyT`, `Saber T`, `pruebas saber` | `saber_tyt` |
| `Agencia Pública de Empleo` | `ape` |
| `carnet` | `carnet` |
| `documento de identidad`, `documento vencido`, `identidad vencida` | `documento_identidad` |
| `etapa productiva` | `etapa_productiva` |
| `certificado de la empresa`, `certificado empresa` | `certificado_empresa` |
| `biblioteca` | `biblioteca` |
| `bienestar` | `bienestar` |
| `almacén` | `almacen` |

Si el motivo es genérico («No ha remitido documentos») y no se reconoce una
causa, **no se inventa un requisito**. Ese texto no participa en la comparación
columna/motivo.

### 5.3 Matriz de patrones

| Patrón | Condición | Grupo | Sugerencia | ¿Automática? |
| --- | --- | --- | --- | --- |
| `evidence_fulfilled_motivo_missing` | Columna `X` (`Cumplido`) y el motivo nombra el requisito. | Alta confianza / auto-sugerible | `Pendiente` | No |
| `evidence_blank_motivo_missing` | Celda vacía (`Sin información`) y el motivo nombra el requisito. | Media | `Pendiente` | No |
| `evidence_na_motivo_missing` | Columna `N.A` (`No aplica`) y el motivo dice que falta. | Requiere revisión | Sin sugerencia fuerte | No |
| `tyt_not_applicable_level` | Saber TyT, nivel distinto de TGO y celda vacía. | Alta confianza / auto-sugerible | `No aplica` | Sí |
| `tyt_level_mismatch` | Saber TyT, nivel distinto de TGO, columna con `X`/`Pendiente` y motivo que lo nombra. | Requiere revisión | `No aplica` | No |

La sugerencia es una ayuda visual. Salvo `tyt_not_applicable_level`, **no se
aplica sola**: la persona debe confirmarla o cambiarla.

### 5.4 Casos que no generan conflicto

- Celda vacía y motivo que **no** nombra el requisito (por ejemplo, APE vacío
  con motivo «No anexa T&T»).
- Celda `Pendiente` explícita y motivo que sí nombra el requisito: son
  coherentes.
- Saber TyT vacío en un nivel distinto de TGO: se resuelve por la regla
  automática `No aplica`, no como conflicto manual.
- Saber TyT ya marcado `No aplica` en un nivel distinto de TGO: la columna ya
  dice lo que corresponde.
- Motivo genérico sin causa reconocible.
- Cruce del mismo documento entre CERTIFICADOS y PENDIENTES: es un **conflicto
  de estado**, se revisa en la otra pestaña y no se mezcla con requisitos.

### 5.5 Regla de Saber TyT

Saber TyT está marcado en el consolidado como **«(SOLO TGO)»**. La regla se
evalúa antes de mirar el motivo:

```text
si requisito == saber_tyt y nivel != tecnologo:
    si celda vacía           -> conflicto automático, No aplica
    si celda == No aplica    -> sin conflicto
    si celda == X/Pendiente y motivo nombra TyT -> revisión manual
    en otro caso             -> sin conflicto
```

La regla automática se registra con origen `rule` y no bloquea la importación.

---

## 6. Experiencia de usuario

### 6.1 Flujo

1. La persona carga el consolidado ACTAS 2026.
2. La validación muestra el aviso de coherencia con el número de conflictos
   manuales y automáticos.
3. Al abrir «Resolver conflicto», el modal tiene dos pestañas:
   - **Estados de certificación** (cruces CERTIFICADOS/PENDIENTES);
   - **Requisitos y evidencias** (el rediseño de este documento).
4. La pestaña de requisitos muestra primero los grupos de mayor confianza.
5. La persona decide caso por caso o aplica una acción por lote sobre los
   conflictos visibles.
6. El botón «Continuar a confirmación» se habilita solo cuando no quedan
   decisiones pendientes.
7. Antes de importar aparece un segundo modal con el resumen:
   - estados resueltos;
   - requisitos resueltos por regla automática;
   - requisitos manuales o guardados;
   - requisitos sin resolver.
8. La advertencia de Google Sheets y su acuse solo se muestran si hay
   **conflictos de estado**. Los conflictos de requisitos no escriben en la hoja.
9. Al confirmar, el backend aplica las decisiones y deja el historial auditado.

### 6.2 Grupos del modal

| Grupo | Contenido | Orden |
| --- | --- | --- |
| Alta confianza / auto-sugerible | `X` contra motivo y TyT no aplicable por nivel. | 1 |
| Media | Celda vacía con motivo que nombra el requisito. | 2 |
| Requiere revisión | `N.A` contra motivo y TyT marcado fuera de TGO. | 3 |

Los grupos son `<details>` plegables y conservan su estado abierto/cerrado
mientras se filtra. Cada grupo muestra cuántos requisitos contiene y cuántos
siguen sin resolver.

### 6.3 Tarjeta de conflicto

Cada tarjeta muestra:

- documento, nombre, ficha, nivel y hoja de origen;
- etiqueta corta del patrón y nombre del requisito;
- contraste «Columna ↔ Motivo»;
- explicación breve del conflicto;
- tres botones de estado;
- sugerencia visible o «Sin sugerencia: requiere revisión»;
- origen de la decisión actual: `Sin resolver`, `Elegido por ti`, `Acción por
  lote`, `Regla automática` o `Decisión guardada`.

### 6.4 Filtros

- búsqueda por documento, nombre, ficha, requisito, patrón, motivo, evidencia o
  estado;
- grupo (`high`, `medium`, `review`);
- tipo de requisito;
- estado de la decisión (`sin resolver`, `resueltos`, `por regla`,
  `manuales o guardados`).

El contador «Mostrando X de Y» se actualiza con los filtros.

### 6.5 Acciones por lote

Las acciones se aplican **solo a los conflictos visibles** con el filtro actual:

| Acción | Qué hace | Omite |
| --- | --- | --- |
| Aplicar sugerencia | Usa `suggested_status` del conflicto. | Casos sin sugerencia y reglas ya iguales. |
| El motivo manda | Marca `Pendiente` cuando el motivo menciona el requisito. | Conflictos automáticos o sin mención en el motivo. |
| La columna manda | Usa el estado de la celda (`Cumplido`, `No aplica` o `Pendiente`). | Conflictos automáticos y celdas sin estado decidible. |
| TyT no TGO → No aplica | Marca `No aplica` en Saber TyT cuando el nivel no aplica. | Requisitos que no son TyT o niveles TGO. |

Las decisiones por lote se envían con origen `bulk`. La persona puede cambiar
una decisión individual después de aplicarla; en ese caso el origen vuelve a
`user`.

### 6.6 Progreso

La barra fija muestra el formato:

```text
Estados: 3/3 resueltos · Requisitos: 180 por regla, 12 manuales, 15 sin resolver
```

- **por regla**: conflictos automáticos (`tyt_not_applicable_level`);
- **manuales**: decisiones explícitas del usuario o por lote, más las
  decisiones guardadas reaplicadas;
- **sin resolver**: conflictos manuales sin decisión.

El porcentaje se calcula sobre la suma de conflictos de estado y de requisitos.
La barra usa `role="progressbar"` y actualiza `aria-valuenow`.

### 6.7 Accesibilidad y responsive

- Las pestañas usan `role="tablist"`, `role="tab"` y `aria-selected`.
- Los botones de estado usan `aria-pressed`.
- Los mensajes de progreso y de resumen usan `aria-live="polite"`.
- El modal conserva el foco en el diálogo y lo devuelve al botón de apertura.
- En pantallas pequeñas la barra de acciones, los filtros y las tarjetas se
  apilan sin perder los tres estados.

---

## 7. Reglas y pseudocódigo

### 7.1 Detección por aprendiz

```text
agrupar registros importables de CERTIFICADOS/PENDIENTES por documento
para cada documento:
    motivo = último motivo no vacío
    causas = normalize_motivo_fragments(motivo)
    requisitos_mencionados = {requirement_for_cause(c) para c en causas}

    effective = último registro leído por campo
                (PENDIENTES se procesa después de CERTIFICADOS)

    para cada campo de evidencia presente:
        raw = texto de la celda
        status = evidence_status(raw)
        aplica = requirement_level_applies(registro, campo)
        patrón = pattern_for(campo, status, campo in requisitos_mencionados, aplica)

        si patrón:
            emitir conflicto {
                llave, documento, requisito, grupo,
                evidencia_raw, evidence_status, motivo,
                sugerencia, auto_resolved, fingerprint
            }
```

El orden final es: grupo (alta, media, revisión), patrón, documento y
requisito. Así la UI es estable entre importaciones.

### 7.2 Selección de patrón

```text
si requisito == saber_tyt y no aplica:
    si status == Sin información: return tyt_not_applicable_level
    si status == No aplica:       return None
    si status in {Cumplido, Pendiente} y motivo menciona TyT:
        return tyt_level_mismatch
    return None

si motivo no menciona el requisito:
    return None

si status == Cumplido:       return evidence_fulfilled_motivo_missing
si status == No aplica:      return evidence_na_motivo_missing
si status == Sin información: return evidence_blank_motivo_missing
si status == Pendiente:      return None   # coherente con el motivo
```

### 7.3 Prioridad de resolución

```text
explícita = decisiones válidas enviadas por la UI
            (llave existente, estado válido, origen válido y huella vigente)

guardada = última decisión de conflicto por llave cuyo fingerprint
           coincida con el conflicto actual (o que no tenga huella, por
           compatibilidad)

effective = {**guardada, **explícita}

para cada conflicto automático sin decisión en effective:
    effective[llave] = {status: sugerencia, source: rule}

si falta alguna llave:
    error 400: "Faltan N resolución(es) de requisito..."
```

Prioridad resultante: **decisión explícita > decisión guardada vigente > regla
automática**.

### 7.4 Reaplicación y reapertura

```text
en la vista previa:
    conflicto_actual = detectar de nuevo
    para cada decisión histórica:
        si fingerprint_guardado == fingerprint_actual:
            mostrar como "Decisión guardada"
        si fingerprint_guardado != fingerprint_actual:
            no reutilizar; el conflicto queda sin resolver
```

- Si el lote no cambió, la decisión guardada se reaplica **sin volver a
  preguntar** y el resumen la cuenta como manual/guardada.
- Si cambió la columna, el motivo o el nivel, el conflicto se reabre.
- Si la UI envía una huella que ya no coincide, el backend rechaza la decisión
  con un error de conflicto desactualizado.

### 7.5 Bloqueo de confirmación

En la UI:

```text
pendientes = estados_sin_resolver + requisitos_sin_resolver
si pendientes > 0:
    abrir modal de resolución
    mostrar "Faltan N decisiones..."
    no confirmar
```

En el backend, `confirm_import()` vuelve a calcular conflictos y exige
resolución para todos los conflictos manuales. Las decisiones automáticas o
guardadas completan lo que falte, por lo que no bloquean.

Si hay cualquier conflicto (aunque ya esté resuelto), la UI abre el segundo
modal de confirmación con el resumen. Nunca se confirma en silencio un lote con
conflictos.

---

## 8. Contrato técnico

### 8.1 Respuesta de validación

`POST /api/files/validate` incluye:

```json
{
  "status_conflicts": [],
  "coherence_conflicts": [],
  "status_conflict_summary": {"total": 0},
  "requirement_conflicts": [],
  "requirement_conflict_summary": {
    "total": 195,
    "auto_resolved": 180,
    "requires_decision": 15,
    "groups": {"high": 12, "medium": 3, "review": 0},
    "patterns": {"tyt_not_applicable_level": 180}
  }
}
```

`coherence_conflicts` se conserva como alias histórico de `status_conflicts`.

### 8.2 Vista previa de importación

`GET /api/imports/{validation_id}/preview` añade:

```json
{
  "requirement_conflicts": [],
  "requirement_conflict_summary": {
    "total": 195,
    "auto_resolved": 180,
    "requires_decision": 15,
    "groups": {"high": 12, "medium": 3, "review": 0},
    "patterns": {},
    "resolved_saved": 12,
    "unresolved": 3
  },
  "requirement_conflict_resolutions": {"documento|requisito": "Pendiente"},
  "requirement_conflict_resolution_sources": {"documento|requisito": "user"},
  "requirement_conflict_resolution_fingerprints": {"documento|requisito": "a1b2c3..."}
}
```

- `requirement_conflict_resolutions` contiene solo decisiones guardadas
  vigentes.
- La UI las pinta como «Decisión guardada» y **no las reenvía**.
- `unresolved` excluye las automáticas y las guardadas.

### 8.3 Confirmación

`POST /api/imports/{validation_id}/confirm` acepta:

```json
{
  "accept_missing_complementaria": true,
  "conflict_resolutions": [
    {"identification": "1001003001", "status": "CERTIFICADOS"}
  ],
  "requirement_conflict_resolutions": [
    {
      "identification": "1001003001",
      "requirement_type": "saber_tyt",
      "status": "Pendiente",
      "source": "user",
      "conflict_fingerprint": "a1b2c3d4e5f6..."
    }
  ]
}
```

Reglas del contrato:

- `status` admite `Pendiente`, `Cumplido` o `No aplica`.
- `source` admite `user`, `bulk` o `rule`; `saved` no se envía desde la UI.
- `conflict_fingerprint` es opcional, pero si se envía debe coincidir con el
  conflicto recalculado.
- Una decisión de otro lote se ignora para no romper la importación actual.
- Una decisión con estado u origen inválido devuelve error 400.
- Una huella desactualizada devuelve error 400 con el mensaje «El conflicto
  cambió desde que se abrió el modal».

### 8.4 Errores esperados

| Situación | Respuesta |
| --- | --- |
| Faltan requisitos manuales por resolver. | `400` con «Faltan N resolución(es) de requisito». |
| Estado u origen inválido. | `400` con el detalle del requisito. |
| Huella desactualizada. | `400` «El conflicto cambió desde que se abrió el modal». |
| Faltan desempates de estado. | `400` con «Faltan N resolución(es) de conflicto». |
| Archivo sin registros importables. | `400` antes de evaluar conflictos. |

---

## 9. Auditoría

### 9.1 Persistencia

Cada decisión de requisito se guarda en `requirement_status_history` con:

| Campo | Valor |
| --- | --- |
| `source` | `conflict:requirement` |
| `status` | Estado final elegido. |
| `decision_source` | `user`, `bulk` o `rule`. |
| `conflict_fingerprint` | Huella del contraste que originó la decisión. |
| `note` | Texto legible con estado, origen, columna, motivo y lote. |
| `recorded_at` | Momento de la importación. |

La decisión también actualiza el estado actual del requisito en `requirements`.
La importación conserva su `ImportHistory` y el mensaje resume cuántos
conflictos se aplicaron por decisión manual/lote, regla automática o decisión
guardada.

### 9.2 Formato de la nota

```text
Conflicto resuelto: {estado} · Origen: {origen} · Columna: «{raw}» ({estado de la celda}) · Motivo: «{motivo}» · Lote: {archivo}
```

Ejemplos:

```text
Conflicto resuelto: Pendiente · Origen: Usuario · Columna: «X» (Cumplido) · Motivo: «No anexa T&T» · Lote: ACTAS_2026.xlsx
```

```text
Conflicto resuelto: No aplica · Origen: Regla automática · Columna: «vacía» (Sin información) · Motivo: «» · Lote: ACTAS_2026.xlsx
```

### 9.3 Consulta

El detalle del aprendiz (`GET /api/learners/{id}`) expone
`requirement_history`; cada evento incluye `decision_source`,
`conflict_fingerprint` y `note`, además de `status`, `source` y `recorded_at`.

---

## 10. Persistencia y migración

- `RequirementStatusHistory` incorpora `decision_source` y
  `conflict_fingerprint`.
- `app/database.py` agrega las columnas con `ALTER TABLE` para bases SQLite
  existentes, sin borrar datos.
- Los eventos antiguos sin huella siguen siendo legibles y se consideran
  compatibles.
- Los desempates de estado (`conflict_resolution`,
  `last_conflict_resolution`) se conservan con su flujo actual; el rediseño no
  los reemplaza, solo separa claramente los conflictos de estado de los de
  requisitos.
- La sincronización con Google Sheets distingue ambos tipos: un conflicto de
  requisitos no destraba un cruce de hojas ni al revés.

---

## 11. Escalabilidad para 200+ conflictos

- La detección es lineal por aprendiz y por campo de evidencia.
- La UI filtra en memoria y agrupa por confianza; no renderiza tarjetas fuera
  del filtro visible.
- Los grupos son plegables, conservan su estado abierto/cerrado y muestran el
  contador de pendientes aunque el volumen sea alto.
- Las acciones por lote permiten resolver cientos de casos coherentes sin abrir
  tarjeta por tarjeta.
- Solo se envían decisiones explícitas; las guardadas y automáticas no viajan
  en el payload.
- La huella corta evita comparaciones costosas y mantiene el historial legible.

---

## 12. Criterios de aceptación

| Criterio | Prueba |
| --- | --- |
| Una celda vacía es `Sin información`, no `Pendiente`. | `test_evidence_status_blank_is_missing_information_not_pending` |
| El motivo genérico no inventa un requisito. | `test_requirement_for_cause_does_not_invent_requirement` |
| La huella es estable y cambia cuando cambia el contraste. | `test_fingerprint_is_stable_and_changes_with_the_contrast` |
| TyT vacío en nivel no TGO se resuelve por regla y no bloquea. | `test_tyt_blank_non_tgo_is_auto_rule_and_does_not_block` |
| `X` + motivo faltante exige decisión y audita el origen. | `test_fulfilled_with_motive_requires_decision_and_records_audit` |
| `N.A` + motivo faltante va a revisión y no tiene sugerencia fuerte. | `test_na_with_motive_is_review_group_without_strong_suggestion` |
| Vacío + motivo que no nombra el requisito no crea conflicto. | `test_blank_without_motive_mention_does_not_create_a_conflict` |
| Vacío + motivo que nombra el requisito va a Media y audita lote. | `test_blank_with_motive_mention_is_medium_and_audits_bulk_source` |
| El resumen cuenta grupos, reglas y pendientes. | `test_summary_counts_groups_rules_and_unresolved` |
| Una decisión guardada se reaplica sin volver a preguntar. | `test_saved_decision_is_reapplied_without_asking_again` |
| Una decisión explícita vence a la guardada. | `test_explicit_decision_overrides_saved_decision` |
| Un cambio de motivo reabre el conflicto y rechaza huellas viejas. | `test_changed_motive_reopens_conflict_and_rejects_stale_fingerprint` |
| Una decisión humana vence a la regla automática y se recuerda. | `test_human_decision_on_auto_rule_is_kept_on_reimport` |
| El modal tiene grupos, filtros, acciones por lote y progreso. | `test_conflict_banner_ui.py::test_requirement_modal_has_groups_filters_batch_actions_and_progress` |
| La UI envía `source` y `fingerprint` solo para decisiones explícitas. | `test_conflict_banner_ui.py::test_requirement_conflicts_are_submitted_with_source_and_fingerprint` |
| La segunda confirmación muestra resumen y advertencia condicional de Sheets. | `test_conflict_banner_ui.py::test_second_confirmation_has_summary_and_conditional_sheets_warning` |

---

## 13. Pruebas y comandos

```bash
# Suite específica del rediseño
python3 -m pytest tests/test_requirement_conflicts.py -q

# Contrato estático de la UI
python3 -m pytest tests/test_conflict_banner_ui.py -q

# Regresiones de importación y validación
python3 -m pytest tests/test_validation_regressions.py tests/test_simplified_upload.py -q

# Suite completa
python3 -m pytest -q

# Sintaxis del JavaScript
node --check app/static/app.js
```

---

## 14. Decisiones y límites conocidos

- Las sugerencias son ayudas, no decisiones. Solo `tyt_not_applicable_level` se
  aplica automáticamente porque el propio consolidado marca Saber TyT como
  «(SOLO TGO)».
- Un conflicto `N.A` contra motivo queda en revisión porque no hay una forma
  segura de saber si el error está en la columna o en el motivo.
- Un conflicto de requisitos no dispara la advertencia de Google Sheets: esa
  advertencia pertenece al cruce de estados entre hojas.
- La app no escribe en Google Sheets; el acuse de corrección manual es solo
  documental.
- Las decisiones históricas sin huella se aceptan por compatibilidad. Las
  nuevas siempre guardan huella para poder reabrir el conflicto si el hecho
  cambia.
