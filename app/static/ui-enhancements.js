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
  const reportFeedback = document.getElementById("report-modal-feedback");
  const reportFormat = document.getElementById("report-format");
  let selectedReportType = "general";

  function updateReportLink() {
    if (!reportGenerate) return;
    const csvOption = reportFormat?.querySelector('option[value="csv"]');
    if (csvOption) {
      csvOption.disabled = selectedReportType === "consolidado";
      if (csvOption.disabled && reportFormat.value === "csv") reportFormat.value = "xlsx";
    }
    const format = reportFormat?.value || "xlsx";
    reportGenerate.href = `/api/informes/export?type=${encodeURIComponent(selectedReportType)}&format=${format}`;
    reportGenerate.download = `informe_${selectedReportType}.${format}`;
  }

  function closeReportModal() {
    if (!reportModal) return;
    reportModal.classList.remove("is-open");
    reportModal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function openReportModal() {
    if (!reportModal) return;
    reportModal.classList.add("is-open");
    reportModal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    reportFeedback.textContent = "";
    reportGenerate?.focus();
  }

  reportOpen?.addEventListener("click", openReportModal);
  reportClose?.addEventListener("click", closeReportModal);
  reportCancel?.addEventListener("click", closeReportModal);
  reportModal?.querySelectorAll("[data-close-report-modal]").forEach((element) => {
    element.addEventListener("click", closeReportModal);
  });
  reportModal?.querySelectorAll(".report-option").forEach((option) => {
    option.addEventListener("click", () => {
      if (option.classList.contains("is-disabled")) {
        reportFeedback.textContent = "Este tipo de informe todavía no está disponible.";
        return;
      }
      reportModal.querySelectorAll(".report-option").forEach((item) => {
        const selected = item === option;
        item.classList.toggle("is-selected", selected);
        item.setAttribute("aria-checked", String(selected));
      });
      selectedReportType = option.dataset.reportType || "general";
      updateReportLink();
    });
  });
  reportFormat?.addEventListener("change", updateReportLink);
  updateReportLink();
  reportGenerate?.addEventListener("click", () => {
    const format = reportFormat?.value || "xlsx";
    showToast(`Preparando informe ${selectedReportType} en formato ${format.toUpperCase()}.`, "info");
    window.setTimeout(closeReportModal, 100);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && reportModal?.classList.contains("is-open")) {
      closeReportModal();
    }
  });

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
  const originalShowView = window.showView;
  if (typeof originalShowView === "function") {
    window.showView = function (viewName, updateHash) {
      if (viewName === "historial") {
        originalShowView("carga", false);
        activateSidebar("historial");
        if (updateHash !== false) history.replaceState(null, "", "#historial");
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
      const target = ["aprendices", "actas", "indicadores"].includes(viewName)
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
    } else if (["aprendices", "actas", "indicadores", "historial"].includes(hash)) {
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
