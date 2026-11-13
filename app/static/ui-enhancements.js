/**
 * SENA Certificación — UI v2 enhancements
 * - Toasts
 * - Modal de revisión / conflictos de importación
 * - Barra de progreso al validar / confirmar
 * - KPIs + certificados por mes del consolidado en Indicadores
 * - Sidebar rail activo y pestañas pill
 */
(function () {
  "use strict";

  /* ---------------- Toasts ---------------- */
  function getToastContainer() {
    let el = document.getElementById("toast-container");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast-container";
      el.className = "toast-container";
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }
    return el;
  }

  function showToast(message, type = "info", options = {}) {
    if (!message) return null;
    const container = getToastContainer();
    const toast = document.createElement("div");
    const t = String(type).toLowerCase();
    const normalized =
      t === "error" || t === "danger"
        ? "error"
        : t === "success" || t === "ok"
          ? "success"
          : t === "warning" || t === "warn"
            ? "warning"
            : "info";
    toast.className = `toast toast-${normalized}`;
    toast.setAttribute("role", normalized === "error" ? "alert" : "status");
    const icons = { success: "✓", error: "✕", warning: "!", info: "i" };
    toast.innerHTML = `
      <span class="toast-icon" aria-hidden="true">${icons[normalized]}</span>
      <div class="toast-body"></div>
      <button type="button" class="toast-close" aria-label="Cerrar">×</button>
    `;
    toast.querySelector(".toast-body").textContent = message;
    const dismiss = () => {
      toast.classList.add("is-leaving");
      setTimeout(() => toast.remove(), 220);
    };
    toast.querySelector(".toast-close").addEventListener("click", dismiss);
    container.appendChild(toast);
    const duration = options.duration ?? 4500;
    if (duration > 0) setTimeout(dismiss, duration);
    return { dismiss };
  }

  window.showToast = showToast;

  /* ---------------- Generación de informes ---------------- */
  const reportModal = document.getElementById("report-modal");
  const reportOpen = document.getElementById("export-report-button");
  const reportClose = document.getElementById("report-modal-close");
  const reportCancel = document.getElementById("report-modal-cancel");
  const reportGenerate = document.getElementById("report-generate-button");
  const reportStatus = document.getElementById("report-modal-status");
  const reportTypeOptions = document.getElementById("report-type-options");
  const reportTypeDescription = document.getElementById("report-type-description");
  const reportScope = document.getElementById("report-scope");
  const reportDetail = document.getElementById("report-detail");
  const reportFormat = document.getElementById("report-format");
  const reportQuarter = document.getElementById("report-quarter");
  const reportMode = document.getElementById("report-mode");
  let selectedReportType = "consolidado";
  let reportCatalog = [];
  let isGenerating = false;

  function setStatus(message, kind) {
    if (!reportStatus) return;
    reportStatus.textContent = message || "";
    reportStatus.className = "report-modal-feedback" + (kind ? " " + kind : "");
  }

  async function loadCatalog() {
    try {
      const res = await fetch("/api/informes/catalog", { cache: "no-store" });
      if (!res.ok) throw new Error("No se pudo cargar el catálogo de informes.");
      reportCatalog = await res.json();
    } catch (error) {
      reportCatalog = [];
      setStatus(error.message, "error");
    }
    renderTypeOptions();
    updateControls();
  }

  function findType(type) {
    return reportCatalog.find((item) => item.type === type) || null;
  }

  function renderTypeOptions() {
    if (!reportTypeOptions) return;
    reportTypeOptions.replaceChildren();
    (reportCatalog.length ? reportCatalog : [
      { type: "consolidado", name: "Informe consolidado de certificación", description: "Resumen, categorías, evolución, pendientes, gestión documental y anexos.", formats: ["pdf", "xlsx"], scopes: ["consolidado"], details: ["completo", "ejecutivo"] },
    ]).forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "report-option" + (item.type === selectedReportType ? " is-selected" : "");
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", String(item.type === selectedReportType));
      button.dataset.reportType = item.type;
      button.innerHTML = `<span class="report-option-icon" aria-hidden="true">▤</span><span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.description)}</small><em>${item.formats.map((f) => f.toUpperCase()).join(" · ")}</em></span>`;
      button.addEventListener("click", () => {
        selectedReportType = item.type;
        renderTypeOptions();
        updateControls();
      });
      reportTypeOptions.appendChild(button);
    });
  }

  function currentType() {
    return findType(selectedReportType);
  }

  function updateControls() {
    const item = currentType();
    const formats = item ? item.formats : ["xlsx"];
    const scopes = item ? item.scopes : ["consolidado"];
    const details = item ? item.details : ["completo"];

    if (reportTypeDescription) {
      reportTypeDescription.textContent = item ? item.description : "";
    }

    if (reportScope) {
      reportScope.replaceChildren();
      scopes.forEach((scope) => {
        const label = scope === "filtrado" ? "Vista filtrada actual" : "Consolidado general";
        reportScope.add(new Option(label, scope));
      });
      reportScope.disabled = scopes.length <= 1;
    }

    if (reportDetail) {
      reportDetail.replaceChildren();
      details.forEach((detail) => {
        const label = detail === "ejecutivo" ? "Ejecutivo" : "Completo";
        reportDetail.add(new Option(label, detail));
      });
      reportDetail.disabled = details.length <= 1;
    }

    if (reportFormat) {
      const previous = reportFormat.value;
      reportFormat.replaceChildren();
      formats.forEach((format) => {
        reportFormat.add(new Option(format.toUpperCase(), format));
      });
      if (formats.includes(previous)) reportFormat.value = previous;
      else reportFormat.value = formats[0] || "xlsx";
    }

    // El informe de gestión oficial solo usa DOCX. Desde el modal se ofrece el
    // acceso directo a la sección donde se redactan las estrategias del periodo.
    if (reportOpenEstrategias) {
      const esInformeGestion =
        ["consolidado", "general"].includes(selectedReportType) &&
        formats.includes("docx");
      reportOpenEstrategias.hidden = !esInformeGestion;
    }
  }

  function getLearnerFilters() {
    const search = (document.getElementById("learner-search")?.value || "").trim();
    const status = document.getElementById("learner-status")?.value || "";
    return { search, status };
  }

  async function generateReport() {
    if (isGenerating) return;
    isGenerating = true;
    if (reportGenerate) {
      reportGenerate.disabled = true;
      reportGenerate.textContent = "Generando…";
    }
    setStatus("Generando el informe, por favor espera…", "info");
    try {
      const format = reportFormat?.value || "xlsx";
      const scope = reportScope?.value || "consolidado";
      const detail = reportDetail?.value || "completo";
      const params = new URLSearchParams({
        type: selectedReportType,
        format,
        scope,
        detail,
        trimestre: reportQuarter?.value || "T3",
        modo: reportMode?.value || "acumulado",
      });
      if (scope === "filtrado") {
        const filters = getLearnerFilters();
        params.set("search", filters.search);
        params.set("status", filters.status);
      }
      const response = await fetch(`/api/informes/export?${params.toString()}`, {
        method: "GET",
      });
      if (!response.ok) {
        let message = "No se pudo generar el informe.";
        try {
          const data = await response.json();
          if (data && data.detail) message = data.detail;
        } catch (_) {}
        throw new Error(message);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/i);
      link.download = match ? match[1] : `informe_${selectedReportType}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus("Informe generado y descargado correctamente.", "success");
      showToast("Informe generado correctamente.", "success");
      window.setTimeout(closeReportModal, 900);
    } catch (error) {
      setStatus(error.message || "No se pudo generar el informe.", "error");
      showToast(error.message || "No se pudo generar el informe.", "error");
    } finally {
      isGenerating = false;
      if (reportGenerate) {
        reportGenerate.disabled = false;
        reportGenerate.textContent = "Generar informe";
      }
    }
  }

  function closeReportModal() {
    if (reportModal) {
      reportModal.classList.remove("is-open");
      reportModal.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    }
  }

  function openReportModal() {
    if (!reportModal) return;
    reportModal.classList.add("is-open");
    reportModal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    setStatus("", "");
    reportGenerate?.focus();
  }

  reportOpen?.addEventListener("click", openReportModal);
  reportClose?.addEventListener("click", closeReportModal);
  reportCancel?.addEventListener("click", closeReportModal);
  reportModal?.querySelectorAll("[data-close-report-modal]").forEach((element) => {
    element.addEventListener("click", closeReportModal);
  });
  reportGenerate?.addEventListener("click", generateReport);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && reportModal?.classList.contains("is-open")) {
      closeReportModal();
    }
  });

  loadCatalog();

  /* ---------------- Informe de gestión: estrategias por periodo ---------------- */
  const informeView = document.getElementById("informe-gestion-view");
  const informeAnio = document.getElementById("informe-anio");
  const informeTrimestre = document.getElementById("informe-trimestre");
  const informeForm = document.getElementById("informe-estrategias-form");
  const informeSave = document.getElementById("informe-estrategias-save");
  const informeStatus = document.getElementById("informe-estrategias-status");
  const informeBadge = document.getElementById("informe-estrategias-badge");
  const informeExportMode = document.getElementById("informe-export-mode");
  const informeExportGenerate = document.getElementById("informe-export-generate");
  const informeExportStatus = document.getElementById("informe-export-status");
  const informeExportSummary = document.getElementById("informe-export-summary");
  const informeExportPeriodo = document.getElementById("informe-export-periodo");
  const informeExportHint = document.getElementById("informe-export-hint");
  const informeTabButtons = document.querySelectorAll("[data-informe-tab]");
  const informePanels = document.querySelectorAll("[data-informe-panel]");
  const informeTextareas = document.querySelectorAll("[data-estrategia-seccion]");
  const informeQuickInputs = document.querySelectorAll("[data-estrategia-quick]");
  const informeAccordionToggles = document.querySelectorAll("[data-accordion-toggle]");
  const informeContextCards = document.querySelectorAll("[data-context-section]");
  const reportOpenEstrategias = document.getElementById("report-open-estrategias");
  const SECCIONES_INFORME = [
    ["3.1.1", "Educación Superior"],
    ["3.1.2", "Técnico Laboral y Otros (sin incluir Media Técnica)"],
    ["3.1.3", "Articulación con la Media"],
    ["3.1.4", "Formación Complementaria"],
    ["3.1.5", "Certificación Total / Centros de Formación"],
    ["3.2", "Otras actividades del trimestre"],
  ];
  const ROMANOS = { T1: "I", T2: "II", T3: "III", T4: "IV" };
  // Cada bloque del informe consume una categoría del consolidado ACTAS.
  const CONTEXTO_POR_SECCION = {
    "3.1.1": "superior",
    "3.1.2": "tecnica",
    "3.1.3": "articulacion",
    "3.1.4": "complementaria",
  };
  const numeroInforme = new Intl.NumberFormat("es-CO");
  const porcentajeInforme = new Intl.NumberFormat("es-CO", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const quickInputPorCodigo = new Map(
    Array.from(informeQuickInputs).map((input) => [input.dataset.estrategiaQuick, input]),
  );
  const textareaPorCodigo = new Map(
    Array.from(informeTextareas).map((textarea) => [
      textarea.dataset.estrategiaSeccion,
      textarea,
    ]),
  );

  let informePeriodoActual = { anio: 2026, trimestre: "T3" };
  let informeCargado = false;
  let informeDirty = false;
  let informeLoadToken = 0;
  let informeContextoToken = 0;

  function setInformeStatus(element, message, kind) {
    if (!element) return;
    element.textContent = message || "";
    element.className = "detail-feedback" + (kind ? " " + kind : "");
  }

  function periodoInforme() {
    const anio = Number.parseInt(informeAnio?.value, 10) || 2026;
    return {
      anio,
      trimestre: informeTrimestre?.value || "T3",
    };
  }

  function etiquetaPeriodo({ anio, trimestre }) {
    return `Trimestre ${ROMANOS[trimestre] || trimestre} ${anio}`;
  }

  function seccionesDelFormulario() {
    const secciones = {};
    informeTextareas.forEach((textarea) => {
      secciones[textarea.dataset.estrategiaSeccion] = textarea.value || "";
    });
    return secciones;
  }

  function marcarInformeDirty(dirty) {
    informeDirty = dirty;
    if (!informeBadge) return;
    informeBadge.textContent = dirty ? "SIN GUARDAR" : "GUARDADO";
    informeBadge.className = "result-badge " + (dirty ? "pending" : "ready");
  }

  function sincronizarBorradoresRapidos(secciones) {
    informeQuickInputs.forEach((input) => {
      const codigo = input.dataset.estrategiaQuick;
      input.value = secciones[codigo] || "";
    });
  }

  function alternarAcordeon(button) {
    const article = button.closest("[data-accordion-section]");
    const panel = document.getElementById(button.getAttribute("aria-controls") || "");
    if (!article || !panel) return;
    const abierto = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!abierto));
    article.classList.toggle("is-open", !abierto);
    panel.hidden = abierto;
  }

  function numeroInformeValido(value) {
    return (
      value !== null &&
      value !== undefined &&
      value !== "" &&
      Number.isFinite(Number(value))
    );
  }

  function formatearNumeroInforme(value) {
    return numeroInformeValido(value) ? numeroInforme.format(Number(value)) : "—";
  }

  function formatearPorcentajeInforme(value) {
    return numeroInformeValido(value)
      ? `${porcentajeInforme.format(Number(value))}%`
      : "—";
  }

  function severidadContexto(avance) {
    if (!numeroInformeValido(avance)) {
      return { clase: "is-neutral", texto: "Sin datos" };
    }
    const valor = Number(avance);
    if (valor >= 100) return { clase: "is-good", texto: "Meta cumplida" };
    if (valor >= 60) return { clase: "is-good", texto: "En camino" };
    if (valor >= 30) return { clase: "is-warning", texto: "En riesgo" };
    return { clase: "is-critical", texto: "Crítico" };
  }

  function renderContextoSeccion(codigo, metrica) {
    const card = Array.from(informeContextCards).find(
      (element) => element.dataset.contextSection === codigo,
    );
    if (!card) return;

    const meta = metrica?.meta ?? null;
    const ejecucion = metrica?.certificados ?? metrica?.total_certificados ?? null;
    let avance = metrica?.avance ?? null;
    if (
      !numeroInformeValido(avance) &&
      numeroInformeValido(meta) &&
      Number(meta) > 0 &&
      numeroInformeValido(ejecucion)
    ) {
      avance = (Number(ejecucion) / Number(meta)) * 100;
    }

    const severidad = severidadContexto(avance);
    const porcentaje = formatearPorcentajeInforme(avance);
    const ancho = numeroInformeValido(avance)
      ? Math.min(100, Math.max(0, Number(avance)))
      : 0;

    const metaEl = card.querySelector("[data-context-meta]");
    const ejecucionEl = card.querySelector("[data-context-ejecucion]");
    const ejecucionPctEl = card.querySelector("[data-context-ejecucion-pct]");
    const pctEl = card.querySelector("[data-context-pct]");
    const barEl = card.querySelector("[data-context-bar]");
    const badgeEl = card.querySelector("[data-context-badge]");

    if (metaEl) metaEl.textContent = formatearNumeroInforme(meta);
    if (ejecucionEl) ejecucionEl.textContent = formatearNumeroInforme(ejecucion);
    if (ejecucionPctEl) {
      ejecucionPctEl.textContent = numeroInformeValido(avance)
        ? `${porcentaje} del avance`
        : "Sin porcentaje";
    }
    if (pctEl) pctEl.textContent = porcentaje;
    if (barEl) barEl.style.width = `${ancho.toFixed(1)}%`;

    card.classList.remove("is-neutral", "is-critical", "is-warning", "is-good");
    card.classList.add(severidad.clase);
    if (badgeEl) {
      badgeEl.classList.remove("is-neutral", "is-critical", "is-warning", "is-good");
      badgeEl.classList.add(severidad.clase);
      const em = badgeEl.querySelector("em");
      if (em) em.textContent = severidad.texto;
    }
  }

  function renderContextoInforme(data, periodo) {
    const etiqueta = etiquetaPeriodo(periodo);
    document.querySelectorAll("[data-context-periodo]").forEach((element) => {
      element.textContent = etiqueta;
    });

    const metricas = data?.metricas || data?.desglose_por_categoria || [];
    const porCategoria = new Map(
      metricas.map((metrica) => [metrica.category, metrica]),
    );
    Object.entries(CONTEXTO_POR_SECCION).forEach(([codigo, categoria]) => {
      renderContextoSeccion(codigo, porCategoria.get(categoria));
    });

    const resumen = data?.resumen_ejecutivo || {};
    renderContextoSeccion("3.1.5", {
      meta: resumen.meta_total ?? resumen.total_meta ?? null,
      certificados:
        resumen.total_certificados ?? resumen.certificados_personas ?? null,
      avance: resumen.avance_global ?? null,
    });
  }

  async function cargarContextoInforme() {
    if (!informeView || !informeContextCards.length) return;
    const periodo = periodoInforme();
    const modo = informeExportMode?.value || "acumulado";
    const token = ++informeContextoToken;
    try {
      const params = new URLSearchParams({
        year: String(periodo.anio),
        trimestre: periodo.trimestre,
        modo,
      });
      const response = await fetch(
        `/api/informes/consolidado?${params.toString()}`,
        { cache: "no-store" },
      );
      if (!response.ok) {
        throw new Error("No se pudo cargar el contexto estadístico.");
      }
      const data = await response.json();
      if (token !== informeContextoToken) return;
      renderContextoInforme(data, periodo);
    } catch (_) {
      if (token !== informeContextoToken) return;
      renderContextoInforme(null, periodo);
    }
  }

  function renderResumenEstrategias(secciones, periodo = periodoInforme()) {
    const cargadas = SECCIONES_INFORME.filter(
      ([key]) => String(secciones[key] || "").trim().length > 0,
    ).length;
    if (informeExportPeriodo) {
      informeExportPeriodo.textContent = etiquetaPeriodo(periodo);
    }
    if (informeExportSummary) {
      informeExportSummary.replaceChildren();
      SECCIONES_INFORME.forEach(([key, label]) => {
        const tieneTexto = String(secciones[key] || "").trim().length > 0;
        const item = document.createElement("li");
        item.className = tieneTexto ? "is-filled" : "is-empty";
        const code = document.createElement("strong");
        code.textContent = key;
        const text = document.createElement("span");
        text.textContent = label;
        const state = document.createElement("em");
        state.textContent = tieneTexto ? "Cargada" : "Pendiente";
        item.append(code, text, state);
        informeExportSummary.appendChild(item);
      });
    }
    if (informeExportHint) {
      informeExportHint.textContent = cargadas
        ? `${cargadas} de ${SECCIONES_INFORME.length} secciones tienen texto. Las vacías se generarán con el placeholder institucional.`
        : "Aún no hay estrategias guardadas para este periodo. Las secciones vacías se generarán con el placeholder institucional.";
    }
  }

  function aplicarEstrategias(data, periodo = periodoInforme()) {
    const secciones = data?.secciones || {};
    informeTextareas.forEach((textarea) => {
      textarea.value = secciones[textarea.dataset.estrategiaSeccion] || "";
    });
    sincronizarBorradoresRapidos(secciones);
    marcarInformeDirty(false);
    renderResumenEstrategias(secciones, periodo);
    const cargadas = SECCIONES_INFORME.filter(
      ([key]) => String(secciones[key] || "").trim().length > 0,
    ).length;
    setInformeStatus(
      informeStatus,
      cargadas
        ? `Textos de ${etiquetaPeriodo(periodo)} cargados.`
        : `No hay textos guardados para ${etiquetaPeriodo(periodo)} todavía.`,
      "",
    );
  }

  async function cargarEstrategias() {
    if (!informeView) return;
    const periodo = periodoInforme();
    informePeriodoActual = periodo;
    const token = ++informeLoadToken;
    cargarContextoInforme();
    setInformeStatus(informeStatus, "Cargando estrategias del periodo…", "info");
    try {
      const params = new URLSearchParams({
        anio: String(periodo.anio),
        trimestre: periodo.trimestre,
      });
      const response = await fetch(`/api/informes/estrategias?${params.toString()}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        let message = "No se pudieron cargar las estrategias del periodo.";
        try {
          const data = await response.json();
          if (data?.detail) message = data.detail;
        } catch (_) {}
        throw new Error(message);
      }
      const data = await response.json();
      if (token !== informeLoadToken) return;
      informeCargado = true;
      aplicarEstrategias(data, periodo);
    } catch (error) {
      if (token !== informeLoadToken) return;
      informeCargado = false;
      setInformeStatus(informeStatus, error.message, "error");
      renderResumenEstrategias(seccionesDelFormulario(), periodo);
    }
  }

  async function guardarEstrategias({ event, periodo, silent = false } = {}) {
    if (event) event.preventDefault();
    if (!informeForm) return false;
    const objetivo = periodo || periodoInforme();
    const secciones = seccionesDelFormulario();
    if (informeSave) informeSave.disabled = true;
    if (!silent) setInformeStatus(informeStatus, "Guardando estrategias…", "info");
    try {
      const response = await fetch("/api/informes/estrategias", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          anio: objetivo.anio,
          trimestre: objetivo.trimestre,
          secciones,
        }),
      });
      if (!response.ok) {
        let message = "No se pudieron guardar las estrategias.";
        try {
          const data = await response.json();
          if (data?.detail) message = data.detail;
        } catch (_) {}
        throw new Error(message);
      }
      const data = await response.json();
      informePeriodoActual = objetivo;
      if (!silent) {
        aplicarEstrategias(data, objetivo);
        setInformeStatus(
          informeStatus,
          `Estrategias de ${etiquetaPeriodo(objetivo)} guardadas.`,
          "success",
        );
        showToast("Estrategias guardadas correctamente.", "success");
      } else {
        marcarInformeDirty(false);
      }
      return true;
    } catch (error) {
      setInformeStatus(
        informeStatus,
        error.message || "No se pudieron guardar las estrategias.",
        "error",
      );
      if (!silent) showToast(error.message, "error");
      return false;
    } finally {
      if (informeSave) informeSave.disabled = false;
    }
  }

  function activarTabInforme(nombre) {
    informeTabButtons.forEach((button) => {
      const activo = button.dataset.informeTab === nombre;
      button.classList.toggle("is-active", activo);
      button.setAttribute("aria-selected", String(activo));
    });
    informePanels.forEach((panel) => {
      const activo = panel.dataset.informePanel === nombre;
      panel.classList.toggle("is-active", activo);
      panel.hidden = !activo;
    });
    // El periodo es único para las tres pestañas. Al entrar en Exportar se
    // refresca el resumen desde la BD para no depender de haber visitado
    // Estrategias en esta sesión (nunca se pisa un borrador sin guardar).
    if (nombre === "exportar" && !informeDirty) {
      cargarEstrategias();
    }
  }

  informeTabButtons.forEach((button) => {
    button.addEventListener("click", () => activarTabInforme(button.dataset.informeTab));
  });

  informeAccordionToggles.forEach((button) => {
    button.addEventListener("click", () => alternarAcordeon(button));
  });

  informeForm?.addEventListener("submit", (event) => guardarEstrategias({ event }));
  informeTextareas.forEach((textarea) => {
    textarea.addEventListener("input", () => {
      const quick = quickInputPorCodigo.get(textarea.dataset.estrategiaSeccion);
      if (quick) quick.value = textarea.value;
      marcarInformeDirty(true);
      renderResumenEstrategias(seccionesDelFormulario());
      setInformeStatus(informeStatus, "Cambios sin guardar.", "warning");
    });
  });

  informeQuickInputs.forEach((input) => {
    const codigo = input.dataset.estrategiaQuick;
    input.addEventListener("input", () => {
      const textarea = textareaPorCodigo.get(codigo);
      if (textarea) textarea.value = input.value;
      marcarInformeDirty(true);
      renderResumenEstrategias(seccionesDelFormulario());
      setInformeStatus(informeStatus, "Cambios sin guardar.", "warning");
    });
  });

  informeExportMode?.addEventListener("change", () => {
    cargarContextoInforme();
  });

  function restaurarPeriodoInforme(periodo) {
    if (informeAnio) informeAnio.value = String(periodo.anio);
    if (informeTrimestre) informeTrimestre.value = periodo.trimestre;
  }

  async function cambiarPeriodoInforme() {
    const anterior = { ...informePeriodoActual };
    const nuevo = periodoInforme();
    if (nuevo.anio === anterior.anio && nuevo.trimestre === anterior.trimestre) {
      return;
    }
    if (informeDirty) {
      // Cambiar de periodo recarga los textos de (año, trimestre). Si hay
      // cambios sin guardar hay que confirmarlo antes de abandonar el periodo.
      const continuar = window.confirm(
        `Hay cambios sin guardar en ${etiquetaPeriodo(anterior)}. ` +
          "Se guardarán antes de cambiar de periodo. ¿Deseas continuar?",
      );
      if (!continuar) {
        restaurarPeriodoInforme(anterior);
        setInformeStatus(informeStatus, "Cambio de periodo cancelado.", "warning");
        return;
      }
      const guardado = await guardarEstrategias({ periodo: anterior, silent: true });
      if (!guardado) {
        // No se abandona el periodo si el guardado automático falla.
        restaurarPeriodoInforme(anterior);
        return;
      }
    }
    informePeriodoActual = nuevo;
    await cargarEstrategias();
  }

  informeAnio?.addEventListener("change", cambiarPeriodoInforme);
  informeTrimestre?.addEventListener("change", cambiarPeriodoInforme);

  async function generarInformeGestion() {
    if (!informeExportGenerate) return;
    const periodo = periodoInforme();
    // El DOCX se genera en el servidor leyendo las estrategias de la BD para
    // (año, trimestre). No depende de haber visitado la pestaña Estrategias.
    if (
      !informeDirty &&
      (periodo.anio !== informePeriodoActual.anio ||
        periodo.trimestre !== informePeriodoActual.trimestre)
    ) {
      await cargarEstrategias();
    }
    if (informeDirty) {
      const guardado = await guardarEstrategias({ silent: true });
      if (!guardado) {
        setInformeStatus(
          informeExportStatus,
          "Guarda las estrategias antes de generar el informe.",
          "error",
        );
        return;
      }
    }
    const modo = informeExportMode?.value || "acumulado";
    informeExportGenerate.disabled = true;
    setInformeStatus(informeExportStatus, "Generando el informe de gestión…", "info");
    try {
      const params = new URLSearchParams({
        year: String(periodo.anio),
        trimestre: periodo.trimestre,
        modo,
      });
      const response = await fetch(`/api/informes/word?${params.toString()}`, {
        method: "GET",
      });
      if (!response.ok) {
        let message = "No se pudo generar el informe de gestión.";
        try {
          const data = await response.json();
          if (data?.detail) message = data.detail;
        } catch (_) {}
        throw new Error(message);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/i);
      link.download =
        match?.[1] ||
        `informe_gestion_${periodo.anio}_${periodo.trimestre}_${modo}.docx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setInformeStatus(
        informeExportStatus,
        `Informe de ${etiquetaPeriodo(periodo)} generado y descargado.`,
        "success",
      );
      showToast("Informe de gestión generado correctamente.", "success");
    } catch (error) {
      setInformeStatus(
        informeExportStatus,
        error.message || "No se pudo generar el informe de gestión.",
        "error",
      );
      showToast(error.message || "No se pudo generar el informe.", "error");
    } finally {
      informeExportGenerate.disabled = false;
    }
  }

  informeExportGenerate?.addEventListener("click", generarInformeGestion);

  window.setInformeGestionPeriodo = function setInformeGestionPeriodo(trimestre) {
    if (informeTrimestre && trimestre) informeTrimestre.value = trimestre;
  };

  reportOpenEstrategias?.addEventListener("click", () => {
    window.setInformeGestionPeriodo?.(reportQuarter?.value || "T3");
    closeReportModal();
    if (typeof window.showView === "function") window.showView("informe-gestion");
    else window.location.hash = "#informe-gestion";
  });

  window.addEventListener("sena:view-changed", (event) => {
    if (event.detail?.view !== "informe-gestion") return;
    activarTabInforme("estrategias");
    if (!informeCargado || informeDirty === false) cargarEstrategias();
  });

  if (informeView && !informeView.hidden) {
    cargarEstrategias();
  }

  function observeFeedback() {
    const feedbackEl = document.getElementById("feedback");
    if (!feedbackEl) return;
    let last = "";
    const obs = new MutationObserver(() => {
      const text = (feedbackEl.textContent || "").trim();
      if (!text || text === last) return;
      last = text;
      const err =
        feedbackEl.classList.contains("error") ||
        /error|falló|invalid|rechaz|no se pudo/i.test(text);
      const info = /validando|revisa el resumen|aun no|aún no|preliminar/i.test(text);
      const ok = /correctamente|completad|procesad|importad|guardad[oa]s?|éxito|exito/i.test(text);
      showToast(text, err ? "error" : info ? "info" : ok ? "success" : "warning");
    });
    obs.observe(feedbackEl, {
      childList: true,
      characterData: true,
      subtree: true,
      attributes: true,
    });
  }

  /* ---------------- Estado posterior a la importación ---------------- */
  function observeImportCompletion() {
    const fileStatus = document.getElementById("file-status");
    const fileDetails = document.getElementById("file-details");
    const validationMessage = document.getElementById("validation-message");
    const validationStatus = document.getElementById("validation-status");
    if (!fileStatus || !validationMessage || !validationStatus) return;
    const sync = () => {
      if (!/importaci[oó]n completa/i.test(fileStatus.textContent || "")) return;
      if (fileDetails) {
        fileDetails.textContent = (fileDetails.textContent || "").replace(
          /listo para validar/i,
          "importación completada"
        );
      }
      validationMessage.textContent =
        "Importación completada. Los registros ya están guardados en la base de datos.";
      validationStatus.textContent = "IMPORTACIÓN COMPLETA";
      validationStatus.className = "result-badge ready";
    };
    new MutationObserver(sync).observe(fileStatus, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }

  /* ---------------- Modal importación ---------------- */
  const modal = document.getElementById("import-modal");
  const modalBody = document.getElementById("import-modal-body");
  const modalDialog = modal?.querySelector(".modal-dialog");
  const modalConfirm = document.getElementById("modal-confirm-button");
  const modalCancel = document.getElementById("modal-cancel-button");
  const modalClose = document.getElementById("modal-close-button");
  const modalProgress = document.getElementById("modal-progress");
  const modalProgressLabel = document.getElementById("modal-progress-label");
  const confirmationPanel = document.getElementById("confirmation-panel");
  const confirmButton = document.getElementById("confirm-button");
  const cancelButton = document.getElementById("cancel-button");

  function syncModalConfirmState() {
    if (!modalConfirm || !confirmButton) return;
    modalConfirm.hidden = confirmButton.hidden;
    modalConfirm.disabled = confirmButton.disabled;
  }

  function syncModalProgress() {
    if (!modalProgress) return;
    const active = globalProgress ? !globalProgress.hidden : false;
    modalProgress.hidden = !(active && modal?.classList.contains("is-open"));
    if (active && modalProgressLabel && progressLabel) {
      modalProgressLabel.textContent = progressLabel.textContent;
    }
  }

  function openImportModal() {
    if (!modal || !confirmationPanel || !modalBody) return;
    if (confirmationPanel.parentElement !== modalBody) {
      modalBody.appendChild(confirmationPanel);
    }
    confirmationPanel.hidden = false;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    syncModalConfirmState();
    syncModalProgress();
    setTimeout(() => {
      const focusTarget = document.getElementById("confirm-summary") || confirmationPanel || modalDialog;
      const reduce = typeof window.matchMedia === "function"
        && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (modalDialog) {
        modalDialog.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
      }
      focusTarget?.focus?.({ preventScroll: true });
    }, 30);
  }

  function closeImportModal() {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    if (modalProgress) modalProgress.hidden = true;
    if (confirmationPanel) confirmationPanel.hidden = true;
    const host =
      document.querySelector("#carga-view .main-column") ||
      document.getElementById("carga-view");
    if (confirmationPanel && host && confirmationPanel.parentElement === modalBody) {
      const actions = host.querySelector(".actions");
      if (actions) host.insertBefore(confirmationPanel, actions);
      else host.appendChild(confirmationPanel);
    }
  }

  function cancelModal() {
    cancelButton?.click();
    closeImportModal();
  }

  if (confirmationPanel) {
    const panelObs = new MutationObserver(() => {
      if (!confirmationPanel.hidden) openImportModal();
      else if (modal?.classList.contains("is-open")) closeImportModal();
      syncModalConfirmState();
    });
    panelObs.observe(confirmationPanel, {
      attributes: true,
      attributeFilter: ["hidden"],
    });
  }

  if (confirmButton) {
    const btnObs = new MutationObserver(() => {
      syncModalConfirmState();
      // app.js oculta el botón al terminar la importación. En ese momento
      // cerramos el modal para que el usuario vea el resultado en la vista.
      if (
        confirmButton.hidden &&
        modal?.classList.contains("is-open") &&
        confirmationPanel &&
        !confirmationPanel.hidden
      ) {
        closeImportModal();
      }
    });
    btnObs.observe(confirmButton, {
      attributes: true,
      attributeFilter: ["hidden", "disabled"],
    });
  }

  modal?.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", cancelModal);
  });
  modalClose?.addEventListener("click", cancelModal);
  modalCancel?.addEventListener("click", cancelModal);

  modalConfirm?.addEventListener("click", () => {
    if (confirmButton && !confirmButton.disabled) confirmButton.click();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal?.classList.contains("is-open")) {
      // El modal "Antes de confirmar" se superpone a la revisión; su tecla
      // Escape solo debe cerrar esa advertencia, no cancelar la importación.
      const warningModal = document.getElementById("conflict-confirm-modal");
      if (warningModal?.classList.contains("is-open")) return;
      cancelModal();
    }
  });

  // Foco contenido dentro del modal (accesibilidad básica).
  modal?.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const focusables = [
      ...modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      ),
    ].filter((el) => !el.hidden && !el.disabled && el.offsetParent !== null);
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });

  /* ---------------- Barra de progreso ---------------- */
  const progress = document.getElementById("upload-progress");
  const progressLabel = document.getElementById("upload-progress-label");
  const globalProgress = document.getElementById("global-progress");
  let progressOps = 0;
  let progressHideTimer = null;

  function setProgress(active, label) {
    const isActive = Boolean(active);
    if (progress) progress.classList.toggle("is-active", isActive);
    if (globalProgress) globalProgress.hidden = !isActive;
    if (modalProgress) {
      modalProgress.hidden = !(isActive && modal?.classList.contains("is-open"));
    }
    if (label) {
      if (progressLabel) progressLabel.textContent = label;
      if (modalProgressLabel) modalProgressLabel.textContent = label;
      if (globalProgress) globalProgress.setAttribute("aria-valuetext", label);
    }
  }

  function beginProgress(label) {
    progressOps += 1;
    if (progressHideTimer) {
      clearTimeout(progressHideTimer);
      progressHideTimer = null;
    }
    setProgress(true, label);
  }

  function endProgress() {
    progressOps = Math.max(0, progressOps - 1);
    if (progressOps > 0) return;
    if (progressHideTimer) clearTimeout(progressHideTimer);
    progressHideTimer = setTimeout(() => {
      progressHideTimer = null;
      if (progressOps === 0) setProgress(false);
    }, 350);
  }

  const originalFetch = window.fetch;
  window.fetch = function patchedFetch(input, init) {
    const url =
      typeof input === "string" ? input : input && input.url ? String(input.url) : "";
    const isValidate = url.includes("/api/files/validate");
    const isPreview = url.includes("/api/imports/") && url.includes("/preview");
    const isConfirm = url.includes("/api/imports/") && url.includes("/confirm");
    let started = false;
    if (isValidate) {
      beginProgress("Subiendo y validando archivo…");
      started = true;
    } else if (isPreview) {
      beginProgress("Preparando vista previa…");
      started = true;
    } else if (isConfirm) {
      beginProgress("Confirmando importación…");
      started = true;
    }
    return originalFetch.apply(this, arguments).finally(() => {
      if (started) endProgress();
    });
  };

  /* ---------------- Sidebar active state ---------------- */
  function activateSidebar(view) {
    document.querySelectorAll(".sidebar-link[data-view]").forEach((link) => {
      const isActive = link.dataset.view === view;
      link.classList.toggle("active", isActive);
      if (isActive) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  /* ---------------- Ajuste de layout de gráficos ---------------- */
  function fixChartPadding() {
    if (!window.Chart) return;
    document.querySelectorAll("#indicadores-view canvas").forEach((canvas) => {
      const chart = window.Chart.getChart(canvas);
      if (!chart || !chart.data?.labels?.length) return;
      if (!chart.chartArea || !chart.chartArea.left) return;
      const padding = chart.options.layout?.padding || {};
      const target = chart.width < 340 ? 80 : 48;
      if (Number(padding.left) >= target) return;
      const needsRoom = chart.data.labels.some((label) =>
        (Array.isArray(label) ? label : [label]).some(
          (line) => String(line).length > 18
        )
      );
      if (!needsRoom) return;
      chart.options.layout.padding = { ...padding, left: target };
      chart.update("none");
    });
  }

  function scheduleChartPadding(attempt = 0) {
    if (!window.Chart) return;
    fixChartPadding();
    const charts = [...document.querySelectorAll("#indicadores-view canvas")].map((canvas) =>
      window.Chart.getChart(canvas)
    );
    const pending = charts.filter((chart) => {
      if (!chart || !chart.data?.labels?.length) return false;
      const target = chart.width < 340 ? 80 : 48;
      const needsRoom = chart.data.labels.some((label) =>
        (Array.isArray(label) ? label : [label]).some(
          (line) => String(line).length > 18
        )
      );
      return needsRoom && Number(chart.options.layout?.padding?.left) < target;
    });
    const missing = charts.some((chart) => !chart);
    if ((pending.length || missing) && attempt < 15) {
      setTimeout(() => scheduleChartPadding(attempt + 1), 100);
    }
  }

  /* ---------------- Indicadores: KPIs + heatmap real ---------------- */
  function formatNum(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return Number(n).toLocaleString("es-CO");
  }

  async function safeJson(url) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? "—";
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => {
      const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
      return map[char];
    });
  }

  async function loadIndicadoresExtras() {
    const [indicadores, acts, learners] = await Promise.all([
      safeJson("/api/indicadores"),
      safeJson("/api/acts"),
      safeJson("/api/learners?page=1&page_size=1"),
    ]);

    if (indicadores) {
      const cert =
        indicadores.certificados_personas ??
        indicadores.certificados ??
        indicadores.total_certificados ??
        indicadores.resumen?.certificados ??
        indicadores.kpis?.certificados;
      const por =
        indicadores.pendientes_personas ??
        indicadores.total_pendientes ??
        indicadores.por_certificar ??
        indicadores.total_por_certificar ??
        indicadores.resumen?.por_certificar ??
        indicadores.kpis?.por_certificar;
      setText("ind-metric-certificados", formatNum(cert));
      setText("ind-metric-por-certificar", formatNum(por));
    }
    if (acts) {
      const total =
        acts.total ?? acts.count ?? (Array.isArray(acts.items) ? acts.items.length : null);
      setText("ind-metric-actas", formatNum(total));
    }
    if (learners) {
      setText(
        "ind-metric-learners",
        formatNum(learners.total ?? learners.count ?? learners.total_count)
      );
    }

    const yearSel = document.getElementById("heatmap-year");
    const year = Number(yearSel?.value || 2026);
    await loadActivity(year);
    scheduleChartPadding();
  }

  const tooltip = document.getElementById("heatmap-tooltip") || createTooltip();
  let tooltipRequest = 0;

  function createTooltip() {
    const el = document.createElement("div");
    el.id = "heatmap-tooltip";
    el.className = "heatmap-tooltip";
    el.setAttribute("role", "tooltip");
    el.setAttribute("aria-hidden", "true");
    document.body.appendChild(el);
    return el;
  }

  function hideTooltip() {
    tooltipRequest += 1;
    tooltip.classList.remove("is-visible");
    tooltip.innerHTML = "";
    tooltip.setAttribute("aria-hidden", "true");
  }

  function positionTooltip(evt, anchor) {
    const pad = 14;
    let x;
    let y;
    if (evt && Number.isFinite(evt.clientX) && Number.isFinite(evt.clientY)) {
      x = evt.clientX + pad;
      y = evt.clientY + pad;
    } else if (anchor) {
      const rect = anchor.getBoundingClientRect();
      x = rect.left + rect.width + pad;
      y = rect.top;
    } else {
      x = window.innerWidth / 2;
      y = window.innerHeight / 2;
    }
    const maxX = window.innerWidth - 340;
    const maxY = window.innerHeight - 140;
    tooltip.style.left = `${Math.max(8, Math.min(maxX, x))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(maxY, y))}px`;
  }

  function showEmptyDay(day, evt, anchor) {
    tooltipRequest += 1;
    positionTooltip(evt, anchor);
    tooltip.innerHTML = `<strong>${escapeHtml(day)}</strong><div>Sin actividad registrada.</div>`;
    tooltip.classList.add("is-visible");
    tooltip.setAttribute("aria-hidden", "false");
  }

  async function showDayDetails(day, evt, anchor) {
    const token = ++tooltipRequest;
    positionTooltip(evt, anchor);
    tooltip.innerHTML = `<strong>${escapeHtml(day)}</strong><div>Cargando aprendices…</div>`;
    tooltip.classList.add("is-visible");
    tooltip.setAttribute("aria-hidden", "false");

    const data = await safeJson(`/api/activity/day/${encodeURIComponent(day)}`);
    if (token !== tooltipRequest) return;
    if (!data) {
      tooltip.innerHTML = `<strong>${escapeHtml(day)}</strong><div>Sin detalle disponible (¿endpoint activo?).</div>`;
      return;
    }

    const learners = Array.isArray(data.learners) ? data.learners : [];
    const imports = Array.isArray(data.imports) ? data.imports : [];
    let html = `<strong>${escapeHtml(data.date || day)}</strong>`;
    html += `<div class="heatmap-tooltip-meta">${learners.length} aprendiz(es) · ${imports.length} importación(es)</div>`;

    if (learners.length) {
      html += '<ul class="heatmap-tooltip-list">';
      learners.slice(0, 8).forEach((learner) => {
        const name = learner.name || "Sin nombre";
        const identification = learner.identification ? ` · ${learner.identification}` : "";
        const status = learner.certification_status || learner.status || "";
        html += `<li><strong>${escapeHtml(name)}</strong>${escapeHtml(identification)}${
          status ? ` <span class="heatmap-tooltip-status">${escapeHtml(status)}</span>` : ""
        }</li>`;
      });
      html += "</ul>";
      if (learners.length > 8) {
        html += `<div class="heatmap-tooltip-more">… y ${learners.length - 8} más</div>`;
      }
    }

    if (imports.length) {
      html += '<div class="heatmap-tooltip-section">Importaciones</div>';
      html += '<ul class="heatmap-tooltip-list">';
      imports.slice(0, 5).forEach((item) => {
        const name = item.file_name || "Importación";
        const added = item.new_records ?? 0;
        const updated = item.updated_records ?? 0;
        html += `<li>${escapeHtml(name)} <span class="heatmap-tooltip-status">+${escapeHtml(
          added
        )} / ~${escapeHtml(updated)}</span></li>`;
      });
      html += "</ul>";
      if (imports.length > 5) {
        html += `<div class="heatmap-tooltip-more">… y ${imports.length - 5} más</div>`;
      }
    }

    if (!learners.length && !imports.length) {
      html += "<div>Sin aprendices asociados en esta fecha.</div>";
    }
    tooltip.innerHTML = html;
  }

  /* ---------------- Certificados del consolidado por mes ---------------- */
  let activityData = null;
  let activityYear = 2026;
  let activityChart = null;
  let activityView = "certificados";
  let certificadosMesData = null;
  let certificadosMesChart = null;
  const ACTIVITY_VIEW_KEY = "indicadores-actividad-vista";

  function normalizeActivityView(value) {
    return "certificados";
  }

  function readStoredActivityView() {
    try {
      return normalizeActivityView(window.sessionStorage.getItem(ACTIVITY_VIEW_KEY));
    } catch (_) {
      return "heatmap";
    }
  }

  function monthShort(isoDate) {
    const dt = new Date(`${isoDate}T00:00:00Z`);
    if (Number.isNaN(dt.getTime())) return "";
    const name = dt
      .toLocaleString("es-CO", { month: "short", timeZone: "UTC" })
      .replace(".", "");
    return name.charAt(0).toUpperCase() + name.slice(1);
  }

  function setActivityView(view, { render = true } = {}) {
    activityView = normalizeActivityView(view);
    try {
      window.sessionStorage.setItem(ACTIVITY_VIEW_KEY, activityView);
    } catch (_) {
      /* sessionStorage puede estar bloqueado; la vista sigue funcionando. */
    }

    document.querySelectorAll(".activity-view-btn").forEach((btn) => {
      const on = btn.dataset.activityView === activityView;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
      btn.tabIndex = on ? 0 : -1;
    });

    const heatmapPanel = document.getElementById("activity-heatmap-panel");
    const chartPanel = document.getElementById("activity-chart-panel");
    const certificadosPanel = document.getElementById("activity-certificados-panel");
    if (heatmapPanel) heatmapPanel.hidden = activityView !== "heatmap";
    if (chartPanel) chartPanel.hidden = activityView !== "chart";
    if (certificadosPanel) certificadosPanel.hidden = activityView !== "certificados";

    if (activityView === "chart" && render && !activityChart) {
      renderActivityChart(activityData, activityYear);
    }
    if (activityView === "certificados" && render && !certificadosMesChart) {
      renderCertificadosMesChart(certificadosMesData);
    }
    if (activityView === "chart" && activityChart) {
      // Chart.js mide el canvas al crearlo; si el panel estaba oculto hay que
      // pedirle que recalcule al mostrarlo.
      setTimeout(() => {
        try {
          activityChart.resize();
        } catch (_) {}
      }, 40);
    }
    if (activityView === "certificados" && certificadosMesChart) {
      setTimeout(() => {
        try {
          certificadosMesChart.resize();
        } catch (_) {}
      }, 40);
    }
  }

  function setupActivityToggle() {
    const toggle = document.getElementById("activity-view-toggle");
    const buttons = [...document.querySelectorAll(".activity-view-btn")];
    if (!toggle || !buttons.length) return;

    buttons.forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        setActivityView(btn.dataset.activityView);
      });
    });

    toggle.addEventListener("keydown", (event) => {
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      let next = null;
      if (event.key === "ArrowRight") next = buttons[(index + 1) % buttons.length];
      else if (event.key === "ArrowLeft") next = buttons[(index - 1 + buttons.length) % buttons.length];
      else if (event.key === "Home") next = buttons[0];
      else if (event.key === "End") next = buttons[buttons.length - 1];
      if (!next) return;
      event.preventDefault();
      next.focus();
      setActivityView(next.dataset.activityView);
    });

    setActivityView(readStoredActivityView(), { render: false });
  }

  function updateActivitySummary(data, year) {
    const summary = document.getElementById("activity-chart-summary");
    if (!summary) return;
    const total = Number(data?.total_events) || 0;
    const days = Array.isArray(data?.days) ? data.days : [];
    const activeDays = days.filter((day) => Number(day.count) > 0).length;
    if (!total) {
      summary.textContent = `Sin eventos de actividad en ${year}.`;
      return;
    }
    summary.textContent =
      `${formatNum(total)} eventos en ${formatNum(activeDays)} días con actividad · ` +
      `${formatNum(data.total_status_changes)} cambios de estado · ` +
      `${formatNum(data.total_imports)} importaciones. ` +
      "Serie semanal (suma de eventos por día); haz clic en una barra para ver el día con más actividad de esa semana.";
  }

  function formatDayShort(isoDate) {
    const dt = new Date(`${isoDate}T00:00:00Z`);
    if (Number.isNaN(dt.getTime())) return isoDate;
    return dt.toLocaleDateString("es-CO", {
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    });
  }

  // Agrupa los dias en semanas (lunes a domingo). El heatmap conserva el detalle
  // diario; el grafico suma esos mismos dias para que 365 barras de 1px no se
  // conviertan en una linea ilegible.
  function buildActivityWeeks(days) {
    const weeks = [];
    let current = null;
    days.forEach((day) => {
      const dt = new Date(`${day.date}T00:00:00Z`);
      if (Number.isNaN(dt.getTime())) return;
      const dow = (dt.getUTCDay() + 6) % 7; // lunes = 0
      const monday = new Date(dt);
      monday.setUTCDate(dt.getUTCDate() - dow);
      const key = monday.toISOString().slice(0, 10);
      if (!current || current.key !== key) {
        current = {
          key,
          start: key,
          end: day.date,
          count: 0,
          status_changes: 0,
          imports: 0,
          import_records: 0,
          best: null,
        };
        weeks.push(current);
      }
      current.end = day.date;
      const count = Number(day.count) || 0;
      const sources = day.sources || {};
      current.count += count;
      current.status_changes += Number(sources.status_changes) || 0;
      current.imports += Number(sources.imports) || 0;
      current.import_records += Number(sources.import_records) || 0;
      if (!current.best || count > current.best.count) {
        current.best = { date: day.date, count };
      }
    });
    return weeks;
  }

  function renderActivityChart(data, year) {
    const canvas = document.getElementById("indicadores-activity-chart");
    const empty = document.getElementById("activity-chart-empty");
    if (!canvas || !empty) return;

    if (activityChart) {
      activityChart.destroy();
      activityChart = null;
    }

    if (typeof Chart === "undefined") {
      canvas.hidden = true;
      empty.hidden = false;
      empty.textContent = "No se pudo cargar la librería de gráficos (Chart.js).";
      return;
    }

    const days = Array.isArray(data?.days) ? data.days : [];
    const total = Number(data?.total_events) || 0;
    if (!days.length || total <= 0) {
      canvas.hidden = true;
      empty.hidden = false;
      empty.textContent = `No hay actividad registrada en ${year}. Cambia el año o importa información para ver eventos.`;
      canvas.setAttribute("aria-label", `Sin actividad registrada en ${year}`);
      return;
    }

    canvas.hidden = false;
    empty.hidden = true;

    const weeks = buildActivityWeeks(days);
    const activeDays = days.filter((day) => Number(day.count) > 0).length;
    canvas.setAttribute(
      "aria-label",
      `Actividad de certificación ${year}: ${total} eventos en ${activeDays} días con actividad (serie semanal)`
    );

    activityChart = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: weeks.map((week) => week.start),
        datasets: [
          {
            label: "Eventos de actividad",
            data: weeks.map((week) => week.count),
            backgroundColor: "rgba(15, 118, 110, 0.6)",
            hoverBackgroundColor: "#0f766e",
            borderWidth: 0,
            borderRadius: 3,
            maxBarThickness: 26,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              autoSkip: false,
              maxRotation: 0,
              callback(value, index) {
                const week = weeks[index];
                if (!week) return "";
                const dt = new Date(`${week.start}T00:00:00Z`);
                if (Number.isNaN(dt.getTime())) return "";
                const month = dt.getUTCMonth();
                const previous = weeks[index - 1];
                const previousMonth = previous
                  ? new Date(`${previous.start}T00:00:00Z`).getUTCMonth()
                  : null;
                // Sin semana previa (la que empieza en diciembre del año
                // anterior) no se rotula; luego solo al cambiar de mes.
                if (previousMonth === null) return "";
                if (month === previousMonth) return "";
                // En pantallas estrechas se rotula mes por medio para que las
                // etiquetas no se amontonen.
                if (canvas.clientWidth < 560 && month % 2 !== 0) return "";
                return monthShort(week.start);
              },
            },
          },
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            title: { display: true, text: "Eventos de actividad" },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => {
                const week = weeks[items[0].dataIndex];
                if (!week) return "";
                return `Semana del ${formatDayShort(week.start)} al ${formatDayShort(week.end)}`;
              },
              label: (ctx) => `${ctx.parsed.y} evento(s) en la semana`,
              afterLabel: (ctx) => {
                const week = weeks[ctx.dataIndex] || {};
                const lines = [];
                if (week.status_changes) lines.push(`Cambios de estado: ${week.status_changes}`);
                if (week.imports) lines.push(`Importaciones: ${week.imports}`);
                if (week.import_records) lines.push(`Registros importados: ${week.import_records}`);
                if (week.best && week.best.count > 0) {
                  lines.push(`Día con más actividad: ${formatDayShort(week.best.date)} (${week.best.count})`);
                }
                return lines;
              },
            },
          },
        },
        onClick: (event, elements) => {
          if (!elements.length) return;
          const week = weeks[elements[0].index];
          if (!week || !week.best || week.best.count <= 0) return;
          const native = event?.native || event;
          showDayDetails(week.best.date, native, canvas);
        },
      },
    });
  }

  function updateCertificadosMesSummary(data) {
    const summary = document.getElementById("certificados-mes-summary");
    const note = document.getElementById("certificados-mes-note");
    if (!summary) return;
    if (!data) {
      summary.textContent =
        "Consolidado ACTAS 2026 · hoja CERTIFICADOS · no disponible.";
      if (note) note.hidden = true;
      return;
    }
    const total = Number(data.total) || 0;
    const lote = data.lote_id != null ? ` · lote #${data.lote_id}` : "";
    summary.textContent =
      `Consolidado ACTAS 2026 · hoja CERTIFICADOS · ${total} persona(s) ` +
      `certificada(s) en ENE–SEP 2026${lote}. No es padrón local ni fecha de importación.`;
    if (note) {
      const partes = [];
      if (Number(data.fuera_de_periodo) > 0) {
        partes.push(`${data.fuera_de_periodo} certificado(s) fuera del período no se grafican.`);
      }
      if (Number(data.sin_mes) > 0) {
        partes.push(`${data.sin_mes} certificado(s) sin mes de certificación.`);
      }
      if (Number(data.conflictos_sin_resolver) > 0) {
        partes.push(
          `${data.conflictos_sin_resolver} conflicto(s) sin resolver se excluyeron del gráfico.`
        );
      }
      note.textContent = partes.join(" ");
      note.hidden = !partes.length;
    }
  }

  function renderCertificadosMesChart(data) {
    const canvas = document.getElementById("indicadores-certificados-mes-chart");
    const empty = document.getElementById("certificados-mes-empty");
    if (!canvas || !empty) return;

    updateCertificadosMesSummary(data);

    if (certificadosMesChart) {
      certificadosMesChart.destroy();
      certificadosMesChart = null;
    }

    if (typeof Chart === "undefined") {
      canvas.hidden = true;
      empty.hidden = false;
      empty.textContent = "No se pudo cargar la librería de gráficos (Chart.js).";
      return;
    }

    const meses = Array.isArray(data?.meses) ? data.meses : [];
    const total = Number(data?.total) || 0;
    if (!meses.length || total <= 0) {
      canvas.hidden = true;
      empty.hidden = false;
      empty.textContent =
        "No hay certificados del consolidado en ENE–SEP 2026. Cargue ACTAS 2026 o revise la hoja CERTIFICADOS.";
      canvas.setAttribute("aria-label", "Sin certificados del consolidado en el período");
      return;
    }

    canvas.hidden = false;
    empty.hidden = true;
    canvas.setAttribute(
      "aria-label",
      `Certificados del consolidado por mes: ${total} en ENE–SEP 2026`
    );

    certificadosMesChart = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: meses.map((mes) => mes.etiqueta),
        datasets: [
          {
            label: "Personas certificadas del consolidado",
            data: meses.map((mes) => Number(mes.certificados) || 0),
            backgroundColor: "rgba(15, 118, 110, 0.7)",
            hoverBackgroundColor: "#0f766e",
            borderWidth: 0,
            borderRadius: 4,
            maxBarThickness: 44,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: { precision: 0 },
            title: { display: true, text: "Personas certificadas" },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) =>
                `${ctx.parsed.y} persona(s) certificada(s) en ${meses[ctx.dataIndex]?.etiqueta || ""}`,
            },
          },
        },
      },
    });
  }

  async function loadActivity(year) {
    activityYear = Number(year) || 2026;
    const certificadosMes = await safeJson("/api/indicadores/certificados-por-mes");
    if (certificadosMesChart) {
      certificadosMesChart.destroy();
      certificadosMesChart = null;
    }
    updateCertificadosMesSummary(certificadosMes);
    certificadosMesData = certificadosMes;
    setActivityView("certificados", { render: true });
    scheduleChartPadding();
  }

  function renderHeatmap(data, year) {
    const host = document.getElementById("indicadores-heatmap");
    const monthsEl = document.getElementById("heatmap-months");
    const empty = document.getElementById("heatmap-empty");
    if (!host) return;
    host.replaceChildren();
    if (monthsEl) monthsEl.replaceChildren();
    hideTooltip();

    if (!data || !Array.isArray(data.days) || !data.days.length) {
      if (empty) {
        empty.hidden = false;
        empty.textContent =
          "No hay actividad registrada o el endpoint /api/activity/heatmap no está disponible.";
      }
      return;
    }

    if (empty) {
      empty.hidden = Number(data.total_events) > 0;
      if (!empty.hidden) {
        empty.textContent = "No hay actividad registrada en el período seleccionado.";
      }
    }

    const days = data.days;
    const first = new Date(`${days[0].date}T00:00:00Z`);
    if (Number.isNaN(first.getTime())) return;
    const pad = (first.getUTCDay() + 6) % 7; // lunes = 0
    const cells = [];
    for (let i = 0; i < pad; i += 1) cells.push({ pad: true });
    days.forEach((day) => cells.push(day));

    const totalCols = Math.ceil(cells.length / 7);
    if (monthsEl) {
      monthsEl.style.gridTemplateColumns = `repeat(${totalCols}, 11px)`;
      monthsEl.style.gap = "3px";
      const labels = new Array(totalCols).fill("");
      cells.forEach((cell, index) => {
        if (cell.pad || !cell.date) return;
        const dt = new Date(`${cell.date}T00:00:00Z`);
        if (dt.getUTCDate() !== 1) return;
        const col = Math.floor(index / 7);
        const name = dt
          .toLocaleString("es-CO", { month: "short", timeZone: "UTC" })
          .replace(".", "");
        if (!labels[col]) {
          labels[col] = name.charAt(0).toUpperCase() + name.slice(1);
        }
      });
      labels.forEach((label) => {
        const span = document.createElement("span");
        span.textContent = label;
        monthsEl.appendChild(span);
      });
    }

    cells.forEach((cellData) => {
      if (cellData.pad) {
        const spacer = document.createElement("span");
        spacer.className = "heatmap-cell level-0";
        spacer.style.visibility = "hidden";
        host.appendChild(spacer);
        return;
      }
      const count = Number(cellData.count) || 0;
      const hasActivity = count > 0;
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = `heatmap-cell level-${Number(cellData.level) || 0}${
        hasActivity ? "" : " is-empty"
      }`;
      cell.dataset.date = cellData.date;
      cell.dataset.count = String(count);
      cell.title = `${cellData.date}: ${count} evento(s)`;
      cell.setAttribute("aria-label", `${cellData.date}, ${count} eventos de actividad`);
      cell.addEventListener("mouseenter", (evt) => {
        if (hasActivity) showDayDetails(cellData.date, evt, cell);
        else showEmptyDay(cellData.date, evt, cell);
      });
      cell.addEventListener("mousemove", (evt) => positionTooltip(evt, cell));
      cell.addEventListener("mouseleave", hideTooltip);
      cell.addEventListener("focus", (evt) => {
        if (hasActivity) showDayDetails(cellData.date, evt, cell);
        else showEmptyDay(cellData.date, evt, cell);
      });
      cell.addEventListener("blur", hideTooltip);
      cell.addEventListener("click", (evt) => {
        if (hasActivity) showDayDetails(cellData.date, evt, cell);
        else showEmptyDay(cellData.date, evt, cell);
      });
      host.appendChild(cell);
    });

    host.setAttribute(
      "aria-label",
      `Mapa de actividad ${year}: ${Number(data.total_events) || 0} eventos`
    );
  }

  /* ---------------- Pestañas pill de Indicadores ---------------- */
  function setupPillTabs() {
    const tabList = document.getElementById("indicadores-pill-tabs");
    const tabs = [...document.querySelectorAll(".pill-tab[data-pill]")];
    const panels = [...document.querySelectorAll(".pill-panel[data-pill]")];
    if (!tabs.length) return;

    function activate(name) {
      const target = ["resumen", "causas", "actas"].includes(name) ? name : "resumen";
      tabs.forEach((tab) => {
        const on = tab.dataset.pill === target;
        tab.classList.toggle("is-active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
        tab.tabIndex = on ? 0 : -1;
      });
      panels.forEach((panel) => {
        const on = panel.dataset.pill === target;
        panel.hidden = !on;
        panel.classList.toggle("is-active", on);
      });
      setTimeout(() => {
        try {
          window.dispatchEvent(new Event("resize"));
          if (target === "causas" && window.graficoCausas) window.graficoCausas.resize();
          if (target === "resumen" && window.graficoAvance) window.graficoAvance.resize();
          scheduleChartPadding();
        } catch (_) {}
      }, 40);
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", (e) => {
        e.preventDefault();
        activate(tab.dataset.pill);
      });
    });

    tabList?.addEventListener("keydown", (e) => {
      const index = tabs.indexOf(document.activeElement);
      if (index < 0) return;
      let next = null;
      if (e.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      else if (e.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (e.key === "Home") next = tabs[0];
      else if (e.key === "End") next = tabs[tabs.length - 1];
      if (!next) return;
      e.preventDefault();
      next.focus();
      activate(next.dataset.pill);
    });

    // app.js conserva su función global; la redirigimos a las pestañas nuevas.
    window.activarTabIndicadores = function (nombre) {
      activate(nombre);
    };

    activate("resumen");
  }

  document.getElementById("heatmap-year")?.addEventListener("change", (e) => {
    loadActivity(Number(e.target.value || 2026));
  });

  document.getElementById("refresh-indicadores")?.addEventListener("click", () => {
    loadIndicadoresExtras();
  });

  /* ---------------- Integración con showView de app.js ---------------- */
  function replaceHashSafely(hash) {
    // Browser Guard y otros bloqueadores pueden interceptar replaceState con
    // "Breaking Browser Locker Behavior detected". La navegación interna no
    // debe romperse por esa API cosmética.
    try {
      history.replaceState(null, "", hash);
    } catch (error) {
      // La vista ya cambió; solo se omite la actualización de la URL.
    }
  }

  const originalShowView = window.showView;
  if (typeof originalShowView === "function") {
    window.showView = function (viewName, updateHash) {
      if (viewName === "historial") {
        originalShowView("carga", false);
        activateSidebar("historial");
        if (updateHash !== false) replaceHashSafely("#historial");
        setTimeout(() => {
          document.getElementById("historial")?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        }, 60);
        return;
      }
      if (viewName === "dashboard") {
        originalShowView("indicadores", updateHash);
        activateSidebar("indicadores");
        loadIndicadoresExtras();
        return;
      }
      const target = [
        "aprendices",
        "actas",
        "indicadores",
        "informe-gestion",
      ].includes(viewName)
        ? viewName
        : "carga";
      originalShowView(target, updateHash);
      activateSidebar(target);
      if (target === "indicadores") loadIndicadoresExtras();
    };
  }

  /* ---------------- Boot ---------------- */
  function boot() {
    observeFeedback();
    observeImportCompletion();
    setupPillTabs();
    setupActivityToggle();

    const hash = (location.hash || "").replace("#", "");
    if (hash === "dashboard") {
      window.showView?.("indicadores", false);
    } else if (
      ["aprendices", "actas", "indicadores", "historial", "informe-gestion"].includes(
        hash,
      )
    ) {
      window.showView?.(hash, false);
    } else {
      activateSidebar("carga");
    }

    if (confirmationPanel && !confirmationPanel.hidden) openImportModal();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.SenaUI = {
    showToast,
    openImportModal,
    closeImportModal,
    loadIndicadoresExtras,
    loadActivity,
    loadHeatmap: loadActivity,
    setProgress,
    activateSidebar,
    fixChartPadding,
    scheduleChartPadding,
  };
})();
