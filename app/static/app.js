const categoryOptions = document.querySelectorAll(".category-option");
const typeOptions = document.querySelectorAll(".type-option");
let selectedCategory = "datos_certificacion";
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
const confirmImportable = document.querySelector("#confirm-importable");
const confirmNew = document.querySelector("#confirm-new");
const confirmUpdated = document.querySelector("#confirm-updated");
const confirmRejected = document.querySelector("#confirm-rejected");
const confirmBreakdown = document.querySelector("#confirm-breakdown");
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
const porCertificarLearnersButton = document.querySelector("#por-certificar-learners-button");
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

let selectedType = "actas_completo";
let selectedFile = null;
let validationId = null;

function setCategory(category) {
  selectedCategory = category;
  categoryOptions.forEach((btn) => btn.classList.toggle("selected", btn.dataset.category === category));

  typeOptions.forEach((btn) => {
    btn.hidden = btn.dataset.category !== category;
  });

  const categoryHeadings = {
    datos_certificacion: {
      title: "Opciones de Datos de certificación",
      description: "Selecciona el origen: Excel institucional, DF14A o CSV alternativo",
    },
    actas_revision: {
      title: "Actas para revisión",
      description: "Acta individual en formato Word o PDF para revisión y vinculación",
    },
    requisitos_aprendices: {
      title: "Requisitos de aprendices",
      description: "Matriz de seguimiento de requisitos por aprendiz",
    },
    documentos_referencia: {
      title: "Documentos de referencia",
      description: "Informe de gestión institucional o documentos de apoyo",
    },
  };

  const headingInfo = categoryHeadings[category] || {
    title: "Opciones disponibles",
    description: "Selecciona el tipo de archivo",
  };

  const titleEl = document.querySelector("#subtype-title");
  const descEl = document.querySelector("#subtype-description");
  if (titleEl) titleEl.textContent = headingInfo.title;
  if (descEl) descEl.textContent = headingInfo.description;

  const currentOption = Array.from(typeOptions).find(
    (opt) => opt.dataset.type === selectedType && opt.dataset.category === category
  );
  if (currentOption) {
    setType(selectedType);
  } else {
    const firstAvailable = Array.from(typeOptions).find(
      (opt) => opt.dataset.category === category
    );
    if (firstAvailable) {
      setType(firstAvailable.dataset.type);
    }
  }
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
    if (!preview.records_count) {
      throw new Error("El archivo no contiene registros importables. Corrige los errores y vuelve a validar.");
    }
    confirmFile.textContent = preview.file_name;
    confirmImportable.textContent = preview.records_count;
    confirmNew.textContent = preview.new_records;
    confirmUpdated.textContent = preview.updated_records;
    confirmRejected.textContent = preview.rejected_records ?? 0;
    const breakdownLabels = {
      certificados: "Aprendices para certificar",
      pendientes: "Aprendices con pendientes",
      complementaria: "Registros de formación complementaria",
      meta: "Metas institucionales",
      requisitos: "Requisitos de aprendices",
      df14a: "Aprendices (Base DF14A)",
      acta: "Documentos de acta",
      informe: "Tablas de informe de gestión",
      otro: "Documentos de apoyo",
    };
    const breakdownLines = Object.entries(preview.breakdown || {}).map(([type, counts]) => {
      const label = breakdownLabels[type] || type;
      if (counts.valid_records === counts.records_found) {
        return `✓ ${counts.valid_records} ${label.toLowerCase()}`;
      }
      return `⚠ ${counts.valid_records} ${label.toLowerCase()} (de ${counts.records_found} detectados)`;
    });
    confirmBreakdown.replaceChildren(...breakdownLines.map((line) => {
      const item = document.createElement("div");
      item.textContent = line;
      return item;
    }));
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
      const title = document.createElement("strong");
      title.textContent = item.file_name;
      const details = document.createElement("small");
      const timeStr = new Date(item.imported_at).toLocaleString();
      details.textContent = `${item.information_type} · ${timeStr}`;
      const msg = document.createElement("div");
      msg.className = "history-message";
      msg.textContent = item.message || "Importación exitosa";
      element.append(title, details, msg);
      return element;
    }));
  } catch (error) {
    historyList.textContent = "No fue posible cargar el historial.";
  }
}

let learnerPageNumber = 1;
const learnerPageSize = 25;
let learnerStatusCounts = null;
let pendingFilterActive = false;

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

function syncLearnerFilterButtons() {
  const porCertificarActivo = normalizeStatusText(learnerStatus.value) === "por certificar";
  porCertificarLearnersButton.classList.toggle("is-active", porCertificarActivo);
  porCertificarLearnersButton.setAttribute("aria-pressed", porCertificarActivo ? "true" : "false");
  pendingLearnersButton.classList.toggle("is-active", pendingFilterActive);
  pendingLearnersButton.setAttribute("aria-pressed", pendingFilterActive ? "true" : "false");
}

async function refreshLearnerStatusCounts(statuses) {
  try {
    const entries = await Promise.all(
      statuses.map(async (status) => {
        const params = new URLSearchParams({ status, page: 1, page_size: 1 });
        const result = await readResponse(await fetch(`/api/learners?${params}`));
        return [normalizeStatusText(status), result.total];
      }),
    );
    learnerStatusCounts = new Map(entries);
  } catch (error) {
    learnerStatusCounts = null;
  }
}

function learnerSummaryLabel(result, conDesglose) {
  const total = result.total;
  const base = `${total} ${total === 1 ? "aprendiz registrado" : "aprendices registrados"}`;
  if (!conDesglose || !learnerStatusCounts) {
    return `${base} · ${result.por_certificar_total} por certificar`;
  }
  let certificados = 0;
  learnerStatusCounts.forEach((count, status) => {
    if (status.startsWith("certificado")) certificados += count;
  });
  const pendientes = Math.max(total - certificados, 0);
  return `${base} · ${certificados} ${certificados === 1 ? "certificado" : "certificados"} · ${pendientes} ${pendientes === 1 ? "pendiente" : "pendientes"}`;
}

function renderLearnerRow(item) {
  const row = document.createElement("tr");
  [item.name, item.identification, item.program || "Sin programa", item.group_code || "Sin ficha"]
    .forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    });
  row.appendChild(renderStatusCell(item.certification_status));
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

function renderLearnerEmptyState() {
  const searchTerm = learnerSearch.value.trim();
  const selectedStatus = learnerStatus.value;
  let message = "Aun no hay aprendices cargados. Confirma una importacion DF14A para empezar.";
  if (searchTerm && selectedStatus) {
    message = `No se encontro ningun aprendiz que coincida con "${searchTerm}" y tenga el estado "${selectedStatus}".`;
  } else if (searchTerm) {
    message = `No se encontro ningun aprendiz que coincida con "${searchTerm}".`;
  } else if (selectedStatus) {
    message = `No se encontro ningun aprendiz con el estado "${selectedStatus}".`;
  }
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 7;
  cell.textContent = message;
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
    pendingFilterActive = false;
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
    if (selectedStatus) setLearnerStatus(selectedStatus);
    porCertificarLearnersButton.textContent = `Por Certificar (${result.por_certificar_total})`;
    syncLearnerFilterButtons();
    const sinFiltros = !learnerSearch.value.trim() && !learnerStatus.value;
    if (sinFiltros) {
      await refreshLearnerStatusCounts(result.statuses);
    }
    learnersSummary.textContent = learnerSummaryLabel(result, sinFiltros);
    learnersPage.textContent = `Pagina ${result.page} de ${Math.max(result.pages, 1)}`;
    learnersPrev.disabled = result.page <= 1;
    learnersNext.disabled = result.page >= result.pages;
    if (!result.items.length) {
      renderLearnerEmptyState();
      return;
    }

    learnersList.replaceChildren(...result.items.map(renderLearnerRow));
  } catch (error) {
    learnersSummary.textContent = "No fue posible consultar SQLite";
    learnersList.textContent = "No fue posible cargar los aprendices.";
  }

}

async function loadPendingLearners() {
  try {
    pendingFilterActive = true;
    syncLearnerFilterButtons();
    const result = await readResponse(await fetch("/api/learners/with-pending-requirements"));
    learnersSummary.textContent = `${result.items.length} ${result.items.length === 1 ? "aprendiz" : "aprendices"} con requisitos pendientes`;
    learnersList.replaceChildren(...result.items.map((item) => {
      const row = renderLearnerRow(item);
      row.cells[5].textContent = item.pending_count;
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
porCertificarLearnersButton.addEventListener("click", () => {
  setLearnerStatus(
    learnerStatus.value.toLowerCase() === "por certificar" ? "" : "Por Certificar",
  );
  learnerPageNumber = 1;
  loadLearners();
});
pendingLearnersButton.addEventListener("click", () => {
  if (pendingFilterActive) {
    learnerPageNumber = 1;
    loadLearners();
    return;
  }
  loadPendingLearners();
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
  const target = ["aprendices", "actas", "indicadores"].includes(viewName) ? viewName : "carga";
  views.forEach((view) => {
    view.hidden = view.id !== `${target}-view`;
  });
  viewLinks.forEach((link) => link.classList.toggle("active", link.dataset.view === target));
  if (updateHash) history.replaceState(null, "", `#${target}`);
  if (target === "aprendices") loadLearners();
  if (target === "actas") loadActs();
  if (target === "indicadores") loadIndicadores();
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
function renderCausasChart(motivos) {
  const canvas = document.querySelector("#indicadores-causas-chart");
  const vacio = document.querySelector("#indicadores-causas-empty");
  if (!canvas || !vacio) return;

  if (graficoCausas) { graficoCausas.destroy(); graficoCausas = null; }

  const filas = motivos || [];
  if (!alternarPanelGrafico(canvas, vacio, filas.length ? "" : "Aún no hay causas registradas")) return;

  canvas.parentElement.style.height = `${Math.max(260, filas.length * 34 + 40)}px`;

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
    kpis.innerHTML = `
      <div class="panel"><div><small>META ANUAL</small><h2>${formatNumeroIndicador(data.total_meta)}</h2><small>Aprendices proyectados</small></div></div>
      <div class="panel" style="border-left:4px solid var(--green)"><div><small style="color:var(--green-dark)">CERTIFICADOS (ENE-SEP)</small><h2 style="color:var(--green-dark)">${formatNumeroIndicador(data.total_certificados)}</h2><small>Aprendices únicos</small></div></div>
      <div class="panel" style="border-left:4px solid #b87d00"><div><small style="color:#b87d00">PENDIENTES</small><h2 style="color:#b87d00">${formatNumeroIndicador(data.total_pendientes)}</h2><small>Aprendices únicos</small></div></div>
      <div class="panel" style="background:var(--green-soft)"><div><small style="color:var(--green-dark)">% AVANCE</small><h2 style="color:var(--green-dark)">${formatPorcentajeIndicador(data.avance_global)}</h2>${kpiBarraProgreso(data.avance_global)}<small>Acumulado</small></div></div>
      <div class="panel"><div><small>EFECTIVIDAD</small><h2>${formatPorcentajeIndicador(data.efectividad_global)}</h2>${kpiBarraProgreso(data.efectividad_global)}<small>Tasa de cierre</small></div></div>
    `;

    // Muestra por que algunos indicadores no se pudieron calcular (datos
    // faltantes, registros sin clasificar, filas fuera del periodo, etc.).
    // Se conserva toda la informacion: el panel solo queda colapsable y con un
    // contador visible para no perder las advertencias de vista.
    if (avisos) {
      const lista = data.advertencias || [];
      if (!lista.length) {
        avisos.innerHTML = "";
      } else {
        const etiqueta = lista.length === 1 ? "advertencia" : "advertencias";
        avisos.innerHTML = `
          <details class="avisos-panel">
            <summary>
              <span class="avisos-title">Datos y advertencias</span>
              <span class="avisos-badge">${lista.length} ${etiqueta}</span>
              <span class="avisos-toggle">Ver detalle</span>
            </summary>
            <p class="avisos-subtitle">${data.datos_suficientes ? "Resultados calculados con los documentos cargados." : "Aún no hay documentos suficientes para calcular los indicadores."}</p>
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

    if (causasTable && data.motivos) {
      if (causasSummary) {
        causasSummary.textContent = `${data.total_incidencias_causas} incidencias de requisitos (${formatNumeroIndicador(data.total_pendientes)} aprendices únicos)`;
      }
      if (causasCount) causasCount.textContent = formatNumeroIndicador(data.total_incidencias_causas);
      causasTable.innerHTML = data.motivos.map(mot => `
        <tr>
          <td>${mot.motivo}</td>
          <td><strong>${mot.cantidad.toLocaleString("es-CO")}</strong></td>
          <td><span class="result-badge pending">${formatPorcentajeIndicador(mot.porcentaje)}</span></td>
        </tr>
      `).join("");
      if (causasNote) {
        // Solo se calcula la diferencia cuando el total de pendientes existe;
        // si no se cargo la hoja PENDIENTES la comparacion no tiene sentido.
        const diferencia = data.total_pendientes === null || data.total_pendientes === undefined
          ? null
          : data.total_incidencias_causas - data.total_pendientes;
        causasNote.innerHTML = `◈ <strong>Auditoría de consistencia:</strong> Se registran <strong>${formatNumeroIndicador(data.total_pendientes)}</strong> aprendices únicos pendientes y <strong>${data.total_incidencias_causas}</strong> incidencias totales de causas.`
          + (diferencia === null
            ? " Cargue la hoja PENDIENTES para comparar aprendices únicos contra incidencias."
            : ` La diferencia de <strong>${diferencia}</strong> corresponde a causas múltiples por aprendiz (concurrencia de requisitos simultáneos no superados).`);
      }
    }

    if (actasTable && data.ultimas_actas) {
      if (actasSummary) {
        actasSummary.textContent = `${data.ultimas_actas.length} actas en el corte (Ene - Sep 2026)`;
      }
      if (actasCount) actasCount.textContent = data.ultimas_actas.length;
      if (data.ultimas_actas.length > 0) {
        actasTable.innerHTML = data.ultimas_actas.map(act => `
          <tr>
            <td><strong>${act.number}</strong></td>
            <td>${act.act_date || "No disponible"}</td>
            <td>${act.act_type || "No disponible"}</td>
            <td style="color:var(--green-dark);font-weight:700">${act.aprendices_count} asociados</td>
          </tr>
        `).join("");
      } else {
        actasTable.innerHTML = `<tr><td colspan="4" style="color:var(--muted)">Sin actas adicionales en la base de datos en este período.</td></tr>`;
      }
    }
    // Graficos complementarios (usan los mismos datos de las tablas de arriba).
    renderAvanceChart(data.metricas);
    renderCausasChart(data.motivos);
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
    const result = await readResponse(await fetch(`/api/acts?${new URLSearchParams({search: actSearch.value.trim(), ...(actStatusFilter.value ? {review_status: actStatusFilter.value} : {})})}`));
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
actStatusFilter.addEventListener("change", loadActs);
document.querySelector("#back-to-acts").addEventListener("click", () => { document.querySelectorAll("#actas-view > .panel").forEach((panel) => { panel.hidden = false; }); actDetail.hidden = true; });

categoryOptions.forEach((btn) => btn.addEventListener("click", () => setCategory(btn.dataset.category)));
typeOptions.forEach((option) => option.addEventListener("click", () => setType(option.dataset.type)));
selectButton.addEventListener("click", (event) => { event.stopPropagation(); fileInput.click(); });
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") fileInput.click(); });
fileInput.addEventListener("change", () => setFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.add("dragging"); }));
["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); }));
dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));
removeButton.addEventListener("click", clearFile);
cancelButton.addEventListener("click", () => { clearFile(); clearFeedback(); setCategory("datos_certificacion"); });
validateButton.addEventListener("click", validateFile);
confirmButton.addEventListener("click", confirmImport);
setCategory("datos_certificacion");
loadHistory();
loadLearners();
showView(window.location.hash === "#aprendices" ? "aprendices" : "carga", false);