const typeOptions = document.querySelectorAll(".type-option");
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
const confirmationPanel = document.querySelector("#confirmation-panel");
const confirmFile = document.querySelector("#confirm-file");
const confirmNew = document.querySelector("#confirm-new");
const confirmUpdated = document.querySelector("#confirm-updated");
const confirmWarnings = document.querySelector("#confirm-warnings");
const historyList = document.querySelector("#history-list");
const learnersList = document.querySelector("#learners-list");
const learnersSummary = document.querySelector("#learners-summary");
const refreshLearnersButton = document.querySelector("#refresh-learners");
const learnerSearch = document.querySelector("#learner-search");
const learnerStatus = document.querySelector("#learner-status");
const clearLearnerSearch = document.querySelector("#clear-learner-search");
const learnersPrev = document.querySelector("#learners-prev");
const learnersNext = document.querySelector("#learners-next");
const learnersPage = document.querySelector("#learners-page");
const pendingLearnersButton = document.querySelector("#pending-learners-button");
const learnersFrame = document.querySelector(".learners-frame");
const learnerDetail = document.querySelector("#learner-detail");
const backToLearners = document.querySelector("#back-to-learners");
const learnerDetailTitle = document.querySelector("#learner-detail-title");
const learnerDetailFeedback = document.querySelector("#learner-detail-feedback");
const learnerDetailContent = document.querySelector("#learner-detail-content");
const learnerBasicInfo = document.querySelector("#learner-basic-info");
const learnerRequirements = document.querySelector("#learner-requirements");
const viewLinks = document.querySelectorAll("[data-view]");
const views = document.querySelectorAll(".app-view");
const maxFileSize = 20 * 1024 * 1024;
const actForm = document.querySelector("#act-form");
const actList = document.querySelector("#acts-list");
const actSearch = document.querySelector("#act-search");
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

const extensionsByType = {
  df14a: [".xlsx", ".xls", ".csv"],
  acta: [".pdf", ".docx"],
  requisitos: [".xlsx", ".xls", ".csv"],
  otro: [".xlsx", ".xls", ".csv", ".pdf", ".docx"],
};

let selectedType = "df14a";
let selectedFile = null;
let validationId = null;

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

function hideReview() {
  validationPanel.hidden = true;
  confirmationPanel.hidden = true;
  confirmButton.hidden = true;
  validateButton.hidden = false;
  validateButton.disabled = !selectedFile;
  validationId = null;
}

function setType(type) {
  selectedType = type;
  typeOptions.forEach((option) => option.classList.toggle("selected", option.dataset.type === type));
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
  validationStatus.textContent = result.status === "error" ? "NO APTO" : result.status === "warning" ? "CON ADVERTENCIAS" : "APTO PARA REVISAR";
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
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "No fue posible completar la operacion.");
  return result;
}

async function validateFile() {
  if (!selectedFile) return;
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
    fileStatus.textContent = result.status === "error" ? "REVISAR ARCHIVO" : "VALIDACION COMPLETA";
    if (result.status === "error") {
      showFeedback("Corrige los errores antes de continuar.", true);
      return;
    }
    const preview = await readResponse(await fetch(`/api/imports/${validationId}/preview`));
    confirmFile.textContent = preview.file_name;
    confirmNew.textContent = preview.new_records;
    confirmUpdated.textContent = preview.updated_records;
    confirmWarnings.replaceChildren(...preview.warnings.map((warning) => {
      const item = document.createElement("div");
      item.textContent = `⚠ ${warning}`;
      return item;
    }));
    confirmationPanel.hidden = false;
    confirmButton.hidden = false;
    validateButton.hidden = true;
    showFeedback("Revisa el resumen y confirma para importar. Aun no se han guardado datos.");
  } catch (error) {
    fileStatus.textContent = "ERROR DE VALIDACION";
    showFeedback(error.message, true);
  } finally {
    validateButton.disabled = false;
  }
}

async function confirmImport() {
  if (!validationId) return;
  confirmButton.disabled = true;
  try {
    const result = await readResponse(await fetch(`/api/imports/${validationId}/confirm`, { method: "POST" }));
    fileStatus.textContent = "IMPORTACION COMPLETA";
    showFeedback(`${result.message} ${result.records_count} registros procesados.`);
    confirmButton.hidden = true;
    await loadHistory();
    await loadLearners();
  } catch (error) {
    showFeedback(error.message, true);
  } finally {
    confirmButton.disabled = false;
  }
}

async function loadHistory() {
  try {
    const result = await readResponse(await fetch("/api/imports/history"));
    if (!result.items.length) return;
    historyList.replaceChildren(...result.items.slice(0, 5).map((item) => {
      const element = document.createElement("div");
      element.className = "history-item";
      element.innerHTML = `<strong>${item.file_name}</strong><small>${item.information_type} · ${item.records_count} registros · ${new Date(item.imported_at).toLocaleString()}</small>`;
      return element;
    }));
  } catch (error) {
    historyList.textContent = "No fue posible cargar el historial.";
  }
}

let learnerPageNumber = 1;
const learnerPageSize = 25;

function renderLearnerRow(item) {
  const row = document.createElement("tr");
  [item.name, item.identification, item.program || "Sin programa", item.group_code || "Sin ficha", item.certification_status || "Sin estado"]
    .forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
  const pendingCell = document.createElement("td");
  pendingCell.textContent = item.pending_count ?? "—";
  row.appendChild(pendingCell);
  const detailCell = document.createElement("td");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "detail-button";
  button.textContent = "Ver detalles";
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    loadLearnerDetail(item.id);
  });
  detailCell.appendChild(button);
  row.appendChild(detailCell);
  row.addEventListener("click", () => loadLearnerDetail(item.id));
  return row;
}

function renderRequirementEditor(items) {
  learnerRequirements.replaceChildren();
  if (!items.length) {
    learnerRequirements.innerHTML = "<p class=\"empty-detail\">No hay requisitos registrados.</p>";
    return;
  }
  items.forEach((item) => {
    const form = document.createElement("form");
    form.className = "requirement-editor";
    form.innerHTML = `<strong>${item.label || item.requirement_type}</strong>
      <label>Estado<select name="status">
        <option>Pendiente</option><option>Cumplido</option><option>No aplica</option>
      </select></label>
      <label>Observación<textarea name="observations" rows="2"></textarea></label>
      <button class="primary-button" type="submit">Guardar</button>
      <span class="requirement-feedback" role="status"></span>`;
    form.elements.status.value = item.status || "Pendiente";
    form.elements.observations.value = item.observations || "";
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
        feedback.textContent = "Guardado.";
      } catch (error) {
        feedback.textContent = error.message;
      }
    });
    learnerRequirements.appendChild(form);
  });
}

async function loadLearnerDetail(learnerId) {
  learnersFrame.hidden = true;
  learnerDetail.hidden = false;
  learnerDetailContent.hidden = true;
  learnerDetailFeedback.textContent = "Consultando...";
  try {
    const result = await readResponse(await fetch(`/api/learners/${learnerId}`));
    window.currentLearnerId = learnerId;
    learnerDetailTitle.textContent = result.basic_info.name;
    learnerBasicInfo.replaceChildren();
    [["Documento", result.basic_info.identification], ["Programa", result.basic_info.program],
      ["Ficha", result.basic_info.group_code], ["Estado", result.basic_info.certification_status]]
      .forEach(([label, value]) => {
        const term = document.createElement("dt");
        term.textContent = label;
        const description = document.createElement("dd");
        description.textContent = value || "No disponible";
        learnerBasicInfo.append(term, description);
      });
    renderRequirementEditor(result.requirements);
    learnerDetailFeedback.textContent = "";
    learnerDetailContent.hidden = false;
  } catch (error) {
    learnerDetailFeedback.textContent = error.message;
  }
}

async function loadLearners() {
  try {
    const params = new URLSearchParams({
      search: learnerSearch.value.trim(),
      status: learnerStatus.value,
      page: learnerPageNumber,
      page_size: learnerPageSize,
    });
    const result = await readResponse(await fetch(`/api/learners?${params}`));
    const selectedStatus = learnerStatus.value;
    learnerStatus.replaceChildren(new Option("Todos los estados", ""));
    result.statuses.forEach((status) => learnerStatus.add(new Option(status, status)));
    learnerStatus.value = selectedStatus;
    learnersSummary.textContent = `${result.total} ${result.total === 1 ? "aprendiz" : "aprendices"} registrados`;
    learnersPage.textContent = `Pagina ${result.page} de ${Math.max(result.pages, 1)}`;
    learnersPrev.disabled = result.page <= 1;
    learnersNext.disabled = result.page >= result.pages;
    if (!result.items.length) {
      learnersList.innerHTML = `<tr><td colspan="7">${learnerSearch.value ? "No se encontraron aprendices." : "Aun no hay aprendices cargados. Confirma una importacion DF14A para empezar."}</td></tr>`;
      return;
    }

    async function loadPendingLearners() {
      try {
        const result = await readResponse(await fetch("/api/learners/with-pending-requirements"));
        learnersSummary.textContent = `${result.items.length} aprendices con requisitos pendientes`;
        learnersList.replaceChildren(...result.items.map((item) => {
          const row = renderLearnerRow(item);
          const pendingCell = row.cells[5];
          pendingCell.textContent = item.pending_count;
          return row;
        }));
      } catch (error) {
        learnersSummary.textContent = error.message;
      }
    }

    backToLearners.addEventListener("click", () => {
      learnerDetail.hidden = true;
      learnersFrame.hidden = false;
    });
    pendingLearnersButton.addEventListener("click", loadPendingLearners);
    learnersList.replaceChildren(...result.items.map(renderLearnerRow));
  } catch (error) {
    learnersSummary.textContent = "No fue posible consultar SQLite";
    learnersList.textContent = "No fue posible cargar los aprendices.";
  }

  learnerSearch.addEventListener("input", () => {
    learnerPageNumber = 1;
    loadLearners();
  });
  clearLearnerSearch.addEventListener("click", () => {
    learnerSearch.value = "";
    learnerStatus.value = "";
    learnerPageNumber = 1;
    loadLearners();
  });
  learnerStatus.addEventListener("change", () => {
    learnerPageNumber = 1;
    loadLearners();
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
}

function showView(viewName, updateHash = true) {
  const target = ["aprendices", "actas"].includes(viewName) ? viewName : "carga";
  views.forEach((view) => {
    view.hidden = view.id !== `${target}-view`;
  });
  viewLinks.forEach((link) => link.classList.toggle("active", link.dataset.view === target));
  if (updateHash) history.replaceState(null, "", `#${target}`);
  if (target === "aprendices") loadLearners();
  if (target === "actas") loadActs();
}

viewLinks.forEach((link) => link.addEventListener("click", (event) => {
  event.preventDefault();
  showView(link.dataset.view);
}));
refreshLearnersButton.addEventListener("click", loadLearners);

function renderActs(items) {
  actList.replaceChildren();
  items.forEach((item) => {
    const row = document.createElement("tr");
    [item.number || "Sin número", item.act_date || "Sin fecha", item.act_type || "Sin tipo", item.review_status, item.learners_count].forEach((value) => {
      const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell);
    });
    const cell = document.createElement("td"), button = document.createElement("button");
    button.className = "detail-button"; button.type = "button"; button.textContent = "Ver detalle";
    button.addEventListener("click", () => loadActDetail(item.id)); cell.appendChild(button); row.appendChild(cell); actList.appendChild(row);
  });
  if (!items.length) actList.innerHTML = '<tr><td colspan="6">No hay actas registradas.</td></tr>';
}
async function loadActs() {
  try {
    const result = await readResponse(await fetch(`/api/acts?search=${encodeURIComponent(actSearch.value.trim())}`));
    actSummary.textContent = `${result.items.length} actas registradas`; renderActs(result.items);
  } catch (error) { actSummary.textContent = error.message; }
}
async function loadActDetail(id) {
  currentActId = id; actDetail.hidden = false; actDetailContent.hidden = true;
  document.querySelectorAll("#actas-view > .panel").forEach((panel) => { if (panel.id !== "act-detail") panel.hidden = true; });
  try {
    const item = await readResponse(await fetch(`/api/acts/${id}`));
    actDetailTitle.textContent = item.number || "Acta"; actBasicInfo.replaceChildren();
    [["Número", item.number], ["Fecha", item.act_date], ["Tipo", item.act_type], ["Estado", item.review_status], ["Archivo", item.original_file], ["Observaciones", item.observations]].forEach(([label, value]) => {
      const term = document.createElement("dt"), description = document.createElement("dd"); term.textContent = label; description.textContent = value || "No disponible"; actBasicInfo.append(term, description);
    });
    renderActLearners(item.learners); actDetailContent.hidden = false; actDetailFeedback.textContent = "";
  } catch (error) { actDetailFeedback.textContent = error.message; }
}
function renderActLearners(items) {
  actLearners.replaceChildren();
  if (!items.length) { actLearners.innerHTML = '<p class="empty-detail">Sin aprendices asociados.</p>'; return; }
  items.forEach((item) => {
    const entry = document.createElement("div"); entry.className = "detail-list-item"; entry.textContent = `${item.name} · ${item.identification}`;
    const button = document.createElement("button"); button.className = "cancel-button"; button.type = "button"; button.textContent = "Desasociar";
    button.addEventListener("click", async () => { await readResponse(await fetch(`/api/acts/${currentActId}/learners/${item.id}`, {method: "DELETE"})); loadActDetail(currentActId); });
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
document.querySelector("#back-to-acts").addEventListener("click", () => { actDetail.hidden = true; document.querySelectorAll("#actas-view > .panel").forEach((panel) => { panel.hidden = false; }); });

typeOptions.forEach((option) => option.addEventListener("click", () => setType(option.dataset.type)));
selectButton.addEventListener("click", (event) => { event.stopPropagation(); fileInput.click(); });
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") fileInput.click(); });
fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));
removeButton.addEventListener("click", clearFile);
cancelButton.addEventListener("click", () => { clearFile(); clearFeedback(); setType("df14a"); });
validateButton.addEventListener("click", validateFile);
confirmButton.addEventListener("click", confirmImport);
updateAcceptedFormats();
loadHistory();
loadLearners();
showView(window.location.hash === "#aprendices" ? "aprendices" : "carga", false);