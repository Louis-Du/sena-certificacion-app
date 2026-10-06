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
const clearLearnerSearch = document.querySelector("#clear-learner-search");
const learnersPrev = document.querySelector("#learners-prev");
const learnersNext = document.querySelector("#learners-next");
const learnersPage = document.querySelector("#learners-page");
const viewLinks = document.querySelectorAll("[data-view]");
const views = document.querySelectorAll(".app-view");
const maxFileSize = 20 * 1024 * 1024;

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
  return row;
}

async function loadLearners() {
  learnersSummary.textContent = "Consultando SQLite...";
  try {
    const params = new URLSearchParams({
      search: learnerSearch.value.trim(),
      page: learnerPageNumber,
      page_size: learnerPageSize,
    });
    const response = await fetch(`/api/learners?${params}`);
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({ detail: `Error HTTP ${response.status}` }));
      throw new Error(errorPayload.detail || `Error HTTP ${response.status}`);
    }
    const result = await response.json();
    learnersSummary.textContent = `${result.total} ${result.total === 1 ? "aprendiz" : "aprendices"} registrados`;
    learnersPage.textContent = `Pagina ${result.page} de ${Math.max(result.pages, 1)}`;
    learnersPrev.disabled = result.page <= 1;
    learnersNext.disabled = result.page >= Math.max(result.pages, 1);
    if (!result.items.length) {
      const cell = document.createElement("td");
      cell.colSpan = 5;
      cell.textContent = learnerSearch.value ? "No se encontraron aprendices." : "Aun no hay aprendices cargados. Confirma una importacion DF14A para empezar.";
      const emptyRow = document.createElement("tr");
      emptyRow.appendChild(cell);
      learnersList.replaceChildren(emptyRow);
      return;
    }
    learnersList.replaceChildren(...result.items.map(renderLearnerRow));
  } catch (error) {
    learnersSummary.textContent = error.message;
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = `No fue posible cargar los aprendices: ${error.message}`;
    const errorRow = document.createElement("tr");
    errorRow.appendChild(cell);
    learnersList.replaceChildren(errorRow);
  }
}

learnerSearch.addEventListener("input", () => {
  learnerPageNumber = 1;
  loadLearners();
});
clearLearnerSearch.addEventListener("click", () => {
  learnerSearch.value = "";
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

function showView(viewName, updateHash = true) {
  const target = viewName === "aprendices" ? "aprendices" : "carga";
  views.forEach((view) => {
    view.hidden = view.id !== `${target}-view`;
  });
  viewLinks.forEach((link) => link.classList.toggle("active", link.dataset.view === target));
  if (updateHash) history.replaceState(null, "", target === "aprendices" ? "#aprendices" : "#carga");
  if (target === "aprendices") loadLearners();
}

viewLinks.forEach((link) => link.addEventListener("click", (event) => {
  event.preventDefault();
  showView(link.dataset.view);
}));
refreshLearnersButton.addEventListener("click", loadLearners);

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