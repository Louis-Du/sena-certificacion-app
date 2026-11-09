const categoryOptions = document.querySelectorAll(".category-option");
const secondaryOptions = document.querySelectorAll(".type-option");
const dropZone = document.querySelector("#drop-zone");
const fileInput = document.querySelector("#file-input");
const selectButton = document.querySelector("#select-button");
const validateButton = document.querySelector("#validate-button");
const confirmButton = document.querySelector("#confirm-button");
const cancelButton = document.querySelector("#cancel-button");
const removeButton = document.querySelector("#remove-file");
const filePanel = document.querySelector("#file-panel");
const fileName = document.querySelector("#file-name");
const fileDetails = document.querySelector("#file-details");
const fileStatus = document.querySelector("#file-status");
const feedback = document.querySelector("#feedback");
const validationPanel = document.querySelector("#validation-panel");
const validationMessage = document.querySelector("#validation-message");
const validationStatus = document.querySelector("#validation-status");
const validationChecks = document.querySelector("#validation-checks");
const cargaView = document.querySelector("#carga-view");
const importSuccessBanner = document.querySelector("#import-success-banner");
const importSuccessMeta = document.querySelector("#import-success-meta");
const newImportButton = document.querySelector("#new-import-button");
const viewImportedButton = document.querySelector("#view-imported-button");
const stepsNav = document.querySelector(".steps");
const stepElements = stepsNav ? [...stepsNav.querySelectorAll(".step")] : [];
const confirmationPanel = document.querySelector("#confirmation-panel");
const confirmSummary = document.querySelector("#confirm-summary");
const confirmFile = document.querySelector("#confirm-file");
const confirmImportable = document.querySelector("#confirm-importable");
const confirmNew = document.querySelector("#confirm-new");
const confirmUpdated = document.querySelector("#confirm-updated");
const confirmRejected = document.querySelector("#confirm-rejected");
const confirmBreakdown = document.querySelector("#confirm-breakdown");
const confirmWarnings = document.querySelector("#confirm-warnings");
const coherenceSection = document.querySelector("#coherence-conflicts");
const coherenceTitle = document.querySelector("#coherence-conflicts-title");
const coherenceList = document.querySelector("#coherence-conflict-list");
const coherenceHelp = document.querySelector("#coherence-help");
const sheetsManualCleanup = document.querySelector("#sheets-manual-cleanup");
const conflictConfirmModal = document.querySelector("#conflict-confirm-modal");
const conflictConfirmAccept = document.querySelector("#conflict-confirm-accept");
const conflictConfirmBack = document.querySelector("#conflict-confirm-back");
const missingComplementariaSection = document.querySelector("#missing-complementaria");
const acceptMissingComplementaria = document.querySelector("#accept-missing-complementaria");
const missingComplementariaHelp = document.querySelector("#missing-complementaria-help");
const historyList = document.querySelector("#history-list");
const learnersList = document.querySelector("#learners-list");
const learnersSummary = document.querySelector("#learners-summary");
const refreshLearnersButton = document.querySelector("#refresh-learners");
const learnerSearch = document.querySelector("#learner-search");
const learnerStatus = document.querySelector("#learner-status");
const learnerMissingRequirement = document.querySelector("#learner-missing-requirement");
const learnerRequirementSummary = document.querySelector("#learner-missing-requirement-summary");
const learnerRequirementOptions = document.querySelector("#learner-missing-requirement-options");
const clearLearnerSearch = document.querySelector("#clear-learner-search");
const learnersDrilldownBanner = document.querySelector("#learners-drilldown-banner");
const learnersDrilldownText = document.querySelector("#learners-drilldown-text");
const learnersDrilldownClear = document.querySelector("#learners-drilldown-clear");
const learnersPrev = document.querySelector("#learners-prev");
const learnersNext = document.querySelector("#learners-next");
const learnersPage = document.querySelector("#learners-page");
const learnerStatusChips = document.querySelector("#learner-status-chips");
const learnersFrame = document.querySelector(".learners-frame");
const learnerDetail = document.querySelector("#learner-detail");
const backToLearners = document.querySelector("#back-to-learners");
const refreshLearnerDetail = document.querySelector("#refresh-learner-detail");
const learnerDetailTitle = document.querySelector("#learner-detail-title");
const learnerDetailFeedback = document.querySelector("#learner-detail-feedback");
const learnerDetailContent = document.querySelector("#learner-detail-content");
const learnerBasicInfo = document.querySelector("#learner-basic-info");
const learnerTrackingSection = document.querySelector("#learner-tracking-section");
const learnerTracking = document.querySelector("#learner-tracking");
const learnerSourcesSection = document.querySelector("#learner-sources-section");
const learnerSources = document.querySelector("#learner-sources");
const learnerRequirements = document.querySelector("#learner-requirements");
const learnerRequirementsCompact = document.querySelector("#learner-requirements-compact");
const learnerRequirementsExpanded = document.querySelector("#learner-requirements-expanded");
const toggleRequirements = document.querySelector("#toggle-requirements");
const learnerRequirementsSubtitle = document.querySelector("#learner-requirements-subtitle");
const learnerRequirementHistory = document.querySelector("#learner-requirement-history");
const learnerMoreData = document.querySelector("#learner-more-data");
const learnerExtra = document.querySelector("#learner-extra");
const viewLinks = document.querySelectorAll("[data-view]");
const views = document.querySelectorAll(".app-view");
const maxFileSize = 20 * 1024 * 1024;
const actForm = document.querySelector("#act-form");
const actList = document.querySelector("#acts-list");
const actSearch = document.querySelector("#act-search");
const actNumberFilter = document.querySelector("#act-number-filter");
const actDateFrom = document.querySelector("#act-date-from");
const actDateTo = document.querySelector("#act-date-to");
const actStatusFilter = document.querySelector("#act-status-filter");
const actSummary = document.querySelector("#acts-summary");
const actFeedback = document.querySelector("#act-form-feedback");
const actDetail = document.querySelector("#act-detail");
const actDetailContent = document.querySelector("#act-detail-content");
const actDetailTitle = document.querySelector("#act-detail-title");
const actDetailFeedback = document.querySelector("#act-detail-feedback");
const actBasicInfo = document.querySelector("#act-basic-info");
const actLearners = document.querySelector("#act-learners");
const actLearnerForm = document.querySelector("#act-learner-form");
let currentActId = null;
const anexoForm = document.querySelector("#anexo-form");
const anexoFeedback = document.querySelector("#anexo-form-feedback");
const anexosList = document.querySelector("#anexos-list");
const anexosSummary = document.querySelector("#anexos-summary");

const conflictBanner = document.querySelector("#global-conflict-banner");
const conflictBannerText = document.querySelector("#global-conflict-text");
const conflictResolveButton = document.querySelector("#global-conflict-resolve");
const conflictLaterButton = document.querySelector("#global-conflict-later");
const CONFLICT_POLL_INTERVAL_MS = 12000;
const CONFLICT_DISMISS_KEY = "sena-conflict-banner-dismissed";
let conflictPollTimer = null;
let activeConflictFingerprint = null;
let conflictDismissedFingerprint = (() => {
  try {
    return window.sessionStorage.getItem(CONFLICT_DISMISS_KEY) || "";
  } catch (error) {
    return "";
  }
})();
let nativeNotificationFingerprint = null;
let conflictConfirmBypass = false;
let conflictResolutionLoading = false;

const importSuccessViews = {
  acta: { view: "actas", label: "Ver actas" },
  actas_completo: { view: "aprendices", label: "Ver aprendices" },
  df14a: { view: "aprendices", label: "Ver aprendices" },
  requisitos: { view: "aprendices", label: "Ver aprendices" },
};

const extensionsByType = {
  actas_completo: [".xlsx", ".xls"],
  df14a: [".xlsx", ".xls", ".csv", ".xml"],
  csv_certificacion: [".csv"],
  certificados: [".xlsx", ".xls", ".csv"],
  pendientes: [".xlsx", ".xls", ".csv"],
  complementaria: [".xlsx", ".xls"],
  meta: [".xlsx", ".xls"],
  informe: [".docx"],
  acta: [".pdf", ".docx"],
  requisitos: [".xlsx", ".xls", ".csv"],
  otro: [".xlsx", ".xls", ".csv", ".pdf", ".docx"],
};

let selectedType = "acta";
let selectedFile = null;
let validationId = null;
let missingComplementariaRequired = false;

// La fuente elegida determina el tipo de procesamiento: no hay selectores de
// subtipos. La carga de requisitos vive en la seccion secundaria.
function selectOption(button) {
  const type = button.dataset.type;
  if (!type) return;
  setType(type);
}

function resetSelection() {
  const first = categoryOptions[0];
  if (first) selectOption(first);
}

function showFeedback(message, isError = false) {
  feedback.textContent = message;
  feedback.classList.toggle("error", isError);
  feedback.classList.add("visible");
}

function clearFeedback() {
  feedback.textContent = "";
  feedback.classList.remove("visible", "error");
}

function updateAcceptedFormats() {
  const extensions = extensionsByType[selectedType];
  fileInput.accept = extensions.join(",");
  dropZone.querySelector("small").textContent = `Formatos admitidos: ${extensions.map((item) => item.slice(1).toUpperCase()).join(", ")}`;
}

const ESTADOS_PASOS = {
  seleccionar: ["active", "", ""],
  validar: ["done", "active", ""],
  confirmar: ["done", "done", "active"],
  completado: ["done", "done", "done"],
};

function setCargaStep(etapa) {
  const estados = ESTADOS_PASOS[etapa] || ESTADOS_PASOS.seleccionar;
  stepElements.forEach((step, index) => {
    step.classList.toggle("active", estados[index] === "active");
    step.classList.toggle("done", estados[index] === "done");
    if (estados[index] === "active") {
      step.setAttribute("aria-current", "step");
    } else {
      step.removeAttribute("aria-current");
    }
  });
}

function resetImportSuccessUI() {
  cargaView.classList.remove("is-import-success");
  importSuccessBanner.hidden = true;
  importSuccessMeta.textContent = "";
  viewImportedButton.hidden = true;
  viewImportedButton.textContent = "";
  delete viewImportedButton.dataset.viewTarget;
}

function setImportSuccessUI(result) {
  const records = Number(result?.records_count || 0);
  const fileNameValue = result?.file_name || selectedFile?.name || "Archivo importado";
  const countText = selectedType === "acta"
    ? `${records} ${records === 1 ? "aprendiz vinculado" : "aprendices vinculados"}`
    : `${records} ${records === 1 ? "registro procesado" : "registros procesados"}`;
  const meta = [fileNameValue, countText];
  const newRecords = Number(result?.new_records || 0);
  const updatedRecords = Number(result?.updated_records || 0);
  const warningCount = Number(result?.warning_count || 0);
  if (newRecords) meta.push(`+${newRecords} nuevos`);
  if (updatedRecords) meta.push(`${updatedRecords} actualizados`);
  if (warningCount) meta.push(`${warningCount} advertencias`);
  importSuccessMeta.textContent = meta.join(" · ");

  const destination = importSuccessViews[selectedType];
  if (destination) {
    viewImportedButton.textContent = destination.label;
    viewImportedButton.dataset.viewTarget = destination.view;
    viewImportedButton.hidden = false;
  } else {
    viewImportedButton.hidden = true;
  }

  cargaView.classList.add("is-import-success");
  importSuccessBanner.hidden = false;
  setCargaStep("completado");
  // El modal se cierra cuando confirmButton pasa a hidden; esperamos ese ciclo
  // para llevar el foco al banner y que el lector de pantalla anuncie el cierre.
  window.setTimeout(() => {
    if (cargaView.classList.contains("is-import-success")) {
      importSuccessBanner.focus({ preventScroll: false });
    }
  }, 120);
}

function startNewImport() {
  // Solo se limpia el estado de UI. El tipo de informacion se conserva para
  // que una segunda carga del mismo formato sea inmediata.
  clearFile();
  clearFeedback();
  resetImportSuccessUI();
  fileName.textContent = "";
  fileDetails.textContent = "";
  validationMessage.textContent = "";
  validationStatus.textContent = "";
  validationStatus.className = "result-badge";
  validationChecks.replaceChildren();
  window.setTimeout(() => dropZone.focus(), 0);
}

function hideReview() {
  validationPanel.hidden = true;
  confirmationPanel.hidden = true;
  resetCoherenceConflicts();
  resetMissingComplementaria();
  confirmButton.hidden = true;
  validateButton.hidden = false;
  validateButton.disabled = !selectedFile;
  validationId = null;
  cargaView.classList.remove("carga-en-revision");
  setCargaStep("seleccionar");
}

function setType(type) {
  selectedType = type;
  categoryOptions.forEach((option) => option.classList.toggle("selected", option.dataset.type === type));
  secondaryOptions.forEach((option) => option.classList.toggle("selected", option.dataset.type === type));
  updateAcceptedFormats();
  hideReview();
  if (selectedFile && !isSupported(selectedFile)) clearFile();
}

function isSupported(file) {
  const extension = `.${file.name.split(".").pop().toLowerCase()}`;
  return extensionsByType[selectedType].includes(extension);
}

function setFile(file) {
  if (!file) return;
  clearFeedback();
  hideReview();
  if (file.size > maxFileSize) {
    showFeedback("El archivo supera el limite recomendado de 20 MB.", true);
    return;
  }
  if (!isSupported(file)) {
    showFeedback(`El formato de ${file.name} no es compatible con el tipo seleccionado.`, true);
    return;
  }
  selectedFile = file;
  fileName.textContent = file.name;
  fileDetails.textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB · listo para validar`;
  fileStatus.textContent = "LISTO PARA VALIDAR";
  filePanel.hidden = false;
  validateButton.disabled = false;
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileStatus.textContent = "LISTO PARA VALIDAR";
  filePanel.hidden = true;
  hideReview();
}

function renderValidation(result) {
  validationMessage.textContent = result.message || "Validacion completada.";
  // Distingue "la validacion termino" (file-status) de "es apto para importar"
  // (este estado). Un archivo con advertencias no se presenta como aprobado.
  validationStatus.textContent = result.status === "error" ? "NO APTO" : result.status === "warning" ? "APTO CON ADVERTENCIAS" : "APTO PARA IMPORTAR";
  validationStatus.className = `result-badge ${result.status}`;
  validationChecks.replaceChildren(...result.checks.map((check) => {
    const item = document.createElement("div");
    item.className = `validation-check ${check.status}`;
    item.textContent = check.label;
    return item;
  }));
  validationPanel.hidden = false;
}

async function readResponse(response) {
  if (response.status === 204) return null;
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "No fue posible completar la operacion.");
  return result;
}

function resetCoherenceConflicts() {
  coherenceSection.hidden = true;
  coherenceTitle.textContent = "Conflictos de coherencia";
  coherenceList.replaceChildren();
  coherenceHelp.textContent = "";
  coherenceHelp.classList.remove("ready");
  closeConflictConfirmModal();
  conflictConfirmBypass = false;
  if (sheetsManualCleanup) sheetsManualCleanup.checked = false;
  confirmButton.disabled = false;
}

function resetMissingComplementaria() {
  missingComplementariaSection.hidden = true;
  missingComplementariaRequired = false;
  acceptMissingComplementaria.checked = false;
  missingComplementariaHelp.textContent = "";
  missingComplementariaHelp.classList.remove("ready");
}

function updateCoherenceState() {
  const rows = [...coherenceList.querySelectorAll(".coherence-conflict-row")];
  const pending = rows.filter((row) => !row.querySelector("input[type=radio]:checked")).length;
  const missingPending = missingComplementariaRequired && !acceptMissingComplementaria.checked;
  confirmButton.disabled = pending > 0 || missingPending;
  if (rows.length) {
    coherenceHelp.classList.toggle("ready", pending === 0);
    coherenceHelp.textContent = pending
      ? `Resuelva los ${pending} conflictos para continuar.`
      : "Todos los conflictos fueron resueltos. Puede confirmar la importación.";
  } else {
    coherenceHelp.textContent = "";
    coherenceHelp.classList.remove("ready");
  }
  if (missingPending) {
    missingComplementariaHelp.textContent = "Debe aceptar continuar sin la hoja COMPLEMENTARIA.";
    missingComplementariaHelp.classList.remove("ready");
  } else if (missingComplementariaRequired) {
    missingComplementariaHelp.textContent = "Se continuará sin formación complementaria.";
    missingComplementariaHelp.classList.add("ready");
  } else {
    missingComplementariaHelp.textContent = "";
    missingComplementariaHelp.classList.remove("ready");
  }
}

function renderCoherenceConflicts(items, { resolutions = {} } = {}) {
  resetCoherenceConflicts();
  if (!items.length) return;
  coherenceSection.hidden = false;
  coherenceTitle.textContent = `Conflictos de coherencia (${items.length})`;
  items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "coherence-conflict-row";
    row.dataset.identification = item.identification;
    const documentCell = document.createElement("strong");
    documentCell.textContent = item.identification;
    const nameCell = document.createElement("span");
    nameCell.textContent = item.name || "Nombre no disponible";
    const groupCell = document.createElement("span");
    groupCell.textContent = item.group_code ? `Ficha ${item.group_code}` : "Sin ficha";
    const options = document.createElement("div");
    options.className = "coherence-options";
    const savedResolution = String(
      resolutions[item.identification] || item.conflict_resolution || "",
    ).toUpperCase();
    [["CERTIFICADOS", "Certificado"], ["PENDIENTE", "Pendiente"]].forEach(([value, labelText]) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `coherence-${index}`;
      input.value = value;
      // Un desempate previo se muestra preseleccionado, pero el usuario puede
      // cambiarlo antes de confirmar. No se importa nada sin confirmacion.
      if (savedResolution === value) input.checked = true;
      input.addEventListener("change", updateCoherenceState);
      label.append(input, document.createTextNode(labelText));
      options.appendChild(label);
    });
    row.append(documentCell, nameCell, groupCell, options);
    coherenceList.appendChild(row);
  });
  updateCoherenceState();
}

function collectConflictResolutions() {
  return [...coherenceList.querySelectorAll(".coherence-conflict-row")]
    .map((row) => {
      const checked = row.querySelector("input[type=radio]:checked");
      return checked
        ? { identification: row.dataset.identification, status: checked.value }
        : null;
    })
    .filter(Boolean);
}

function openConflictConfirmModal() {
  if (!conflictConfirmModal) return;
  if (sheetsManualCleanup) sheetsManualCleanup.checked = false;
  conflictConfirmModal.classList.add("is-open");
  conflictConfirmModal.setAttribute("aria-hidden", "false");
  window.setTimeout(() => {
    conflictConfirmModal.querySelector(".modal-dialog")?.focus?.({ preventScroll: true });
  }, 30);
}

function closeConflictConfirmModal() {
  if (!conflictConfirmModal) return;
  conflictConfirmModal.classList.remove("is-open");
  conflictConfirmModal.setAttribute("aria-hidden", "true");
}

// #65: llevar el foco y la vista al resultado de la validación. El scroll solo
// es suave cuando el usuario no pidió reducir el movimiento.
function prefersReducedMotion() {
  return typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function revealValidationResult(element) {
  if (!element) return;
  window.requestAnimationFrame(() => {
    element.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "start",
    });
    if (typeof element.focus === "function") {
      element.focus({ preventScroll: true });
    }
  });
}

const breakdownLabels = {
  certificados: "Aprendices para certificar",
  pendientes: "Aprendices con pendientes",
  complementaria: "Registros de formación complementaria",
  meta: "Metas institucionales",
  requisitos: "Requisitos de aprendices",
  df14a: "Aprendices (Base DF14A)",
  acta: "Registros de acta",
  informe: "Tablas de informe de gestión",
  otro: "Documentos de apoyo",
};

function createBreakdownCard({ count, label, meta, warning = false, icon, extraClass = "" }) {
  const card = document.createElement("article");
  card.className = `breakdown-card ${warning ? "is-warning" : "is-ok"} ${extraClass}`.trim();

  const iconElement = document.createElement("span");
  iconElement.className = "breakdown-icon";
  iconElement.setAttribute("aria-hidden", "true");
  iconElement.textContent = icon || (warning ? "⚠" : "✓");

  const body = document.createElement("div");
  body.className = "breakdown-body";
  const headline = document.createElement("div");
  headline.className = "breakdown-headline";
  const countElement = document.createElement("strong");
  countElement.className = "breakdown-count";
  countElement.textContent = count;
  const labelElement = document.createElement("span");
  labelElement.className = "breakdown-label";
  labelElement.textContent = label;
  headline.append(countElement, document.createTextNode(" "), labelElement);
  body.appendChild(headline);

  if (meta) {
    const metaElement = document.createElement("span");
    metaElement.className = "breakdown-meta";
    metaElement.textContent = meta;
    body.appendChild(metaElement);
  }

  card.append(iconElement, body);
  return card;
}

function renderPreviewBreakdown(preview) {
  const cards = [];

  // Contexto del acta: se conserva como tarjeta informativa, separada de las
  // métricas por tipo que entrega el preview.
  if (preview.acta) {
    const acta = preview.acta;
    const details = [`Acta ${acta.number || "sin número"}`];
    if (acta.act_date) details.push(acta.act_date);
    details.push(acta.exists ? "ya registrada" : "nueva");
    // El backend puede enviar un conteo o la lista de documentos; el resumen
    // siempre muestra el conteo (antes se imprimía la lista completa, sin espacios).
    const countOf = (value) => (Array.isArray(value) ? value.length : Number(value) || 0);
    details.push(`${countOf(acta.learners_to_link)} aprendices por vincular`);
    if (countOf(acta.learners_por_certificar)) {
      details.push(`${countOf(acta.learners_por_certificar)} quedarán Por Certificar`);
    }
    if (countOf(acta.learners_already_linked)) {
      details.push(`${countOf(acta.learners_already_linked)} ya vinculados`);
    }
    if (countOf(acta.learners_not_registered)) {
      details.push(`${countOf(acta.learners_not_registered)} sin registrar`);
    }
    cards.push(createBreakdownCard({
      count: acta.number ? `Acta ${acta.number}` : "Acta",
      label: "",
      meta: details.slice(1).join(" · "),
      icon: "📋",
      extraClass: "breakdown-acta",
    }));
  }

  Object.entries(preview.breakdown || {}).forEach(([type, counts]) => {
    const valid = Number(counts?.valid_records ?? 0);
    const found = Number(counts?.records_found ?? valid);
    const rejected = Number(counts?.rejected_records ?? Math.max(found - valid, 0));
    const warning = valid !== found || rejected > 0;
    const label = breakdownLabels[type] || type;
    let meta = "";
    if (warning) {
      meta = `${found} detectados · ${rejected} rechazados`;
    }
    cards.push(createBreakdownCard({
      count: valid,
      label: label.toLowerCase(),
      meta,
      warning,
    }));
  });

  if (!cards.length) {
    const empty = document.createElement("p");
    empty.className = "breakdown-empty";
    empty.textContent = "No hay desglose por tipo para este archivo.";
    confirmBreakdown.replaceChildren(empty);
    return;
  }
  confirmBreakdown.replaceChildren(...cards);
}

function renderPreviewWarnings(warnings) {
  const items = Array.isArray(warnings) ? warnings : [];
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "confirm-warning is-ok";
    const icon = document.createElement("span");
    icon.className = "confirm-warning-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "✓";
    const text = document.createElement("span");
    text.textContent = "Sin advertencias para este archivo.";
    empty.append(icon, text);
    confirmWarnings.replaceChildren(empty);
    return;
  }
  confirmWarnings.replaceChildren(...items.map((warning) => {
    const item = document.createElement("div");
    item.className = "confirm-warning";
    const icon = document.createElement("span");
    icon.className = "confirm-warning-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "⚠";
    const text = document.createElement("span");
    text.textContent = warning;
    item.append(icon, text);
    return item;
  }));
}

async function validateFile() {
  if (!selectedFile) return;
  resetCoherenceConflicts();
  resetMissingComplementaria();
  validateButton.disabled = true;
  fileStatus.textContent = "VALIDANDO...";
  showFeedback(`Validando ${selectedType.toUpperCase()}...`);
  const formData = new FormData();
  formData.append("information_type", selectedType);
  formData.append("file", selectedFile);
  try {
    const result = await readResponse(await fetch("/api/files/validate", { method: "POST", body: formData }));
    validationId = result.validation_id;
    renderValidation(result);
    setCargaStep("validar");
    fileStatus.textContent = result.status === "error" ? "REVISAR ARCHIVO" : "VALIDACION COMPLETA";
    if (result.status === "error") {
      showFeedback("Corrige los errores antes de continuar.", true);
      revealValidationResult(validationPanel);
      return;
    }
    const preview = await readResponse(await fetch(`/api/imports/${validationId}/preview`));
    if (!preview.records_count) {
      throw new Error("El archivo no contiene registros importables. Corrige los errores y vuelve a validar.");
    }
    confirmFile.textContent = preview.file_name;
    confirmImportable.textContent = preview.records_count;
    confirmNew.textContent = preview.new_records;
    confirmUpdated.textContent = preview.updated_records;
    confirmRejected.textContent = preview.rejected_records ?? 0;
    confirmRejected.closest(".confirm-metric")?.classList.toggle(
      "has-rejected",
      Number(preview.rejected_records || 0) > 0,
    );
    renderPreviewBreakdown(preview);
    renderPreviewWarnings(preview.warnings);
    renderCoherenceConflicts(preview.coherence_conflicts || []);
    missingComplementariaRequired = Boolean(preview.missing_complementaria);
    if (missingComplementariaRequired) {
      missingComplementariaSection.hidden = false;
    }
    updateCoherenceState();
    confirmationPanel.hidden = false;
    confirmButton.hidden = false;
    validateButton.hidden = true;
    cargaView.classList.add("carga-en-revision");
    setCargaStep("confirmar");
    // El modal de revisión se abre al mostrar el panel (ui-enhancements.js).
    // Este segundo aviso deja el foco en el resumen incluso si el modal se
    // monta de forma asíncrona.
    window.setTimeout(() => revealValidationResult(confirmSummary), 60);
    showFeedback("Revisa el resumen y confirma para importar. Aun no se han guardado datos.");
  } catch (error) {
    fileStatus.textContent = "ERROR DE VALIDACION";
    showFeedback(error.message, true);
    revealValidationResult(validationPanel.hidden ? feedback : validationPanel);
  } finally {
    validateButton.disabled = false;
  }
}

async function confirmImport() {
  if (!validationId) {
    conflictConfirmBypass = false;
    return;
  }
  const resolutions = collectConflictResolutions();
  if (resolutions.length > 0 && !conflictConfirmBypass) {
    // Segunda confirmacion obligatoria: no se envia el POST hasta que el
    // usuario lea la advertencia de solo lectura y confirme de nuevo.
    openConflictConfirmModal();
    return;
  }
  conflictConfirmBypass = false;
  const isSheetsResolve = Boolean(window.__sheetsResolvePending);
  const isSheetsSync = Boolean(window.__sheetsSyncPending) || isSheetsResolve;
  confirmButton.disabled = true;
  let stopProgress = null;
  if (isSheetsSync) stopProgress = startImportPercentProgress();
  try {
    const endpoint = isSheetsResolve
      ? "/api/sheets/sync/resolve"
      : (isSheetsSync
        ? "/api/sheets/sync/confirm"
        : `/api/imports/${validationId}/confirm`);
    const payload = {
      conflict_resolutions: resolutions,
      accept_missing_complementaria: acceptMissingComplementaria.checked,
    };
    if (resolutions.length > 0) {
      payload.sheets_manual_cleanup_acknowledged = Boolean(sheetsManualCleanup?.checked);
    }
    if (isSheetsSync && !isSheetsResolve) payload.validation_id = validationId;
    const response = await readResponse(await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
    const result = isSheetsSync ? (response.result || response) : response;
    if (stopProgress) stopProgress(true);
    closeConflictConfirmModal();
    if (sheetsManualCleanup) sheetsManualCleanup.checked = false;
    fileStatus.textContent = "IMPORTACION COMPLETA";
    showFeedback(`${result.message} ${result.records_count} registros procesados.`);
    confirmButton.hidden = true;
    if (isSheetsSync) {
      window.__sheetsSyncPending = false;
      window.__sheetsResolvePending = false;
      setConflictBannerVisible(false);
      hideReview();
      window.SenaUI?.closeImportModal?.();
      await loadSheetsStatus();
    } else {
      setImportSuccessUI(result);
    }
    await loadHistory();
    await loadLearners();
  } catch (error) {
    if (stopProgress) stopProgress(false);
    showFeedback(error.message, true);
  } finally {
    if (!confirmButton.hidden) updateCoherenceState();
  }
}

const HISTORY_LIMIT = 5;
const HISTORY_TYPE_LABELS = {
  df14a: "DF14A",
  certificados: "Listado de certificados",
  pendientes: "Listado de pendientes",
  complementaria: "Formación complementaria",
  meta: "Metas oficiales",
  informe: "Informe de gestión",
  acta: "Acta de certificación",
  requisitos: "Requisitos / pendientes",
  actas_completo: "Excel institucional (ACTAS 2026)",
  csv_certificacion: "CSV alternativo",
  otro: "Otro archivo",
};

function historyTypeLabel(item) {
  const raw = item.information_type || "";
  return HISTORY_TYPE_LABELS[raw] || raw || "Importación";
}

function historyFileIcon(item) {
  const extension = String(item.file_name || "").split(".").pop().toLowerCase();
  return {
    xlsx: "▦",
    xls: "▦",
    csv: "▤",
    pdf: "▣",
    docx: "▤",
    xml: "◇",
  }[extension] || "▦";
}

function historyStatusMeta(item) {
  const errorCount = Number(item.error_count || 0);
  const warningCount = Number(item.warning_count || 0);
  const message = String(item.message || "");
  if (errorCount > 0 || /error/i.test(item.status || "")) {
    return { label: "Error", className: "is-error" };
  }
  if (/conflictos resueltos manualmente/i.test(message)) {
    return { label: "Conflictos resueltos", className: "is-resolved" };
  }
  if (warningCount > 0) {
    return { label: "Con advertencias", className: "is-warning" };
  }
  return { label: "Éxito", className: "is-success" };
}

function formatHistoryDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Fecha no disponible";
  return date.toLocaleString("es-CO", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function createHistoryMetric(value, label, className = "") {
  const metric = document.createElement("span");
  metric.className = `history-metric ${className}`.trim();
  const valueElement = document.createElement("strong");
  valueElement.textContent = value;
  metric.append(valueElement, document.createTextNode(` ${label}`));
  return metric;
}

function renderHistoryEmpty(message, isError = false) {
  const empty = document.createElement("div");
  empty.className = `history-empty ${isError ? "is-error" : ""}`.trim();
  const title = document.createElement("strong");
  title.textContent = message;
  empty.appendChild(title);
  historyList.replaceChildren(empty);
}

function renderHistoryItem(item) {
  const card = document.createElement("article");
  card.className = "history-item";

  const top = document.createElement("div");
  top.className = "history-item-top";
  const file = document.createElement("div");
  file.className = "history-file";
  const icon = document.createElement("span");
  icon.className = "history-file-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = historyFileIcon(item);
  const fileName = document.createElement("strong");
  fileName.className = "history-file-name";
  fileName.textContent = item.file_name || "Archivo sin nombre";
  fileName.title = fileName.textContent; // nombre completo al pasar el cursor
  file.append(icon, fileName);
  const status = historyStatusMeta(item);
  const statusBadge = document.createElement("span");
  statusBadge.className = `history-status ${status.className}`;
  statusBadge.textContent = status.label;
  top.append(file, statusBadge);

  const meta = document.createElement("div");
  meta.className = "history-meta";
  const typeBadge = document.createElement("span");
  typeBadge.className = "history-type-badge";
  typeBadge.textContent = historyTypeLabel(item);
  const time = document.createElement("time");
  time.setAttribute("datetime", item.imported_at || "");
  time.textContent = formatHistoryDate(item.imported_at);
  meta.append(typeBadge, time);

  const metrics = document.createElement("div");
  metrics.className = "history-metrics";
  metrics.append(
    createHistoryMetric(`+${Number(item.new_records || 0)}`, "nuevos", "is-new"),
    createHistoryMetric(Number(item.updated_records || 0), "actualizados", "is-updated"),
    createHistoryMetric(Number(item.records_count || 0), "registros", "is-total"),
  );
  if (Number(item.warning_count || 0) > 0) {
    metrics.appendChild(
      createHistoryMetric(Number(item.warning_count), "advertencias", "is-warning"),
    );
  }
  if (Number(item.rejected_records || 0) > 0) {
    metrics.appendChild(
      createHistoryMetric(Number(item.rejected_records), "rechazados", "is-danger"),
    );
  }

  const message = document.createElement("p");
  message.className = "history-message";
  message.textContent = item.message || "Importación exitosa";
  message.title = message.textContent; // mensaje completo al pasar el cursor

  card.append(top, meta, metrics, message);
  return card;
}

async function loadHistory() {
  try {
    const result = await readResponse(await fetch("/api/imports/history"));
    const items = Array.isArray(result?.items) ? result.items : [];
    if (!items.length) {
      renderHistoryEmpty("Aún no hay importaciones.");
      return;
    }
    historyList.replaceChildren(
      ...items.slice(0, HISTORY_LIMIT).map(renderHistoryItem),
    );
  } catch (error) {
    renderHistoryEmpty("No fue posible cargar el historial.", true);
  }
}

let learnerPageNumber = 1;
let learnerRequestId = 0;
const learnerPageSize = 25;
const selectedRequirementValues = new Set();
const requirementLabelsByValue = new Map();
// Drill-down desde Indicadores. ``learnerDrilldown`` conserva los filtros que no
// tienen control propio en el listado (causa y numero de acta); el estado se
// aplica al selector y el resto de filtros sigue viviendo en sus controles.
let learnerDrilldown = null;
let learnerPendingStatus = "";

function renderDrilldownBanner() {
  if (!learnersDrilldownBanner) return;
  if (!learnerDrilldown) {
    learnersDrilldownBanner.hidden = true;
    if (learnersDrilldownText) learnersDrilldownText.textContent = "";
    return;
  }
  if (learnersDrilldownText) {
    learnersDrilldownText.textContent = `Filtro desde Indicadores: ${learnerDrilldown.label}`;
  }
  learnersDrilldownBanner.hidden = false;
}

// Abre el listado con los filtros de un KPI, causa o acta de Indicadores.
// No inventa filtros: estado, causa y numero de acta son parametros reales de
// /api/learners; si un KPI no se puede representar en el padron local no se
// enlaza (caso de los certificados del consolidado ENE-SEP).
function abrirAprendicesDesdeIndicadores({ label, status = "", reasons = [], actNumber = "" }) {
  learnerDrilldown = {
    label: label || "Indicadores",
    status: status || "",
    reasons: (reasons || []).filter(Boolean),
    actNumber: actNumber || "",
  };
  learnerSearch.value = "";
  setSelectedMissingRequirements([]);
  learnerStatus.value = "";
  learnerPendingStatus = status || "";
  learnerPageNumber = 1;
  renderDrilldownBanner();
  showView("aprendices");
}

function normalizeStatusText(status) {
  return (status || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function statusChipVariant(status) {
  const normalized = normalizeStatusText(status);
  if (normalized.startsWith("certificado")) return "is-ok";
  if (normalized.startsWith("pendiente")) return "is-warning";
  if (normalized.startsWith("por certificar")) return "is-info";
  return "is-neutral";
}

function renderStatusCell(status) {
  const cell = document.createElement("td");
  const chip = document.createElement("span");
  chip.className = `status-chip ${statusChipVariant(status)}`;
  chip.textContent = status || "Sin estado";
  cell.appendChild(chip);
  return cell;
}

function statusSortRank(status) {
  const normalized = normalizeStatusText(status);
  if (normalized.startsWith("certificado")) return 0;
  if (normalized.startsWith("pendiente")) return 1;
  if (normalized.startsWith("por certificar")) return 2;
  if (normalized === "sin estado") return 3;
  return 4;
}

function statusIsActive(status) {
  if (!status) return !learnerStatus.value;
  return normalizeStatusText(learnerStatus.value) === normalizeStatusText(status);
}

function renderStatusChips(statusCounts) {
  const counts = [...(statusCounts || [])].sort(
    (left, right) =>
      statusSortRank(left.status) - statusSortRank(right.status) ||
      left.status.localeCompare(right.status),
  );
  const total = counts.reduce((sum, item) => sum + item.count, 0);
  const items = [
    { status: "", label: "Todos", count: total, variant: "is-neutral" },
    ...counts.map((item) => ({
      status: item.status,
      label: item.status,
      count: item.count,
      variant: statusChipVariant(item.status),
    })),
  ];
  learnerStatusChips.replaceChildren(
    ...items.map((item) => {
      const chip = document.createElement("button");
      chip.type = "button";
      const countLabel = `${item.count.toLocaleString("es-CO")} ${
        item.count === 1 ? "aprendiz" : "aprendices"
      }`;
      chip.className = `status-chip status-chip-button ${item.variant}`;
      chip.classList.toggle("is-active", statusIsActive(item.status));
      chip.setAttribute("aria-pressed", statusIsActive(item.status) ? "true" : "false");
      chip.setAttribute(
        "aria-label",
        item.status
          ? `Filtrar por estado ${item.label}, ${countLabel}`
          : `Mostrar todos los estados, ${countLabel}`,
      );
      chip.textContent = `${item.label} ${item.count.toLocaleString("es-CO")}`;
      chip.addEventListener("click", () => {
        const nextStatus = statusIsActive(item.status) ? "" : item.status;
        if (nextStatus && ![...learnerStatus.options].some((option) => option.value === nextStatus)) {
          learnerStatus.add(new Option(nextStatus, nextStatus));
        }
        learnerStatus.value = nextStatus;
        learnerPageNumber = 1;
        loadLearners();
      });
      return chip;
    }),
  );
}

function learnerSummaryLabel(result) {
  const total = result.total;
  const label = total === 1 ? "aprendiz" : "aprendices";
  return `${total} ${label} en la consulta actual · Página ${result.page} de ${Math.max(result.pages, 1)}`;
}

// Orden operativo de los requisitos: primero lo que falta, luego lo cumplido y
// al final lo que no aplica. "No aplica" no cuenta como falta documental.
function requirementStatusRank(status) {
  const normalized = normalizeStatusText(status);
  if (normalized === "pendiente") return 0;
  if (normalized === "cumplido") return 1;
  if (normalized === "no aplica") return 2;
  if (normalized === "sin informacion") return 3;
  return 4;
}

function requirementStatusClass(status) {
  const normalized = normalizeStatusText(status);
  if (normalized === "pendiente") return "is-pending";
  if (normalized === "cumplido") return "is-fulfilled";
  if (normalized === "no aplica") return "is-na";
  if (normalized === "sin informacion") return "is-info";
  return "is-other";
}

const requirementCategoryOrder = ["Paz y salvos", "Documentación del aprendiz", "Otros"];
const requirementCategoryAliases = {
  biblioteca: "Paz y salvos",
  "paz y salvo biblioteca": "Paz y salvos",
  bienestar: "Paz y salvos",
  almacen: "Paz y salvos",
  "paz y salvo almacen": "Paz y salvos",
  "documento de identidad": "Documentación del aprendiz",
  "documento de identidad vigente": "Documentación del aprendiz",
  identidad: "Documentación del aprendiz",
  "saber tyt": "Documentación del aprendiz",
  "t y t": "Documentación del aprendiz",
  "t&t": "Documentación del aprendiz",
  ape: "Documentación del aprendiz",
  "inscripcion ape": "Documentación del aprendiz",
  "etapa productiva": "Documentación del aprendiz",
  "formato de evaluacion de la etapa productiva": "Documentación del aprendiz",
  "certificado de la empresa": "Documentación del aprendiz",
};

function requirementCategory(item) {
  const values = [item.label, item.requirement_type].filter(Boolean);
  for (const value of values) {
    const normalized = normalizeStatusText(value).replace(/\s+/g, " ");
    if (requirementCategoryAliases[normalized]) {
      return requirementCategoryAliases[normalized];
    }
  }
  return "Otros";
}

function requirementCategorySummary(items) {
  const summary = summarizeRequirementItems(items);
  return [
    `${summary.pending.length} pendiente${summary.pending.length === 1 ? "" : "s"}`,
    `${summary.fulfilled} cumplido${summary.fulfilled === 1 ? "" : "s"}`,
    `${summary.na} no aplica`,
    `${summary.info} sin información`,
  ].join(" · ");
}

function summarizeRequirementItems(items) {
  const list = items || [];
  const pending = [];
  const fulfilledNames = [];
  const naNames = [];
  let fulfilled = 0;
  let na = 0;
  let info = 0;
  list.forEach((item) => {
    const normalized = normalizeStatusText(item.status);
    if (normalized === "pendiente") {
      pending.push(item.label || item.requirement_type || "Requisito");
    } else if (normalized === "cumplido") {
      fulfilled += 1;
      fulfilledNames.push(item.label || item.requirement_type || "Requisito");
    } else if (normalized === "no aplica") {
      na += 1;
      naNames.push(item.label || item.requirement_type || "Requisito");
    } else if (normalized === "sin informacion") {
      info += 1;
    }
  });
  return {
    total: list.length,
    pending,
    fulfilled,
    fulfilledNames,
    na,
    naNames,
    info,
    applicable: list.length - na,
    complete: list.length > 0 && pending.length === 0,
  };
}

function formatRequirementNameList(labels, limit = 3) {
  const visible = labels.slice(0, limit);
  const remaining = labels.length - visible.length;
  return `${visible.join(", ")}${remaining > 0 ? ` y ${remaining} más` : ""}`;
}

function requirementCountsText(summary) {
  const pending = summary.pending.length;
  return [
    `${pending} pendiente${pending === 1 ? "" : "s"}`,
    `${summary.fulfilled} cumplido${summary.fulfilled === 1 ? "" : "s"}`,
    `${summary.na} no aplica`,
    `${summary.info} sin información`,
  ].join(" · ");
}

function requirementSummaryTotal(summary) {
  if (Number.isFinite(Number(summary.total))) return Number(summary.total);
  const pending = (summary.pending || []).length;
  return pending + (summary.fulfilled_count || 0) + (summary.na_count || 0);
}

function documentationLabelFromSummary(summary) {
  const pending = summary.pending || [];
  const total = requirementSummaryTotal(summary);
  if (!total) return "Sin requisitos registrados";
  return pending.length
    ? `Documentación incompleta (${pending.length} pendiente${pending.length === 1 ? "" : "s"})`
    : "Documentación completa";
}

// Texto compacto de procedencia: documentación, requisitos pendientes y origen.
// Se usa como "title" para una vista rapida al pasar el cursor, sin abrir el detalle.
function learnerSummaryText(item) {
  const sources = item.data_sources || [];
  const summary = item.requirements_summary || {};
  const pending = summary.pending || [];
  const total = item.requirements_total ?? requirementSummaryTotal(summary);
  return [
    `Documentación: ${documentationLabelFromSummary(summary)}`,
    `Origen: ${sources.length ? sources.join(" · ") : "Desconocido"}`,
    `Motivo: ${item.non_certification_reason || "Sin motivo"}`,
    pending.length
      ? `Requisitos pendientes: ${pending.join(", ")}`
      : total === 0
        ? "Sin requisitos registrados"
        : "Sin requisitos pendientes",
  ].join("\n");
}

// Bloque de resumen accesible (mismo contenido del "title"), pensado para teclado
// y movil, donde no hay hover.
function renderLearnerSummaryBlock(item) {
  const sources = item.data_sources || [];
  const summary = item.requirements_summary || {};
  const pending = summary.pending || [];
  const total = item.requirements_total ?? requirementSummaryTotal(summary);
  const wrapper = document.createElement("div");
  wrapper.className = "learner-summary";
  const rows = [
    ["Documentación", documentationLabelFromSummary(summary)],
    [
      "Requisitos pendientes",
      pending.length
        ? `${pending.length}: ${formatRequirementNameList(pending, 5)}`
        : total === 0
          ? "Sin requisitos registrados"
          : "Ninguno",
    ],
    [
      "Cumplidos / No aplica",
      `${summary.fulfilled_count || 0} / ${summary.na_count || 0}`,
    ],
    ["Origen", sources.length ? sources.join(" · ") : "Desconocido"],
    ["Motivo de no certificación", item.non_certification_reason || "Sin motivo"],
  ];
  rows.forEach(([label, value]) => {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    wrapper.append(term, description);
  });
  return wrapper;
}

function updateRequirementsPanelSubtitle(summary) {
  if (!learnerRequirementsSubtitle) return;
  learnerRequirementsSubtitle.textContent = summary.total
    ? requirementCountsText(summary)
    : "Sin requisitos registrados.";
}

function renderRequirementSummary(items) {
  if (!learnerRequirementsCompact) return;
  const summary = summarizeRequirementItems(items);
  learnerRequirementsCompact.replaceChildren();
  if (!summary.total) {
    const empty = document.createElement("p");
    empty.className = "empty-detail";
    empty.textContent = "Sin requisitos registrados.";
    learnerRequirementsCompact.appendChild(empty);
    return;
  }

  const sections = [
    {
      label: "Qué falta",
      names: summary.pending,
      empty: "Ninguno pendiente",
      className: "is-pending",
    },
    {
      label: "Cumplidos",
      names: summary.fulfilledNames,
      empty: "Ninguno cumplido",
      className: "is-fulfilled",
    },
    {
      label: "No aplica",
      names: summary.naNames,
      empty: "Ninguno",
      className: "is-na",
    },
    {
      label: "Sin información",
      names: [],
      empty: summary.info ? `${summary.info} sin información` : "Ninguno",
      className: "is-info",
    },
  ];
  sections.forEach(({label, names, empty, className}) => {
    const section = document.createElement("section");
    section.className = `requirements-summary-section ${className}`;
    const heading = document.createElement("strong");
    heading.textContent = label;
    section.appendChild(heading);
    if (!names.length) {
      const message = document.createElement("span");
      message.className = "requirements-summary-empty";
      message.textContent = empty;
      section.appendChild(message);
    } else {
      const namesList = document.createElement("div");
      namesList.className = "requirements-summary-chips";
      const visibleNames = names.slice(0, 5);
      visibleNames.forEach((name) => {
        const chip = document.createElement("span");
        chip.className = "requirements-summary-chip";
        chip.textContent = name;
        namesList.appendChild(chip);
      });
      if (names.length > visibleNames.length) {
        const remaining = document.createElement("span");
        remaining.className = "requirements-summary-more";
        remaining.textContent = `y ${names.length - visibleNames.length} más`;
        namesList.appendChild(remaining);
      }
      section.appendChild(namesList);
    }
    learnerRequirementsCompact.appendChild(section);
  });
}

function renderOriginCell(item, row) {
  const cell = document.createElement("td");
  cell.className = "origin-cell-wrapper";
  // El flex debe ir en un div interno: aplicar display:flex al td lo saca del
  // layout de tabla y rompe la linea inferior de la fila.
  const content = document.createElement("div");
  content.className = "origin-cell";
  const sources = item.data_sources || [];
  const label = document.createElement("span");
  label.className = "origin-label";
  label.textContent = sources.length ? sources.join(" · ") : "Desconocido";
  const info = document.createElement("button");
  info.type = "button";
  info.className = "info-button";
  info.textContent = "Resumen";
  info.title = "Ver resumen de origen y requisitos del aprendiz";
  info.setAttribute("aria-expanded", "false");
  info.setAttribute("aria-label", `Resumen de origen y requisitos de ${item.name}`);
  info.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleLearnerSummary(row, item, info);
  });
  content.append(label, info);
  cell.appendChild(content);
  return cell;
}

// Muestra/oculta el resumen como una fila extra bajo el aprendiz. Se usa una fila
// (colspan completo) en lugar de un tooltip flotante para que no lo recorte el
// contenedor con scroll de la tabla.
function toggleLearnerSummary(row, item, button) {
  const following = row.nextElementSibling;
  if (following && following.classList.contains("learner-summary-row")) {
    following.remove();
    button.setAttribute("aria-expanded", "false");
    return;
  }
  learnersList
    .querySelectorAll(".learner-summary-row")
    .forEach((element) => element.remove());
  learnersList
    .querySelectorAll(".info-button")
    .forEach((element) => element.setAttribute("aria-expanded", "false"));
  const summaryRow = document.createElement("tr");
  summaryRow.className = "learner-summary-row";
  const cell = document.createElement("td");
  cell.colSpan = 8;
  cell.appendChild(renderLearnerSummaryBlock(item));
  summaryRow.appendChild(cell);
  row.after(summaryRow);
  button.setAttribute("aria-expanded", "true");
}

// El listado debe responder "cuántos y cuáles faltan" sin abrir la ficha.
function renderPendingRequirementsCell(item) {
  const cell = document.createElement("td");
  cell.className = "pending-requirements-cell";
  const summary = item.requirements_summary || {};
  const pending = summary.pending || [];
  const total = item.requirements_total ?? requirementSummaryTotal(summary);

  if (!pending.length) {
    const none = document.createElement("span");
    none.className = "pending-none";
    if (total === 0) {
      // Sin matriz cargada: no es lo mismo que una matriz completa sin faltantes.
      none.classList.add("is-missing");
      none.textContent = "Sin requisitos registrados";
      none.title = "Este aprendiz no tiene requisitos asociados en el sistema.";
      cell.title = "Sin requisitos registrados";
    } else {
      none.textContent = "Ninguno";
      none.title = "Sin requisitos pendientes";
      cell.title = "Sin requisitos pendientes";
    }
    cell.appendChild(none);
    return cell;
  }

  cell.classList.add("has-pending");
  const count = document.createElement("span");
  count.className = "pending-count-badge";
  count.textContent = pending.length;
  count.setAttribute(
    "aria-label",
    `${pending.length} requisito${pending.length === 1 ? "" : "s"} pendiente${pending.length === 1 ? "" : "s"}`,
  );

  const names = document.createElement("span");
  names.className = "pending-requirement-names";
  names.textContent = formatRequirementNameList(pending, 2);

  cell.append(count, names);
  cell.title = `Requisitos pendientes: ${pending.join(", ")}`;

  // El resumen corto no debe obligar a abrir la ficha para ver el resto. El
  // botón es focusable y aria-expanded anuncia el estado del listado completo.
  if (pending.length > 2) {
    const panelId = `pending-details-${item.id}`;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "pending-toggle";
    toggle.textContent = "Ver pendientes";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", panelId);

    const panel = document.createElement("ul");
    panel.className = "pending-list";
    panel.id = panelId;
    panel.hidden = true;
    pending.forEach((label) => {
      const itemLabel = document.createElement("li");
      itemLabel.textContent = label;
      panel.appendChild(itemLabel);
    });

    const setExpanded = (expanded) => {
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
      toggle.textContent = expanded ? "Ocultar pendientes" : "Ver pendientes";
      toggle.setAttribute(
        "aria-label",
        `${expanded ? "Ocultar" : "Ver"} los ${pending.length} requisitos pendientes de ${item.name}`,
      );
      panel.hidden = !expanded;
    };
    setExpanded(false);

    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      setExpanded(toggle.getAttribute("aria-expanded") !== "true");
    });

    cell.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || toggle.getAttribute("aria-expanded") !== "true") {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      setExpanded(false);
      toggle.focus();
    });

    cell.addEventListener("focusout", (event) => {
      if (
        toggle.getAttribute("aria-expanded") === "true" &&
        !cell.contains(event.relatedTarget)
      ) {
        setExpanded(false);
      }
    });

    cell.append(toggle, panel);
  }

  return cell;
}

function renderLearnerRow(item) {
  const row = document.createElement("tr");
  row.title = learnerSummaryText(item);
  const pending = (item.requirements_summary || {}).pending || [];
  row.classList.toggle("has-pending", pending.length > 0);
  const nameCell = document.createElement("td");
  nameCell.className = "learner-name-cell";
  const nameLink = document.createElement("a");
  nameLink.className = "learner-name-link";
  nameLink.href = "#aprendices";
  nameLink.textContent = item.name;
  nameLink.setAttribute("aria-label", `Ver detalles de ${item.name}`);
  nameLink.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    loadLearnerDetail(item.id);
  });
  nameCell.appendChild(nameLink);
  row.appendChild(nameCell);
  [item.identification, item.program || "Sin programa", item.group_code || "Sin ficha"]
    .forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
  row.appendChild(renderStatusCell(item.certification_status));
  row.appendChild(renderOriginCell(item, row));
  row.appendChild(renderPendingRequirementsCell(item));
  const detailCell = document.createElement("td");
  detailCell.className = "detail-cell";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "detail-button";
  button.textContent = "Ver detalles";
  button.setAttribute("aria-label", `Ver detalles de ${item.name}`);
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    loadLearnerDetail(item.id);
  });
  detailCell.appendChild(button);
  row.appendChild(detailCell);
  row.addEventListener("click", () => loadLearnerDetail(item.id));
  return row;
}

function selectedMissingRequirements() {
  return [...selectedRequirementValues];
}

function updateRequirementFilterUI() {
  const selected = selectedMissingRequirements();
  const labels = selected.map((value) => requirementLabelsByValue.get(value) || value);
  learnerRequirementSummary.textContent = labels.length ? labels.join(", ") : "Cualquiera";
  learnerRequirementSummary.title = labels.length ? labels.join(", ") : "Todos los requisitos";
  [...learnerRequirementOptions.querySelectorAll(".requirement-option")].forEach((option) => {
    const isSelected = option.dataset.value
      ? selectedRequirementValues.has(option.dataset.value)
      : selected.length === 0;
    option.classList.toggle("is-selected", isSelected);
    option.setAttribute("aria-selected", isSelected ? "true" : "false");
  });
}

function setSelectedMissingRequirements(values) {
  selectedRequirementValues.clear();
  values.filter(Boolean).forEach((value) => selectedRequirementValues.add(value));
  updateRequirementFilterUI();
}

function renderRequirementOptions(types) {
  requirementLabelsByValue.clear();
  Object.entries(types || {}).forEach(([value, label]) => {
    requirementLabelsByValue.set(value, label);
  });
  const options = [document.createElement("button")];
  options[0].type = "button";
  options[0].className = "requirement-option";
  options[0].dataset.value = "";
  options[0].setAttribute("role", "option");
  options[0].textContent = "Cualquiera";
  for (const [value, label] of requirementLabelsByValue) {
    const option = document.createElement("button");
    option.type = "button";
    option.className = "requirement-option";
    option.dataset.value = value;
    option.setAttribute("role", "option");
    option.textContent = label;
    options.push(option);
  }
  learnerRequirementOptions.replaceChildren(...options);
  updateRequirementFilterUI();
}

function learnerFiltersActive() {
  return Boolean(
    learnerSearch.value.trim() ||
      learnerStatus.value ||
      selectedMissingRequirements().length ||
      learnerDrilldown?.reasons.length ||
      learnerDrilldown?.actNumber
  );
}

function clearLearnerFilters() {
  learnerSearch.value = "";
  learnerStatus.value = "";
  setSelectedMissingRequirements([]);
  learnerDrilldown = null;
  learnerPendingStatus = "";
  renderDrilldownBanner();
  learnerPageNumber = 1;
  loadLearners();
}

function renderLearnerEmptyState() {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 8;
  cell.className = "learners-empty-cell";

  const message = document.createElement("p");
  message.className = "learners-empty-message";

  if (learnerFiltersActive()) {
    message.textContent = "No hay aprendices con estos filtros.";
    const hint = document.createElement("p");
    hint.className = "learners-empty-hint";
    hint.textContent = "Prueba con otros criterios o limpia los filtros.";
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "cancel-button";
    clear.textContent = "Limpiar filtros";
    clear.addEventListener("click", clearLearnerFilters);
    cell.append(message, hint, clear);
  } else {
    message.textContent =
      "Aún no hay aprendices cargados. Confirma una importación DF14A para empezar.";
    cell.appendChild(message);
  }

  row.appendChild(cell);
  learnersList.replaceChildren(row);
}

function setLearnerStatus(status) {
  const matchingOption = [...learnerStatus.options].find(
    (option) => option.value.toLowerCase() === status.toLowerCase(),
  );
  if (matchingOption) {
    learnerStatus.value = matchingOption.value;
    return;
  }
  learnerStatus.add(new Option(status, status));
  learnerStatus.value = status;
}

function applyRequirementEditorStatus(form, status) {
  const statusClass = requirementStatusClass(status);
  form.className = `requirement-editor ${statusClass}`;
  form.dataset.status = normalizeStatusText(status);
  const badge = form.querySelector(".requirement-state-badge");
  if (badge) {
    badge.className = `requirement-state-badge ${statusClass}`;
    badge.textContent = status;
  }
}

// Mantiene el orden "pendientes primero" despues de guardar, sin reemplazar los
// formularios (asi no se pierde el foco ni el mensaje de confirmacion).
function sortRequirementEditors() {
  const active = document.activeElement;
  learnerRequirements.querySelectorAll(".requirement-category-items").forEach((group) => {
    const forms = [...group.querySelectorAll(".requirement-editor")];
    forms
      .sort(
        (a, b) =>
          requirementStatusRank(a.dataset.status) - requirementStatusRank(b.dataset.status),
      )
      .forEach((form) => group.appendChild(form));
  });
  // Mover un formulario en el DOM puede perder el foco; si el usuario estaba
  // dentro de una fila, se restaura para no interrumpir teclado ni lectores.
  if (active && active.isConnected && learnerRequirements.contains(active)) {
    active.focus({ preventScroll: true });
  }
}

function updateRequirementCategoryCounts() {
  learnerRequirements.querySelectorAll(".requirement-category").forEach((section) => {
    const statuses = [...section.querySelectorAll(".requirement-editor")].map(
      (form) => form.dataset.status,
    );
    const items = statuses.map((status) => ({status}));
    const count = section.querySelector(".requirement-category-count");
    if (count) count.textContent = requirementCategorySummary(items);
  });
}

function renderRequirementEditor(items) {
  learnerRequirements.replaceChildren();
  if (!items.length) {
    learnerRequirements.innerHTML = "<p class=\"empty-detail\">Sin requisitos registrados.</p>";
    return;
  }

  const grouped = new Map(
    requirementCategoryOrder.map((category) => [category, []]),
  );
  items.forEach((item) => grouped.get(requirementCategory(item)).push(item));
  grouped.forEach((categoryItems, category) => {
    if (!categoryItems.length) return;
    categoryItems.sort(
      (a, b) => requirementStatusRank(a.status) - requirementStatusRank(b.status),
    );
    const section = document.createElement("section");
    section.className = "requirement-category";
    const heading = document.createElement("h4");
    heading.className = "requirement-category-title";
    heading.textContent = category;
    const count = document.createElement("span");
    count.className = "requirement-category-count";
    count.textContent = requirementCategorySummary(categoryItems);
    heading.appendChild(count);
    const group = document.createElement("div");
    group.className = "requirement-category-items";
    section.append(heading, group);
    learnerRequirements.appendChild(section);

    categoryItems.forEach((item) => {
    const label = item.label || item.requirement_type || "Requisito";
    const status = item.status || "Pendiente";
    const form = document.createElement("form");
    form.className = "requirement-editor";
    form.dataset.status = normalizeStatusText(status);
    form.dataset.category = category;
    form.innerHTML = `<div class="requirement-name"><strong></strong><span class="requirement-state-badge" aria-hidden="true"></span></div>
      <select name="status">
        <option>Pendiente</option><option>Cumplido</option><option>No aplica</option><option>Sin información</option>
      </select>
      <input type="text" name="observations" placeholder="Observación">
      <button class="primary-button" type="submit">Guardar</button>
      <span class="requirement-feedback" role="status"></span>`;

    form.querySelector(".requirement-name strong").textContent = label;
    const select = form.elements.status;
    select.setAttribute("aria-label", `Estado de ${label}`);
    const observations = form.elements.observations;
    observations.setAttribute("aria-label", `Observación de ${label}`);
    form
      .querySelector("button[type='submit']")
      .setAttribute("aria-label", `Guardar requisito ${label}`);

    applyRequirementEditorStatus(form, status);
    select.value = status;
    observations.value = item.observations || "";

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const feedback = form.querySelector(".requirement-feedback");
      feedback.textContent = "Guardando...";
      try {
        const response = await fetch(
          item.id
            ? `/api/learners/${window.currentLearnerId}/requirements/${item.id}`
            : `/api/learners/${window.currentLearnerId}/requirements`,
          {
          method: item.id ? "PATCH" : "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            requirement_type: item.requirement_type,
            status: form.elements.status.value,
            observations: form.elements.observations.value,
          }),
          },
        );
        const result = await readResponse(response);
        item.id = result.id;
        item.status = result.status;
        item.observations = result.observations;
        applyRequirementEditorStatus(form, result.status);
        sortRequirementEditors();
        updateRequirementCategoryCounts();
        const detail = await readResponse(
          await fetch(`/api/learners/${window.currentLearnerId}`),
        );
        renderRequirementHistory(detail.requirement_history);
        renderRequirementSummary(detail.requirements);
        updateRequirementsPanelSubtitle(summarizeRequirementItems(detail.requirements));
        feedback.textContent = "Guardado.";
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
      group.appendChild(form);
    });
  });
}

function renderRequirementsPanel(items) {
  const list = items || [];
  const summary = summarizeRequirementItems(list);
  renderRequirementSummary(list);
  renderRequirementEditor(list);
  updateRequirementsPanelSubtitle(summary);
  if (!toggleRequirements || !learnerRequirementsExpanded) return;

  const hasRequirements = summary.total > 0;
  toggleRequirements.hidden = !hasRequirements;
  toggleRequirements.setAttribute("aria-expanded", "false");
  toggleRequirements.textContent = `Ver todos (${summary.total})`;
  learnerRequirementsExpanded.hidden = true;
  learnerRequirementsCompact.hidden = false;
  toggleRequirements.onclick = () => {
    const expanded = toggleRequirements.getAttribute("aria-expanded") === "true";
    toggleRequirements.setAttribute("aria-expanded", expanded ? "false" : "true");
    toggleRequirements.textContent = expanded ? `Ver todos (${summary.total})` : "Recoger";
    learnerRequirementsExpanded.hidden = expanded;
    learnerRequirementsCompact.hidden = !expanded;
  };
}

function requirementSourceLabel(source) {
  if (source === "import:actas_completo") return "Importación ACTAS 2026";
  if (source === "import:requisitos") return "Importación matriz de requisitos";
  if (source === "manual") return "Edición manual";
  return source || "Origen no registrado";
}

function formatRequirementHistoryDate(value) {
  if (!value) return "Sin fecha";
  // recorded_at se guarda en UTC. Si la API entrega una fecha sin zona horaria,
  // se interpreta como UTC para evitar el desfase de 5 horas de Colombia.
  const normalized = /(Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}

function requirementStatusChipVariant(status) {
  const normalized = normalizeStatusText(status);
  if (normalized === "cumplido") return "is-ok";
  if (normalized === "pendiente") return "is-warning";
  return "is-neutral";
}

function renderRequirementHistory(items) {
  learnerRequirementHistory.replaceChildren();
  if (!items || !items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-detail";
    empty.textContent = "Aún no hay cambios de requisitos registrados.";
    learnerRequirementHistory.appendChild(empty);
    return;
  }
  const list = document.createElement("div");
  list.className = "requirement-history-list";

  const header = document.createElement("div");
  header.className = "requirement-history-header";
  header.setAttribute("aria-hidden", "true");
  ["Fecha", "Requisito", "Origen", "Estado"].forEach((title) => {
    const cell = document.createElement("span");
    cell.textContent = title;
    header.appendChild(cell);
  });
  list.appendChild(header);

  items.forEach((event) => {
    const row = document.createElement("div");
    row.className = "requirement-history-row";

    const when = document.createElement("time");
    when.className = "requirement-history-date";
    when.dateTime = event.recorded_at || "";
    when.textContent = formatRequirementHistoryDate(event.recorded_at);

    const req = document.createElement("span");
    req.className = "requirement-history-req";
    req.textContent = event.requirement_label || event.requirement_type || "Requisito";

    const source = document.createElement("span");
    source.className = "requirement-history-source";
    source.textContent = requirementSourceLabel(event.source);

    const status = document.createElement("span");
    status.className = `status-chip ${requirementStatusChipVariant(event.status)}`;
    status.textContent = event.status || "Sin estado";

    row.append(when, req, source, status);
    if (event.note) {
      const note = document.createElement("span");
      note.className = "requirement-history-note";
      note.textContent = event.note;
      row.appendChild(note);
    }
    list.appendChild(row);
  });
  learnerRequirementHistory.appendChild(list);
}

function fillDetailList(container, entries) {
  container.replaceChildren();
  entries.forEach(([label, value]) => {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value || "No disponible";
    container.append(term, description);
  });
}

async function loadLearnerDetail(learnerId) {
  learnersFrame.hidden = true;
  learnerDetail.hidden = false;
  learnerDetailContent.hidden = true;
  learnerDetailFeedback.textContent = "Consultando...";
  // Al entrar al detalle, el header sticky queda arriba de la ficha.
  try {
    const reduce = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    learnerDetail.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  } catch (_) {}
  try {
    const result = await readResponse(await fetch(`/api/learners/${learnerId}`));
    window.currentLearnerId = learnerId;
    const info = result.basic_info;
    learnerDetailTitle.textContent = info.name || "Detalle";
    fillDetailList(learnerBasicInfo, [
      ["Documento", info.identification],
      ["Programa", info.program],
      ["Ficha", info.group_code],
      ["Nivel de formación", info.training_type],
      ["Estado", info.certification_status],
    ]);
    // Seguimiento de certificacion: el motivo (PENDIENTES) y los datos de
    // contacto solo se muestran si el archivo los aporto; no se rellenan.
    const trackingEntries = [
      ["Motivo de no certificación", info.non_certification_reason],
      ["Instructor de seguimiento", info.instructor],
      ["N° de acta", info.act_number],
      ["Correo", info.email],
      ["Teléfono", info.phone],
      ["Mes de certificación", info.certification_month],
      ["Recibido en admon. educativa", info.administrative_receipt_date],
    ].filter(([, value]) => value);
    learnerTrackingSection.hidden = trackingEntries.length === 0;
    if (trackingEntries.length) {
      fillDetailList(learnerTracking, trackingEntries);
    }
    // Origen de los datos: fuentes reales registradas en la importacion. Si no
    // hay, se muestra "Desconocido"; nunca se inventa de que archivo salio.
    const sources = info.data_sources || [];
    learnerSourcesSection.hidden = false;
    fillDetailList(learnerSources, [
      ["Fuente(s) de origen", sources.length ? sources.join(" · ") : "Desconocido"],
    ]);
    renderRequirementsPanel(result.requirements);
    renderRequirementHistory(result.requirement_history);
    const dates = result.dates || {};
    const extraEntries = [
      ["Inicio de ficha", dates.start_date],
      ["Terminación de ficha", dates.termination_date],
    ].filter(([, value]) => value);
    learnerMoreData.hidden = extraEntries.length === 0;
    if (extraEntries.length) {
      fillDetailList(learnerExtra, extraEntries);
    }
    learnerDetailFeedback.textContent = "";
    learnerDetailContent.hidden = false;
    // Al abrir la ficha, el foco queda en el nombre para que el lector de
    // pantalla anuncie el contexto sin obligar a recorrer toda la pagina.
    try {
      learnerDetailTitle.focus({ preventScroll: true });
    } catch (_) {
      learnerDetailTitle.focus();
    }
  } catch (error) {
    learnerDetailFeedback.textContent = error.message;
  }
}

async function loadLearners() {
  const requestId = ++learnerRequestId;
  learnersSummary.textContent = "Consultando...";
  learnersList.setAttribute("aria-busy", "true");
  learnersPrev.disabled = true;
  learnersNext.disabled = true;
  try {
    // El estado del drill-down se aplica cuando el selector ya tiene sus
    // opciones; hasta entonces se envia directo a la API.
    const selectedStatus = learnerPendingStatus || learnerStatus.value;
    const params = new URLSearchParams({
      search: learnerSearch.value.trim(),
      status: selectedStatus,
      page: learnerPageNumber,
      page_size: learnerPageSize,
    });
    selectedMissingRequirements().forEach((value) => {
      params.append("missing_requirement", value);
    });
    (learnerDrilldown?.reasons || []).forEach((value) => {
      params.append("reason", value);
    });
    if (learnerDrilldown?.actNumber) {
      params.set("act_number", learnerDrilldown.actNumber);
    }
    const result = await readResponse(await fetch(`/api/learners?${params}`));
    if (requestId !== learnerRequestId) return;
    const statusOptions = [...result.statuses];
    if (
      (result.status_counts || []).some((item) => item.status === "Sin estado") &&
      !statusOptions.includes("Sin estado")
    ) {
      statusOptions.push("Sin estado");
    }
    if (
      selectedStatus &&
      !statusOptions.some((status) => status.toLowerCase() === selectedStatus.toLowerCase())
    ) {
      statusOptions.push(selectedStatus);
    }
    learnerStatus.replaceChildren(new Option("Todos los estados", ""));
    statusOptions.forEach((status) => learnerStatus.add(new Option(status, status)));
    if (selectedStatus) setLearnerStatus(selectedStatus);
    learnerPendingStatus = "";
    // Opciones del filtro "Requisito faltante" segun los tipos del backend.
    renderRequirementOptions(result.requirement_types);
    renderStatusChips(result.status_counts);

    if (!result.items.length) {
      learnersSummary.textContent =
        result.total === 0
          ? "0 aprendices en la consulta actual · Sin resultados"
          : learnerSummaryLabel(result);
      learnersPage.textContent = "Sin resultados";
      renderLearnerEmptyState();
      return;
    }

    learnersSummary.textContent = learnerSummaryLabel(result);
    learnersPage.textContent = `Página ${result.page} de ${Math.max(result.pages, 1)}`;
    learnersPrev.disabled = result.page <= 1;
    learnersNext.disabled = result.page >= result.pages;
    learnersList.replaceChildren(...result.items.map(renderLearnerRow));
  } catch (error) {
    if (requestId !== learnerRequestId) return;
    learnersSummary.textContent = "No fue posible consultar SQLite";
    learnersPage.textContent = "Sin resultados";
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.className = "learners-empty-cell";
    cell.textContent = "No fue posible cargar los aprendices.";
    row.appendChild(cell);
    learnersList.replaceChildren(row);
  } finally {
    if (requestId === learnerRequestId) {
      learnersList.removeAttribute("aria-busy");
    }
  }
}

backToLearners.addEventListener("click", () => {
  learnerDetail.hidden = true;
  learnersFrame.hidden = false;
});

refreshLearnerDetail?.addEventListener("click", () => {
  if (window.currentLearnerId) {
    loadLearnerDetail(window.currentLearnerId);
  }
});
learnerSearch.addEventListener("input", () => {
  learnerPageNumber = 1;
  loadLearners();
});
clearLearnerSearch.addEventListener("click", clearLearnerFilters);
learnersDrilldownClear?.addEventListener("click", clearLearnerFilters);
learnerStatus.addEventListener("change", () => {
  learnerPageNumber = 1;
  loadLearners();
});
learnerRequirementOptions.addEventListener("click", (event) => {
  const option = event.target.closest(".requirement-option");
  if (!option) return;
  event.preventDefault();
  const value = option.dataset.value;
  if (!value) {
    selectedRequirementValues.clear();
  } else if (selectedRequirementValues.has(value)) {
    selectedRequirementValues.delete(value);
  } else {
    selectedRequirementValues.add(value);
  }
  updateRequirementFilterUI();
  learnerPageNumber = 1;
  loadLearners();
});
document.addEventListener("click", (event) => {
  if (!learnerMissingRequirement.contains(event.target)) {
    learnerMissingRequirement.open = false;
  }
});
learnerMissingRequirement.addEventListener("toggle", () => {
  learnerRequirementSummary.setAttribute(
    "aria-expanded",
    learnerMissingRequirement.open ? "true" : "false",
  );
});
learnersPrev.addEventListener("click", () => {
  if (learnerPageNumber > 1) {
    learnerPageNumber -= 1;
    loadLearners();
  }
});
learnersNext.addEventListener("click", () => {
  learnerPageNumber += 1;
  loadLearners();
});

function replaceLocationHash(hash) {
  // Algunos bloqueadores (p. ej. Malwarebytes Browser Guard) interceptan
  // history.replaceState y lanzan "Breaking Browser Locker Behavior detected".
  // El cambio de vista no debe depender de esa API: si falla, la navegacion
  // interna sigue funcionando y la URL simplemente conserva su valor.
  if (window.location.hash === hash) return;
  try {
    history.replaceState(null, "", hash);
  } catch (error) {
    // Silencioso a proposito: es una mejora cosmetica de la URL.
  }
}

function showView(viewName, updateHash = true) {
  const target = ["aprendices", "actas", "indicadores", "anexos"].includes(viewName) ? viewName : "carga";
  views.forEach((view) => {
    view.hidden = view.id !== `${target}-view`;
  });
  viewLinks.forEach((link) => link.classList.toggle("active", link.dataset.view === target));
  if (updateHash) replaceLocationHash(`#${target}`);
  if (target === "aprendices") loadLearners();
  if (target === "actas") loadActs();
  if (target === "indicadores") loadIndicadores();
  if (target === "anexos") loadAnexos();
}

// ---------------------------------------------------------------------------
// Indicadores: como mostrar valores que el backend NO pudo calcular
// ---------------------------------------------------------------------------
// El backend devuelve ``null`` cuando un indicador no se puede calcular (por
// ejemplo, falta cargar la hoja de metas o la de pendientes). Ese ``null`` NO
// significa cero, asi que aqui se muestra un guion o "No calculable" en lugar
// de una cifra falsa.
function formatNumeroIndicador(valor) {
  if (valor === null || valor === undefined) return "—";
  return Number(valor).toLocaleString("es-CO");
}

function formatPorcentajeIndicador(valor) {
  if (valor === null || valor === undefined) return "No calculable";
  return `${valor}%`;
}

// ---------------------------------------------------------------------------
// Indicadores: graficos (Chart.js)
// ---------------------------------------------------------------------------
// Los graficos son un COMPLEMENTO de las tablas existentes: reutilizan
// exactamente los mismos datos que ya entrega el backend (``metricas`` para el
// avance por categoria y ``motivos`` para las causas). Aqui NO se calcula ni se
// inventa ninguna metrica nueva.
const COLOR_IND_CERTIFICADOS = "#15945d"; // verde
const COLOR_IND_META = "#6b8ba4";         // azul grisaceo (linea del 100%)
const COLOR_IND_PROBLEMA = "#c0554f";     // rojo (causas / problemas)

// Las instancias se conservan para destruirlas antes de redibujar; si no,
// Chart.js reutiliza el canvas y los datos se duplican al pulsar "Actualizar".
let graficoAvance = null;
let graficoCausas = null;

// Alterna entre el canvas y el mensaje de estado vacio dentro del mismo panel.
// Devuelve ``true`` solo cuando corresponde dibujar el grafico.
function alternarPanelGrafico(canvas, mensajeVacio, textoVacio) {
  const contenedor = canvas.parentElement;
  if (typeof Chart === "undefined") {
    canvas.hidden = true;
    mensajeVacio.hidden = false;
    mensajeVacio.textContent = "No se pudo cargar la librería de gráficos (Chart.js).";
    contenedor.style.height = "";
    return false;
  }
  if (!textoVacio) {
    canvas.hidden = false;
    mensajeVacio.hidden = true;
    return true;
  }
  canvas.hidden = true;
  mensajeVacio.hidden = false;
  mensajeVacio.textContent = textoVacio;
  contenedor.style.height = "";
  return false;
}

// Barra de progreso de los KPI de porcentaje. El ancho se limita a 100% para
// que un avance superior (por ejemplo 120%) no rompa la barra, pero el numero
// mostrado conserva siempre el valor real.
function kpiBarraProgreso(valor) {
  if (valor === null || valor === undefined) {
    return '<div class="kpi-progress is-empty"><div class="kpi-progress-track"></div></div>';
  }
  const ancho = Math.max(0, Math.min(100, Number(valor)));
  return `<div class="kpi-progress"><div class="kpi-progress-track"><span class="kpi-progress-fill" style="width:${ancho}%"></span></div></div>`;
}

// Linea punteada en el 100% de la meta. Solo se dibuja cuando la escala visible
// la incluye; si todas las categorias estan muy por debajo, la escala se ajusta
// al mayor avance y la linea quedaria fuera del area del grafico.
const lineaMeta100 = {
  id: "lineaMeta100",
  afterDatasetsDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    if (!scales.x || scales.x.max < 100) return;
    const x = scales.x.getPixelForValue(100);
    ctx.save();
    ctx.strokeStyle = COLOR_IND_META;
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.stroke();
    ctx.restore();
  },
};

// Rotulo con el valor exacto al final de cada barra. Es necesario porque una
// categoria puede tener un % muy pequeno y su barra seria casi invisible.
const etiquetasAvance = {
  id: "etiquetasAvance",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    chart.data.datasets.forEach((dataset, indiceDataset) => {
      const meta = chart.getDatasetMeta(indiceDataset);
      if (meta.hidden) return;
      meta.data.forEach((barra, indice) => {
        const valor = dataset.data[indice];
        if (valor === null || valor === undefined) return;
        ctx.save();
        ctx.fillStyle = "#0f3c28";
        ctx.font = "600 11px system-ui, sans-serif";
        ctx.textBaseline = "middle";
        ctx.fillText(`${valor}%`, barra.x + 6, barra.y);
        ctx.restore();
      });
    });
  },
};

// Parte las etiquetas largas en varias lineas: en la columna del grafico los
// nombres de categoria no caben en una sola linea.
function partirEtiqueta(texto, maximo = 24) {
  if (texto.length <= maximo) return texto;
  const lineas = [];
  let actual = "";
  texto.split(" ").forEach((palabra) => {
    if (actual && `${actual} ${palabra}`.length > maximo) {
      lineas.push(actual);
      actual = palabra;
    } else {
      actual = actual ? `${actual} ${palabra}` : palabra;
    }
  });
  if (actual) lineas.push(actual);
  return lineas;
}

// Grafico 1: % de Avance por categoria (Certificados / Meta * 100).
// Se abandono la comparacion de valores absolutos en un mismo eje porque la meta
// de Formacion Complementaria (decenas de miles) aplastaba a las demas
// categorias, cuyas metas son de cientos o miles.
function renderAvanceChart(metricas) {
  const canvas = document.querySelector("#indicadores-avance-chart");
  const vacio = document.querySelector("#indicadores-avance-empty");
  if (!canvas || !vacio) return;

  if (graficoAvance) { graficoAvance.destroy(); graficoAvance = null; }

  // Solo las categorias con avance calculable: sin meta no hay porcentaje.
  const filas = (metricas || []).filter((m) => m.avance !== null && m.avance !== undefined);

  if (!alternarPanelGrafico(canvas, vacio, filas.length ? "" : "Sin datos cargados")) return;

  graficoAvance = new Chart(canvas.getContext("2d"), {
    type: "bar",
    data: {
      labels: filas.map((m) => m.category_label),
      datasets: [
        {
          label: "% Avance",
          data: filas.map((m) => m.avance),
          backgroundColor: COLOR_IND_CERTIFICADOS,
          borderRadius: 4,
          maxBarThickness: 30,
        },
      ],
    },
    options: {
      indexAxis: "y", // barras horizontales: los nombres de categoria son largos
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: 52 } }, // espacio para el rotulo del valor
      scales: {
        x: { beginAtZero: true, maxTicksLimit: 6, ticks: { callback: (valor) => `${valor}%` } },
        y: { ticks: { autoSkip: false, callback: (valor, indice) => partirEtiqueta(filas[indice] ? filas[indice].category_label : valor) } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `% Avance: ${ctx.parsed.x}%`,
            // El detalle absoluto acompania al porcentaje en el mismo tooltip.
            afterLabel: (ctx) => {
              const m = filas[ctx.dataIndex];
              return [
                `Meta: ${formatNumeroIndicador(m.meta)}`,
                `Certificados: ${formatNumeroIndicador(m.certificados)}`,
                `Pendientes: ${formatNumeroIndicador(m.pendientes)}`,
              ];
            },
          },
        },
      },
    },
    plugins: [lineaMeta100, etiquetasAvance],
  });
}

// Grafico 2: barras horizontales de causas de no certificacion. La altura del
// panel crece con el numero de causas para que ninguna quede aplastada.
function renderCausasChart(motivos, onSelect) {
  const canvas = document.querySelector("#indicadores-causas-chart");
  const vacio = document.querySelector("#indicadores-causas-empty");
  if (!canvas || !vacio) return;

  if (graficoCausas) { graficoCausas.destroy(); graficoCausas = null; }

  const filas = motivos || [];
  if (!alternarPanelGrafico(canvas, vacio, filas.length ? "" : "Aún no hay causas registradas")) return;

  // Altura acotada: con Top 10 + "Otras" el grafico no crece sin limite.
  canvas.parentElement.style.height = `${Math.max(240, Math.min(460, filas.length * 34 + 40))}px`;

  graficoCausas = new Chart(canvas.getContext("2d"), {
    type: "bar",
    data: {
      labels: filas.map((m) => m.motivo),
      datasets: [
        {
          label: "Incidencias",
          data: filas.map((m) => m.cantidad),
          backgroundColor: COLOR_IND_PROBLEMA,
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const fila = filas[ctx.dataIndex];
              const porcentaje = fila.porcentaje === null || fila.porcentaje === undefined
                ? "—"
                : `${fila.porcentaje}%`;
              return `${fila.cantidad.toLocaleString("es-CO")} incidencias (${porcentaje} del total)`;
            },
          },
        },
      },
      onClick: (event, elements) => {
        if (!elements.length || typeof onSelect !== "function") return;
        const fila = filas[elements[0].index];
        if (fila) onSelect(fila);
      },
      onHover: (event, elements) => {
        if (canvas) canvas.style.cursor = elements.length ? "pointer" : "default";
      },
    },
  });
}

// Limpia los graficos cuando la carga falla o la vista se vacia, para no dejar
// visualizaciones de datos anteriores.
function limpiarGraficosIndicadores() {
  if (graficoAvance) { graficoAvance.destroy(); graficoAvance = null; }
  if (graficoCausas) { graficoCausas.destroy(); graficoCausas = null; }
  const avance = document.querySelector("#indicadores-avance-chart");
  const avanceVacio = document.querySelector("#indicadores-avance-empty");
  if (avance && avanceVacio) alternarPanelGrafico(avance, avanceVacio, "Sin datos cargados");
  const causas = document.querySelector("#indicadores-causas-chart");
  const causasVacio = document.querySelector("#indicadores-causas-empty");
  if (causas && causasVacio) alternarPanelGrafico(causas, causasVacio, "Aún no hay causas registradas");
}

// Pestañas de la zona inferior de Indicadores (Causas / Actas). Reorganizan el
// contenido complementario para reducir el desplazamiento vertical sin ocultar
// informacion: todo sigue a un clic de distancia.
function activarTabIndicadores(nombre) {
  document.querySelectorAll(".indicadores-tabs .tab-button").forEach((boton) => {
    const activo = boton.dataset.tab === nombre;
    boton.classList.toggle("is-active", activo);
    boton.setAttribute("aria-selected", String(activo));
  });
  document.querySelectorAll(".indicadores-tabs .tab-panel").forEach((panel) => {
    panel.hidden = panel.dataset.tab !== nombre;
  });
  // Chart.js mide el lienzo cuando se crea; si el panel estaba oculto el ancho
  // es 0, asi que al mostrarlo hay que pedirle que recalcule.
  if (nombre === "causas" && graficoCausas) graficoCausas.resize();
}

document.querySelectorAll(".indicadores-tabs .tab-button").forEach((boton) => {
  boton.addEventListener("click", () => activarTabIndicadores(boton.dataset.tab));
});

// ---------------------------------------------------------------------------
// Causas: el backend entrega etiquetas canonicas atomicas. El frontend solo
// limita el grafico; la tabla conserva el desglose completo.
// ---------------------------------------------------------------------------
function agruparMotivos(motivos, limite = null) {
  const mapa = new Map();
  (motivos || []).forEach((item) => {
    const cantidad = Number(item.cantidad) || 0;
    if (cantidad <= 0) return;
    const label = item.motivo;
    const actual = mapa.get(label) || { motivo: label, cantidad: 0, variantes: [] };
    actual.cantidad += cantidad;
    if (item.motivo && !actual.variantes.includes(item.motivo)) {
      actual.variantes.push(item.motivo);
    }
    mapa.set(label, actual);
  });

  const total = [...mapa.values()].reduce((acumulado, item) => acumulado + item.cantidad, 0);
  const filas = [...mapa.values()]
    .sort((a, b) => b.cantidad - a.cantidad)
    .map((item) => ({
      ...item,
      porcentaje: total ? Math.round((item.cantidad / total) * 1000) / 10 : null,
    }));

  if (!limite || filas.length <= limite) {
    return { filas, resto: null, total, agrupadas: filas.filter((f) => f.variantes.length > 1).length };
  }

  const principales = filas.slice(0, limite);
  const restoFilas = filas.slice(limite);
  const restoCantidad = restoFilas.reduce((acumulado, item) => acumulado + item.cantidad, 0);
  principales.push({
    motivo: `Otras causas (${restoFilas.length})`,
    cantidad: restoCantidad,
    porcentaje: total ? Math.round((restoCantidad / total) * 1000) / 10 : null,
    variantes: restoFilas.map((item) => item.motivo),
    agrupada: true,
  });
  return {
    filas: principales,
    resto: { count: restoFilas.length, cantidad: restoCantidad },
    total,
    agrupadas: filas.filter((f) => f.variantes.length > 1).length,
  };
}

function textoAuditoriaCausas(data) {
  const incidencias = Number(data.total_incidencias_causas) || 0;
  const pendientes = data.total_pendientes;
  if (pendientes === null || pendientes === undefined) {
    return `◈ <strong>Auditoría de consistencia:</strong> hay <strong>${formatNumeroIndicador(incidencias)}</strong> incidencias de causas registradas. Cargue la hoja PENDIENTES para compararlas con el total de aprendices únicos.`;
  }
  const personas = Number(pendientes);
  const diferencia = incidencias - personas;
  let explicacion;
  if (diferencia > 0) {
    explicacion = `Hay <strong>${formatNumeroIndicador(diferencia)}</strong> incidencias adicionales porque una misma persona puede tener varias causas sin superar; no significa que haya más aprendices pendientes.`;
  } else if (diferencia === 0) {
    explicacion = "Las incidencias coinciden con las personas: cada aprendiz registra una sola causa.";
  } else {
    const sinMotivo = Number(data.aprendices_pendientes_sin_motivo) || 0;
    explicacion = `Las incidencias son <strong>${formatNumeroIndicador(Math.abs(diferencia))}</strong> menos que las personas porque hay aprendices sin causa registrada en la hoja PENDIENTES${sinMotivo ? ` (${formatNumeroIndicador(sinMotivo)} sin motivo)` : ""}.`;
  }
  const multiples = Number(data.aprendices_con_causas_multiples) || 0;
  const detalleMultiples = multiples
    ? ` ${formatNumeroIndicador(multiples)} aprendices registran más de una causa.`
    : "";
  return `◈ <strong>Auditoría de consistencia:</strong> <strong>${formatNumeroIndicador(personas)}</strong> aprendices únicos pendientes y <strong>${formatNumeroIndicador(incidencias)}</strong> incidencias de causas. ${explicacion}${detalleMultiples}`;
}

// ---------------------------------------------------------------------------
// Actas del periodo: columnas condicionales.
// La hoja CERTIFICADOS solo trae el numero de acta; si el modulo Actas tiene el
// acta registrada se completan fecha/tipo y se ofrece enlace al detalle. Si no
// hay dato para toda una columna, se oculta en lugar de mostrar "No disponible"
// en todas las filas.
// ---------------------------------------------------------------------------
function renderActasIndicadores(data, tabla, resumen, nota) {
  const actas = Array.isArray(data.ultimas_actas) ? data.ultimas_actas : [];
  const thFecha = document.querySelector("#indicadores-actas-date-th");
  const thTipo = document.querySelector("#indicadores-actas-type-th");
  const thDetalle = document.querySelector("#indicadores-actas-link-th");
  if (!tabla) return;

  const hayFilas = actas.length > 0;
  const conFecha = actas.some((acta) => Boolean(acta.act_date));
  const conTipo = actas.some((acta) => Boolean(acta.act_type));
  const conDetalle = actas.some((acta) => acta.act_id !== null && acta.act_id !== undefined);
  const ocultarFecha = !hayFilas || !conFecha;
  const ocultarTipo = !hayFilas || !conTipo;
  const ocultarDetalle = !hayFilas || !conDetalle;

  if (thFecha) thFecha.hidden = ocultarFecha;
  if (thTipo) thTipo.hidden = ocultarTipo;
  if (thDetalle) thDetalle.hidden = ocultarDetalle;

  if (resumen) {
    const totalAprendices = actas.reduce((acumulado, acta) => acumulado + (Number(acta.aprendices_count) || 0), 0);
    resumen.textContent = hayFilas
      ? `${actas.length} actas distintas en el consolidado · ${formatNumeroIndicador(totalAprendices)} certificados asociados`
      : "Sin actas distintas en la hoja CERTIFICADOS para el período";
  }

  if (nota) {
    const avisos = [];
    if (ocultarFecha && ocultarTipo) {
      avisos.push("El consolidado solo trae el número de acta: la fecha y el tipo no vienen en la hoja CERTIFICADOS, por eso se ocultan esas columnas.");
    } else {
      if (ocultarFecha) avisos.push("La fecha no viene en el consolidado; se oculta la columna.");
      if (ocultarTipo) avisos.push("El tipo no viene en el consolidado; se oculta la columna.");
    }
    if (conDetalle) avisos.push("Las actas registradas en el módulo Actas incluyen enlace a su detalle.");
    nota.innerHTML = avisos.join(" ");
    nota.hidden = !avisos.length;
  }

  if (!hayFilas) {
    tabla.innerHTML = `<tr><td colspan="2" style="color:var(--muted)">Sin actas adicionales en la base de datos en este período.</td></tr>`;
    return;
  }

  tabla.innerHTML = actas.map((acta) => {
    // Drill-down P1: numero de acta -> aprendices con ese acta en el padron.
    const celdas = [`<td><button class="drilldown-link" type="button" data-acta-number="${acta.number}" title="Ver aprendices del acta ${acta.number}">${acta.number}</button></td>`];
    if (!ocultarFecha) celdas.push(`<td>${acta.act_date || "No disponible"}</td>`);
    if (!ocultarTipo) celdas.push(`<td>${acta.act_type || "No disponible"}</td>`);
    celdas.push(`<td style="color:var(--green-dark);font-weight:700">${formatNumeroIndicador(acta.aprendices_count)} asociados</td>`);
    if (!ocultarDetalle) {
      celdas.push(
        acta.act_id !== null && acta.act_id !== undefined
          ? `<td><button class="act-link-button" type="button" data-act-id="${acta.act_id}" aria-label="Ver detalle del acta ${acta.number}">Ver</button></td>`
          : "<td>—</td>"
      );
    }
    return `<tr>${celdas.join("")}</tr>`;
  }).join("");

  tabla.querySelectorAll("button[data-act-id]").forEach((boton) => {
    boton.addEventListener("click", () => {
      const id = Number(boton.dataset.actId);
      if (!Number.isFinite(id)) return;
      showView("actas");
      if (typeof loadActDetail === "function") loadActDetail(id);
    });
  });

  tabla.querySelectorAll("button[data-acta-number]").forEach((boton) => {
    boton.addEventListener("click", () => {
      const numero = boton.dataset.actaNumber;
      if (!numero) return;
      abrirAprendicesDesdeIndicadores({
        label: `acta ${numero}`,
        actNumber: numero,
      });
    });
  });
}

async function loadIndicadores() {
  const kpis = document.querySelector("#indicadores-kpis");
  const avisos = document.querySelector("#indicadores-avisos");
  const table = document.querySelector("#indicadores-table");
  const causasTable = document.querySelector("#indicadores-causas-table");
  const causasSummary = document.querySelector("#indicadores-causas-summary");
  const causasNote = document.querySelector("#indicadores-causas-note");
  const actasTable = document.querySelector("#indicadores-actas-table");
  const actasSummary = document.querySelector("#indicadores-actas-summary");
  const causasCount = document.querySelector("#indicadores-causas-count");
  const actasCount = document.querySelector("#indicadores-actas-count");
  if (!kpis || !table) return;

  try {
    const data = await readResponse(await fetch("/api/indicadores"));
    const personasCertificadas = data.certificados_personas ?? data.total_certificados;
    const personasPendientes = data.pendientes_personas ?? data.total_pendientes;
    const notaComplementaria = Number(data.certificados_complementaria) > 0
      ? ` · Excluye ${formatNumeroIndicador(data.certificados_complementaria)} certificados agregados de formación complementaria.`
      : " · Solo personas del consolidado (titulada).";
    kpis.innerHTML = `
      <div class="panel"><div><small>META ANUAL INSTITUCIONAL</small><h2>${formatNumeroIndicador(data.total_meta)}</h2><small>Aprendices proyectados por la meta</small></div></div>
      <div class="panel" style="background:var(--green-soft)"><div><small style="color:var(--green-dark)">% AVANCE</small><h2 style="color:var(--green-dark)">${formatPorcentajeIndicador(data.avance_global)}</h2>${kpiBarraProgreso(data.avance_global)}<small class="kpi-formula" title="Certificados de todas las categorías ÷ meta anual × 100">Fórmula: certificados ÷ meta (todas las categorías)</small></div></div>
      <div class="panel"><div><small>EFECTIVIDAD DE PERSONAS</small><h2>${formatPorcentajeIndicador(data.efectividad_global)}</h2>${kpiBarraProgreso(data.efectividad_global)}<small class="kpi-formula" title="Certificados de personas ÷ (certificados de personas + pendientes de personas) × 100">Fórmula: ${formatNumeroIndicador(personasCertificadas)} ÷ (${formatNumeroIndicador(personasCertificadas)} + ${formatNumeroIndicador(personasPendientes)})${notaComplementaria}</small></div></div>
    `;

    // Advertencias: solo se muestran las que calcula el backend. Si el array
    // viene vacio no se pinta ningun banner ni contador.
    if (avisos) {
      const lista = data.advertencias || [];
      if (!lista.length) {
        avisos.innerHTML = "";
      } else {
        const etiqueta = lista.length === 1 ? "advertencia" : "advertencias";
        avisos.innerHTML = `
          <details class="avisos-panel">
            <summary>
              <span class="avisos-title">Advertencias de cálculo</span>
              <span class="avisos-badge">${lista.length} ${etiqueta}</span>
              <span class="avisos-toggle">Ver detalle</span>
            </summary>
            <ul class="avisos-list">${lista.map((texto) => `<li>${texto}</li>`).join("")}</ul>
          </details>`;
      }
    }

    table.innerHTML = data.metricas.map(m => `
      <tr>
        <td><strong>${m.category_label}</strong>${m.nota_doble_conteo ? `<br><small style="color:var(--muted)">${m.nota_doble_conteo}</small>` : ""}</td>
        <td>${formatNumeroIndicador(m.meta)}</td>
        <td style="color:var(--green-dark);font-weight:700">${formatNumeroIndicador(m.certificados)}</td>
        <td style="color:#b87d00">${formatNumeroIndicador(m.pendientes)}</td>
        <td><strong>${formatPorcentajeIndicador(m.avance)}</strong></td>
        <td>${m.brecha === null || m.brecha === undefined ? "—" : (m.brecha > 0 ? m.brecha.toLocaleString("es-CO") : "Cumplida")}</td>
        <td><span class="result-badge ready">${formatPorcentajeIndicador(m.efectividad)}</span></td>
      </tr>
    `).join("");

    const causasCompletas = {
      filas: (data.motivos || []).map((m) => ({
        motivo: m.motivo,
        cantidad: Number(m.cantidad) || 0,
        porcentaje: m.porcentaje,
        variantes: [],
      })),
      total: Number(data.total_incidencias_causas) || 0,
    };
    const causasGrafico = agruparMotivos(data.motivos, 10);
    if (causasTable && data.motivos) {
      if (causasSummary) {
        causasSummary.textContent = `${formatNumeroIndicador(data.total_incidencias_causas)} incidencias · ${formatNumeroIndicador(data.total_pendientes)} aprendices únicos pendientes. Los motivos compuestos se desglosan; un aprendiz puede contar en más de una causa.`;
      }
      if (causasCount) causasCount.textContent = formatNumeroIndicador(data.total_incidencias_causas);
      causasTable.innerHTML = causasCompletas.filas.map((mot, index) => `
        <tr>
          <td><button class="drilldown-link" type="button" data-causa-index="${index}" title="Ver aprendices con esta causa">${mot.motivo}</button>${mot.variantes.length > 1 ? `<br><small class="causa-variantes">Agrupa: ${mot.variantes.join(", ")}</small>` : ""}</td>
          <td><strong>${mot.cantidad.toLocaleString("es-CO")}</strong></td>
          <td><span class="result-badge pending">${formatPorcentajeIndicador(mot.porcentaje)}</span></td>
        </tr>
      `).join("") || `<tr><td colspan="3" style="color:var(--muted)">Sin causas registradas en la hoja PENDIENTES.</td></tr>`;
      // Drill-down P0: causa normalizada -> motivos reales de la hoja PENDIENTES.
      causasTable.querySelectorAll("button[data-causa-index]").forEach((boton) => {
        boton.addEventListener("click", () => {
          const fila = causasCompletas.filas[Number(boton.dataset.causaIndex)];
          if (!fila) return;
          abrirAprendicesDesdeIndicadores({
            label: `causa «${fila.motivo}»`,
            reasons: fila.variantes.length ? fila.variantes : [fila.motivo],
          });
        });
      });
      if (causasNote) {
        causasNote.innerHTML = textoAuditoriaCausas(data);
      }
      const notaGrafico = document.querySelector("#indicadores-causas-chart-note");
      if (notaGrafico) {
        const partes = [];
        if (causasGrafico.resto) {
          partes.push(`Se muestran las 10 causas con más incidencias; «Otras causas» agrupa ${causasGrafico.resto.count} causas con ${formatNumeroIndicador(causasGrafico.resto.cantidad)} incidencias (detalle en la tabla completa).`);
        }
        if (causasGrafico.agrupadas) {
          partes.push(`${causasGrafico.agrupadas} causas agrupan variantes de escritura del mismo motivo.`);
        }
        notaGrafico.textContent = partes.join(" ");
        notaGrafico.hidden = !partes.length;
      }
    }

    if (actasTable && data.ultimas_actas) {
      if (actasCount) actasCount.textContent = data.ultimas_actas.length;
      renderActasIndicadores(
        data,
        actasTable,
        actasSummary,
        document.querySelector("#indicadores-actas-note")
      );
    }
    // Graficos complementarios (usan los mismos datos de las tablas de arriba).
    renderAvanceChart(data.metricas);
    renderCausasChart(causasGrafico.filas, (fila) => {
      abrirAprendicesDesdeIndicadores({
        label: `causa «${fila.motivo}»`,
        reasons: fila.variantes && fila.variantes.length ? fila.variantes : [fila.motivo],
      });
    });
  } catch (err) {
    kpis.innerHTML = `<p class="error">No fue posible calcular indicadores: ${err.message}</p>`;
    // Sin datos validos no se deben dejar graficos ni contadores desactualizados.
    limpiarGraficosIndicadores();
    if (causasCount) causasCount.textContent = "";
    if (actasCount) actasCount.textContent = "";
  }
}

const refreshIndicadoresBtn = document.querySelector("#refresh-indicadores");
if (refreshIndicadoresBtn) {
  refreshIndicadoresBtn.addEventListener("click", loadIndicadores);
}

viewLinks.forEach((link) => link.addEventListener("click", (event) => {
  event.preventDefault();
  showView(link.dataset.view);
}));
refreshLearnersButton.addEventListener("click", loadLearners);

function formatActReviewStatus(status) {
  const labels = {
    pending: "Pendiente",
    reviewed: "Revisada",
    rejected: "Rechazada",
  };
  return labels[String(status || "").toLowerCase()] || status || "Sin estado";
}

function renderActs(items) {
  actList.replaceChildren();
  items.forEach((item) => {
    const row = document.createElement("tr");
    [item.number || "Sin número", item.act_date || "Sin fecha", item.act_type || "Sin tipo", formatActReviewStatus(item.review_status), item.learners_count].forEach((value) => {
      const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell);
    });
    const cell = document.createElement("td"), button = document.createElement("button");
    button.className = "detail-button"; button.type = "button"; button.textContent = "Ver detalle";
    button.addEventListener("click", () => loadActDetail(item.id)); cell.appendChild(button); row.appendChild(cell); actList.appendChild(row);
  });
  if (!items.length) actList.innerHTML = '<tr><td colspan="6">No hay actas registradas.</td></tr>';
}
async function loadAnexos() {
  try {
    const result = await readResponse(await fetch("/api/anexos"));
    const items = result.items || [];
    anexosSummary.textContent = `${items.length} anexos cargados`;
    anexosList.replaceChildren();
    if (!items.length) {
      anexosList.innerHTML = '<p class="empty-detail">Aún no hay anexos cargados.</p>';
      return;
    }
    items.forEach((item) => {
      const entry = document.createElement("div");
      entry.className = "detail-list-item";
      const img = document.createElement("img");
      img.src = item.image_url;
      img.alt = item.title;
      img.style.maxWidth = "120px";
      img.style.maxHeight = "120px";
      img.style.objectFit = "contain";
      const text = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.title;
      const desc = document.createElement("p");
      desc.textContent = item.description || "Sin descripción";
      const date = document.createElement("small");
      date.textContent = item.attachment_date || "";
      text.append(title, desc, date);
      entry.append(img, text);
      anexosList.appendChild(entry);
    });
  } catch (error) {
    anexosSummary.textContent = error.message;
  }
}

if (anexoForm) {
  anexoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(anexoForm);
    try {
      await readResponse(await fetch("/api/anexos", { method: "POST", body: formData }));
      anexoForm.reset();
      anexoFeedback.textContent = "Anexo guardado correctamente.";
      loadAnexos();
    } catch (error) {
      anexoFeedback.textContent = error.message;
    }
  });
}

async function loadActs() {
  try {
    const params = {
      search: actSearch.value.trim(),
      ...(actNumberFilter.value.trim() ? {number: actNumberFilter.value.trim()} : {}),
      ...(actDateFrom.value ? {date_from: actDateFrom.value} : {}),
      ...(actDateTo.value ? {date_to: actDateTo.value} : {}),
      ...(actStatusFilter.value ? {review_status: actStatusFilter.value} : {}),
    };
    const result = await readResponse(await fetch(`/api/acts?${new URLSearchParams(params)}`));
    actSummary.textContent = `${result.items.length} actas registradas`; renderActs(result.items);
  } catch (error) { actSummary.textContent = error.message; }
}
async function loadActDetail(id) {
  currentActId = id; actDetail.hidden = false; actDetailContent.hidden = true;
  document.querySelectorAll("#actas-view > .panel").forEach((panel) => { if (panel.id !== "act-detail") panel.hidden = true; });
  try {
    const item = await readResponse(await fetch(`/api/acts/${id}`));
    actDetailTitle.textContent = item.number || "Acta"; actBasicInfo.replaceChildren();
    [["Número", item.number], ["Fecha", item.act_date], ["Tipo", item.act_type], ["Estado", formatActReviewStatus(item.review_status)], ["Archivo", item.original_file], ["Observaciones", item.observations]].forEach(([label, value]) => {
      const term = document.createElement("dt"), description = document.createElement("dd"); term.textContent = label; description.textContent = value || "No disponible"; actBasicInfo.append(term, description);
    });
    renderActLearners(item.learners); actDetailContent.hidden = false; actDetailFeedback.textContent = "";
  } catch (error) { actDetailFeedback.textContent = error.message; }
}
function renderActLearners(items) {
  actLearners.replaceChildren();
  if (!items.length) { actLearners.innerHTML = '<p class="empty-detail">Sin aprendices asociados.</p>'; return; }
  items.forEach((item) => {
    const entry = document.createElement("div"); entry.className = "detail-list-item"; entry.textContent = `${item.name} · ${item.identification} · ${item.certification_status || "Sin estado"}`;
    const button = document.createElement("button"); button.className = "cancel-button"; button.type = "button"; button.textContent = "Desasociar";
    button.addEventListener("click", async () => {
      let failure = null;
      try { await readResponse(await fetch(`/api/acts/${currentActId}/learners/${item.id}`, {method: "DELETE"})); }
      catch (error) { failure = error.message; }
      await loadActDetail(currentActId);
      if (failure) actDetailFeedback.textContent = failure;
    });
    entry.appendChild(button); actLearners.appendChild(entry);
  });
}
actForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const result = await readResponse(await fetch("/api/acts", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(Object.fromEntries(new FormData(actForm)))})); actForm.reset(); actFeedback.textContent = `Acta ${result.number} guardada correctamente.`; loadActs(); }
  catch (error) { actFeedback.textContent = error.message; }
});
actLearnerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const payload = Object.fromEntries(new FormData(actLearnerForm)); payload.learner_id = Number(payload.learner_id); await readResponse(await fetch(`/api/acts/${currentActId}/learners`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)})); actLearnerForm.reset(); loadActDetail(currentActId); }
  catch (error) { actDetailFeedback.textContent = error.message; }
});
document.querySelector("#refresh-acts").addEventListener("click", loadActs);
actSearch.addEventListener("input", loadActs);
actNumberFilter.addEventListener("input", loadActs);
actDateFrom.addEventListener("change", loadActs);
actDateTo.addEventListener("change", loadActs);
actStatusFilter.addEventListener("change", loadActs);
document.querySelector("#back-to-acts").addEventListener("click", () => { document.querySelectorAll("#actas-view > .panel").forEach((panel) => { panel.hidden = false; }); actDetail.hidden = true; });

[...categoryOptions, ...secondaryOptions].forEach((option) => option.addEventListener("click", () => selectOption(option)));
selectButton.addEventListener("click", (event) => { event.stopPropagation(); fileInput.click(); });
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") fileInput.click(); });
fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));
removeButton.addEventListener("click", clearFile);
cancelButton.addEventListener("click", () => {
  window.__sheetsSyncPending = false;
  window.__sheetsResolvePending = false;
  closeConflictConfirmModal();
  conflictConfirmBypass = false;
  if (sheetsManualCleanup) sheetsManualCleanup.checked = false;
  clearFile();
  clearFeedback();
  resetSelection();
  // Si el usuario cierra la resolución sin decidir, el lote sigue pendiente:
  // el banner vuelve a mostrarse y el worker no lo reimporta.
  loadSheetsStatus();
});
validateButton.addEventListener("click", validateFile);
confirmButton.addEventListener("click", confirmImport);
if (conflictConfirmAccept) {
  conflictConfirmAccept.addEventListener("click", () => {
    conflictConfirmBypass = true;
    closeConflictConfirmModal();
    confirmImport();
  });
}
if (conflictConfirmBack) {
  conflictConfirmBack.addEventListener("click", () => {
    conflictConfirmBypass = false;
    closeConflictConfirmModal();
    confirmButton?.focus?.({ preventScroll: true });
  });
}
conflictConfirmModal?.querySelectorAll("[data-close-conflict-confirm]").forEach((element) => {
  element.addEventListener("click", () => {
    conflictConfirmBypass = false;
    closeConflictConfirmModal();
    confirmButton?.focus?.({ preventScroll: true });
  });
});
conflictConfirmModal?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    conflictConfirmBypass = false;
    closeConflictConfirmModal();
    confirmButton?.focus?.({ preventScroll: true });
    return;
  }
  if (event.key !== "Tab") return;
  const focusables = [
    ...conflictConfirmModal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ].filter((element) => !element.hidden && !element.disabled && element.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
newImportButton.addEventListener("click", startNewImport);
viewImportedButton.addEventListener("click", () => {
  const target = viewImportedButton.dataset.viewTarget;
  if (target) showView(target);
});
acceptMissingComplementaria.addEventListener("change", updateCoherenceState);
resetSelection();
loadHistory();
loadLearners();
const initialView = window.location.hash === "#aprendices" ? "aprendices"
  : window.location.hash === "#anexos" ? "anexos"
  : window.location.hash === "#actas" ? "actas"
  : window.location.hash === "#indicadores" ? "indicadores"
  : "carga";
showView(initialView, false);


// ---------------------------------------------------------------------------
// Sincronización Google Sheets desde la barra superior
// ---------------------------------------------------------------------------
const sheetsToggleButton = document.querySelector("#sheets-toggle-button");
const sheetsSearchPanel = document.querySelector("#sheets-search-panel");
const sheetsUrlInput = document.querySelector("#sheets-url-input");
const sheetsSyncButton = document.querySelector("#sheets-sync-button");

const sheetsReviewModal = document.querySelector("#sheets-review-modal");
const sheetsReviewSubtitle = document.querySelector("#sheets-review-subtitle");
const sheetsReviewMessage = document.querySelector("#sheets-review-message");
const sheetsReviewCheck = document.querySelector("#sheets-review-check");
const sheetsReviewImport = document.querySelector("#sheets-review-import");
const sheetsProgressBar = document.querySelector("#sheets-progress-bar");
const sheetsProgressLabel = document.querySelector("#sheets-progress-label");
const sheetsReviewCloseButton = document.querySelector("#sheets-review-close-button");
const sheetsReviewClose = document.querySelector("#sheets-review-close");

let sheetsProgressTimer = null;
let sheetsProgressValue = 0;
let importProgressTimer = null;

function formatSheetsDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("es-CO", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function setSheetsProgress(percent, label) {
  if (sheetsProgressBar) {
    sheetsProgressBar.classList.add("is-determinate");
    sheetsProgressBar.style.width = `${percent}%`;
  }
  if (sheetsProgressLabel) sheetsProgressLabel.textContent = label || `${percent}%`;
}

function startSheetsProgress() {
  window.clearInterval(sheetsProgressTimer);
  sheetsProgressValue = 0;
  setSheetsProgress(0, "Sincronizando hoja… 0%");
  sheetsProgressTimer = window.setInterval(() => {
    const remaining = 90 - sheetsProgressValue;
    const step = Math.max(1, Math.round(remaining * 0.08));
    sheetsProgressValue = Math.min(90, sheetsProgressValue + step);
    setSheetsProgress(sheetsProgressValue, `Sincronizando hoja… ${sheetsProgressValue}%`);
  }, 320);
}

function stopSheetsProgress(success) {
  window.clearInterval(sheetsProgressTimer);
  sheetsProgressTimer = null;
  if (success) {
    setSheetsProgress(100, "Sincronización completada · 100%");
  }
}

function startImportPercentProgress() {
  const progress = document.querySelector("#modal-progress");
  const bar = document.querySelector("#modal-progress-bar");
  const label = document.querySelector("#modal-progress-label");
  if (progress) progress.hidden = false;
  if (bar) {
    bar.classList.add("is-determinate");
    bar.style.width = "0%";
  }
  let value = 0;
  const update = () => {
    const remaining = 90 - value;
    const step = Math.max(1, Math.round(remaining * 0.07));
    value = Math.min(90, value + step);
    if (bar) bar.style.width = `${value}%`;
    if (label) label.textContent = `Importando información… ${value}%`;
  };
  if (label) label.textContent = "Importando información… 0%";
  window.clearInterval(importProgressTimer);
  importProgressTimer = window.setInterval(update, 340);
  return (success) => {
    window.clearInterval(importProgressTimer);
    importProgressTimer = null;
    if (success) {
      if (bar) bar.style.width = "100%";
      if (label) label.textContent = "Importación completada · 100%";
      window.setTimeout(() => {
        if (progress) progress.hidden = true;
        if (bar) bar.classList.remove("is-determinate");
      }, 700);
    } else {
      if (progress) progress.hidden = true;
      if (bar) bar.classList.remove("is-determinate");
    }
  };
}

function openSheetsReviewModal() {
  if (!sheetsReviewModal) return;
  sheetsReviewModal.classList.add("is-open");
  sheetsReviewModal.setAttribute("aria-hidden", "false");
}

function closeSheetsReviewModal() {
  if (!sheetsReviewModal) return;
  sheetsReviewModal.classList.remove("is-open");
  sheetsReviewModal.setAttribute("aria-hidden", "true");
}

function setSheetsReviewState({ subtitle, message, check, importText }) {
  if (sheetsReviewSubtitle) sheetsReviewSubtitle.textContent = subtitle;
  if (sheetsReviewMessage) sheetsReviewMessage.textContent = message;
  if (sheetsReviewCheck) sheetsReviewCheck.textContent = check || "";
  if (sheetsReviewImport) sheetsReviewImport.textContent = importText || "";
}

function showSheetsPreview(data) {
  const preview = data.preview;
  if (!preview) return;
  const fields = [
    [confirmFile, preview.file_name],
    [confirmImportable, preview.records_count],
    [confirmNew, preview.new_records],
    [confirmUpdated, preview.updated_records],
    [confirmRejected, preview.rejected_records ?? 0],
  ];
  fields.forEach(([element, value]) => {
    if (element) element.textContent = value;
  });
  confirmRejected.closest(".confirm-metric")?.classList.toggle(
    "has-rejected",
    Number(preview.rejected_records || 0) > 0,
  );
  renderPreviewBreakdown(preview);
  renderPreviewWarnings(preview.warnings);
  renderCoherenceConflicts(preview.coherence_conflicts || [], {
    resolutions: preview.conflict_resolutions || {},
  });
  missingComplementariaRequired = Boolean(preview.missing_complementaria);
  if (missingComplementariaRequired) missingComplementariaSection.hidden = false;
  updateCoherenceState();

  validationId = data.validation_id;
  window.__sheetsSyncPending = true;
  confirmationPanel.hidden = false;
  confirmButton.hidden = false;
  validateButton.hidden = true;
  cargaView.classList.add("carga-en-revision");
  setCargaStep("confirmar");
  window.setTimeout(() => revealValidationResult(confirmSummary), 80);
}

function setConflictBannerVisible(visible) {
  if (!conflictBanner) return;
  conflictBanner.hidden = !visible;
  document.body.classList.toggle("has-conflict-banner", visible);
  if (visible) {
    window.requestAnimationFrame(() => {
      const height = conflictBanner.offsetHeight || 0;
      document.documentElement.style.setProperty("--conflict-banner-height", `${height}px`);
    });
  } else {
    document.documentElement.style.setProperty("--conflict-banner-height", "0px");
  }
}

function conflictCountLabel(count) {
  return count === 1 ? "1 conflicto pendiente" : `${count} conflictos pendientes`;
}

function updateConflictBanner(data) {
  const count = Number(data.pending_conflict_count || 0);
  const pending = Boolean(data.conflict_pending && count > 0);
  if (!pending) {
    activeConflictFingerprint = null;
    conflictDismissedFingerprint = "";
    try {
      window.sessionStorage.removeItem(CONFLICT_DISMISS_KEY);
    } catch (error) {
      // La sesión puede estar restringida; el banner igualmente se oculta.
    }
    setConflictBannerVisible(false);
    return;
  }

  const fingerprint = String(
    data.pending_conflict_fingerprint
      || data.pending_conflict_summary?.fingerprint
      || "",
  );
  activeConflictFingerprint = fingerprint || null;
  if (fingerprint && fingerprint === conflictDismissedFingerprint) {
    setConflictBannerVisible(false);
    return;
  }

  if (conflictBannerText) {
    conflictBannerText.textContent = (
      `${conflictCountLabel(count)} de resolución (Google Sheets).`
    );
  }
  setConflictBannerVisible(true);
}

async function sendNativeConflictNotification(data) {
  if (!data.notification_pending) return;
  const fingerprint = String(
    data.pending_conflict_fingerprint
      || data.pending_conflict_summary?.fingerprint
      || "",
  );
  if (!fingerprint || fingerprint === nativeNotificationFingerprint) return;

  const count = Number(data.pending_conflict_count || 0);
  const title = "Conflicto de certificación detectado";
  const body = count === 1
    ? "1 aprendiz aparece en CERTIFICADOS y PENDIENTES. Debe definir el estado final en la aplicación."
    : `${count} aprendices aparecen en CERTIFICADOS y PENDIENTES. Debe definir el estado final en la aplicación.`;

  // Se marca antes del await para que dos ciclos de polling simultáneos no
  // intenten mostrar el mismo toast.
  nativeNotificationFingerprint = fingerprint;
  let delivered = false;

  const bridge = window.pywebview?.api;
  if (bridge && typeof bridge.notify_conflict === "function") {
    try {
      const result = await bridge.notify_conflict(count, fingerprint, title, body);
      delivered = Boolean(result) && result.delivered !== false;
    } catch (error) {
      delivered = false;
    }
  }

  if (!delivered && typeof window.Notification === "function") {
    try {
      let permission = window.Notification.permission;
      if (permission === "default") permission = await window.Notification.requestPermission();
      if (permission === "granted") {
        const notification = new window.Notification(title, {
          body,
          tag: `sena-conflict-${fingerprint}`,
          requireInteraction: true,
        });
        notification.onclick = () => {
          window.focus();
          openPendingConflictResolution();
          notification.close();
        };
        delivered = true;
      }
    } catch (error) {
      delivered = false;
    }
  }

  if (!delivered) {
    // Se reintenta en el próximo ciclo; el backend mantiene notified_at vacío.
    nativeNotificationFingerprint = null;
    return;
  }

  try {
    await fetch("/api/sheets/sync/notified", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fingerprint }),
    });
  } catch (error) {
    // Si falla la marca, el backend volverá a pedir la notificación; el
    // bridge de escritorio deduplica por huella dentro del mismo proceso.
  }
}

function setConflictResolutionLoading(loading) {
  conflictResolutionLoading = loading;
  if (conflictResolveButton) {
    conflictResolveButton.disabled = loading;
    conflictResolveButton.classList.toggle("is-loading", loading);
    conflictResolveButton.textContent = loading
      ? "Cargando conflictos…"
      : "Resolver ahora";
    conflictResolveButton.setAttribute("aria-busy", loading ? "true" : "false");
  }
  const globalProgress = document.getElementById("global-progress");
  if (globalProgress) globalProgress.hidden = !loading;
  if (loading) {
    window.showToast?.("Cargando conflictos…", "info", { duration: 2000 });
  }
}

async function openPendingConflictResolution() {
  if (conflictResolutionLoading) return;
  setConflictResolutionLoading(true);
  try {
    const response = await fetch("/api/sheets/sync/pending-conflicts", { cache: "no-store" });
    const data = await readResponse(response);
    if (!data.conflict_pending || !data.preview) {
      window.showToast?.("No hay conflictos pendientes de Google Sheets.", "info");
      await loadSheetsStatus();
      return;
    }

    // Sin cambio de hash: abrir la resolución no debe depender de
    // history.replaceState (algunos bloqueadores lo marcan como browser
    // locker y abortarían el flujo antes de mostrar el modal).
    showView("carga", false);
    showSheetsPreview({ validation_id: data.validation_id, preview: data.preview });
    window.__sheetsSyncPending = true;
    window.__sheetsResolvePending = true;
    setConflictBannerVisible(false);
    window.setTimeout(() => window.SenaUI?.openImportModal?.(), 80);
    window.showToast?.(
      `${conflictCountLabel(Number(data.pending_conflict_count || 0))}. `
        + "Elige Certificado o Pendiente para cada aprendiz.",
      "warning",
      { duration: 6500 },
    );
  } catch (error) {
    window.showToast?.(
      "No fue posible cargar los conflictos. Intente de nuevo.",
      "error",
    );
  } finally {
    setConflictResolutionLoading(false);
  }
}

function dismissConflictBannerForSession() {
  if (activeConflictFingerprint) {
    conflictDismissedFingerprint = activeConflictFingerprint;
    try {
      window.sessionStorage.setItem(CONFLICT_DISMISS_KEY, activeConflictFingerprint);
    } catch (error) {
      // Sin sessionStorage se oculta solo hasta la próxima recarga.
    }
  }
  setConflictBannerVisible(false);
  window.showToast?.(
    "El lote sigue pendiente. Puedes retomarlo desde el botón Google Sheets o al recargar.",
    "info",
    { duration: 6000 },
  );
}

async function loadSheetsStatus() {
  try {
    const response = await fetch("/api/sheets/sync", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    if (!data.configured) {
      updateConflictBanner(data);
      if (conflictPollTimer) {
        window.clearInterval(conflictPollTimer);
        conflictPollTimer = null;
      }
      return;
    }
    // El polling ligero solo se mantiene cuando hay una hoja configurada.
    startConflictPolling();
    updateConflictBanner(data);
    if (data.notification_pending) {
      sendNativeConflictNotification(data).catch(() => {});
    }
    if (sheetsUrlInput && !sheetsUrlInput.value) sheetsUrlInput.value = data.url || "";
    if (sheetsToggleButton) {
      const state = data.enabled ? "activa" : "detenida";
      sheetsToggleButton.title = `Sincronización Google Sheets ${state}. Última revisión: ${formatSheetsDate(data.last_check_at)}`;
    }
  } catch (error) {
    // El estado no debe bloquear la carga manual de archivos.
  }
}

async function runSheetsSync() {
  const url = (sheetsUrlInput?.value || "").trim();
  if (!url || !url.includes("docs.google.com")) {
    showFeedback("Introduce un enlace válido de Google Sheets.", true);
    if (sheetsUrlInput) sheetsUrlInput.focus();
    return;
  }
  openSheetsReviewModal();
  startSheetsProgress();
  setSheetsReviewState({
    subtitle: "Descargando y validando la hoja…",
    message: "Espera mientras se revisa el contenido del documento.",
    check: "",
    importText: "",
  });
  try {
    const response = await fetch("/api/sheets/sync/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        information_type: "actas_completo",
        interval_seconds: 60,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No fue posible sincronizar la hoja.");

    stopSheetsProgress(true);
    if (data.status === "ready") {
      const preview = data.preview || {};
      setSheetsReviewState({
        subtitle: "Cambios detectados",
        message: data.message || "Revisa la información antes de importar.",
        check: `Registros importables: ${preview.records_count ?? 0}`,
        importText: `Advertencias: ${(preview.warnings || []).length}`,
      });
      window.setTimeout(() => {
        closeSheetsReviewModal();
        showSheetsPreview(data);
      }, 550);
    } else {
      setSheetsReviewState({
        subtitle: data.status === "unchanged" ? "Sin cambios" : "No se pudo preparar la importación",
        message: data.message || "No hay cambios para importar.",
        check: data.config?.last_check_at ? `Última revisión: ${formatSheetsDate(data.config.last_check_at)}` : "",
        importText: "",
      });
    }
  } catch (error) {
    stopSheetsProgress(false);
    setSheetsProgress(100, "Error de sincronización · 100%");
    setSheetsReviewState({
      subtitle: "Error de sincronización",
      message: error.message,
      check: "",
      importText: "",
    });
  } finally {
    // Si la hoja quedo configurada, esto activa el polling del banner.
    loadSheetsStatus();
  }
}

if (sheetsToggleButton && sheetsSearchPanel) {
  sheetsToggleButton.addEventListener("click", () => {
    const isOpen = sheetsSearchPanel.classList.toggle("is-open");
    sheetsToggleButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
    if (isOpen) window.setTimeout(() => sheetsUrlInput?.focus(), 180);
  });
}

if (sheetsSyncButton) sheetsSyncButton.addEventListener("click", runSheetsSync);
if (sheetsUrlInput) {
  sheetsUrlInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSheetsSync();
    }
  });
}

if (sheetsReviewCloseButton) sheetsReviewCloseButton.addEventListener("click", closeSheetsReviewModal);
if (sheetsReviewClose) sheetsReviewClose.addEventListener("click", closeSheetsReviewModal);
document.querySelectorAll("[data-close-sheets-review]").forEach((el) => {
  el.addEventListener("click", closeSheetsReviewModal);
});

if (conflictResolveButton) {
  conflictResolveButton.addEventListener("click", () => {
    openPendingConflictResolution();
  });
}
if (conflictLaterButton) {
  conflictLaterButton.addEventListener("click", dismissConflictBannerForSession);
}

// API usada por el bridge de pywebview al hacer clic en el toast nativo.
window.SenaConflictBanner = {
  refresh: loadSheetsStatus,
  openResolution: openPendingConflictResolution,
  update: updateConflictBanner,
  dismiss: dismissConflictBannerForSession,
};

window.addEventListener("hashchange", () => {
  if (window.location.hash === "#conflict-pending") {
    openPendingConflictResolution().finally(() => {
      // Se limpia el hash con la misma protección que el resto de la
      // navegación: si el bloqueador lo impide, no afecta al modal abierto.
      replaceLocationHash("#carga");
    });
  }
});

if (window.location.hash === "#conflict-pending") {
  window.setTimeout(openPendingConflictResolution, 350);
}

// El bridge JS -> Python se inyecta de forma asíncrona; al estar listo se
// refresca el estado para poder emitir el toast pendiente.
window.addEventListener("pywebviewready", () => {
  loadSheetsStatus();
});

function startConflictPolling() {
  if (conflictPollTimer) return;
  conflictPollTimer = window.setInterval(() => {
    if (document.visibilityState === "hidden") return;
    loadSheetsStatus();
  }, CONFLICT_POLL_INTERVAL_MS);
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") loadSheetsStatus();
});

window.addEventListener("resize", () => {
  if (!conflictBanner || conflictBanner.hidden) return;
  document.documentElement.style.setProperty(
    "--conflict-banner-height",
    `${conflictBanner.offsetHeight || 0}px`,
  );
});

loadSheetsStatus();
