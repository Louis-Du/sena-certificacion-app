/**
 * SENA Certificación — UI v2 enhancements
 * - Toasts
 * - Modal de revisión / conflictos de importación
 * - Barra de carga al validar
 * - KPIs + heatmap real en Indicadores (hover con aprendices)
 * - Sidebar rail activo
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
      const ok = /correctamente|guardad|completad|éxito|exito|procesad/i.test(text);
      showToast(text, err ? "error" : ok ? "success" : "warning");
    });
    obs.observe(feedbackEl, {
      childList: true,
      characterData: true,
      subtree: true,
      attributes: true,
    });
  }

  /* ---------------- Modal importación ---------------- */
  const modal = document.getElementById("import-modal");
  const modalBody = document.getElementById("import-modal-body");
  const modalConfirm = document.getElementById("modal-confirm-button");
  const modalCancel = document.getElementById("modal-cancel-button");
  const confirmationPanel = document.getElementById("confirmation-panel");
  const confirmButton = document.getElementById("confirm-button");
  const cancelButton = document.getElementById("cancel-button");

  function openImportModal() {
    if (!modal || !confirmationPanel || !modalBody) return;
    // Mover el panel al modal para que sea el foco visual
    if (confirmationPanel.parentElement !== modalBody) {
      modalBody.appendChild(confirmationPanel);
    }
    confirmationPanel.hidden = false;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    if (modalConfirm && confirmButton) {
      modalConfirm.hidden = confirmButton.hidden;
      modalConfirm.disabled = confirmButton.disabled;
    }
    // foco accesible
    (modalCancel || modalConfirm)?.focus?.();
  }

  function closeImportModal() {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    // Devolver panel al flujo original si existe contenedor
    const host = document.querySelector("#carga-view .main-column") || document.getElementById("carga-view");
    if (confirmationPanel && host && confirmationPanel.parentElement === modalBody) {
      // insert before actions if possible
      const actions = host.querySelector(".actions");
      if (actions) host.insertBefore(confirmationPanel, actions);
      else host.appendChild(confirmationPanel);
    }
    if (confirmationPanel) confirmationPanel.hidden = true;
  }

  function syncModalConfirmState() {
    if (!modalConfirm || !confirmButton) return;
    modalConfirm.hidden = confirmButton.hidden;
    modalConfirm.disabled = confirmButton.disabled;
  }

  if (confirmationPanel) {
    const panelObs = new MutationObserver(() => {
      if (!confirmationPanel.hidden) openImportModal();
      else if (modal?.classList.contains("is-open") && confirmationPanel.hidden) {
        // solo cerrar si app.js lo ocultó tras confirmar
        closeImportModal();
      }
      syncModalConfirmState();
    });
    panelObs.observe(confirmationPanel, { attributes: true, attributeFilter: ["hidden"] });
  }

  if (confirmButton) {
    const btnObs = new MutationObserver(syncModalConfirmState);
    btnObs.observe(confirmButton, { attributes: true, attributeFilter: ["hidden", "disabled"] });
  }

  modal?.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", () => {
      cancelButton?.click();
      closeImportModal();
    });
  });

  modalCancel?.addEventListener("click", () => {
    cancelButton?.click();
    closeImportModal();
  });

  modalConfirm?.addEventListener("click", () => {
    if (confirmButton && !confirmButton.disabled) confirmButton.click();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal?.classList.contains("is-open")) {
      cancelButton?.click();
      closeImportModal();
    }
  });

  /* ---------------- Loading bar en validación ---------------- */
  const progress = document.getElementById("upload-progress");
  const progressLabel = document.getElementById("upload-progress-label");
  const validateButton = document.getElementById("validate-button");

  function setProgress(active, label) {
    if (!progress) return;
    progress.classList.toggle("is-active", !!active);
    if (progressLabel && label) progressLabel.textContent = label;
  }

  if (validateButton) {
    validateButton.addEventListener(
      "click",
      () => {
        setProgress(true, "Validando y preparando vista previa…");
      },
      true
    );
  }

  // Desactivar cuando aparece confirmación o feedback de error
  const stopProgressObs = new MutationObserver(() => {
    if (confirmationPanel && !confirmationPanel.hidden) setProgress(false);
  });
  if (confirmationPanel) {
    stopProgressObs.observe(confirmationPanel, { attributes: true, attributeFilter: ["hidden"] });
  }

  const originalFetch = window.fetch;
  window.fetch = function patchedFetch(input, init) {
    const url = String(input);
    const isValidate = url.includes("/api/files/validate");
    const isConfirm = url.includes("/api/imports/") && url.includes("/confirm");
    if (isValidate) setProgress(true, "Subiendo y validando archivo…");
    if (isConfirm) setProgress(true, "Confirmando importación…");
    return originalFetch.apply(this, arguments).finally(() => {
      if (isValidate || isConfirm) {
        // pequeña espera para que el usuario perciba cierre
        setTimeout(() => setProgress(false), 250);
      }
    });
  };

  /* ---------------- Sidebar active state ---------------- */
  function activateSidebar(view) {
    document.querySelectorAll(".sidebar-link[data-view]").forEach((link) => {
      const match =
        link.dataset.view === view ||
        (view === "carga" && link.getAttribute("href") === "#historial" && location.hash === "#historial");
      link.classList.toggle("active", link.dataset.view === view);
    });
  }

  document.querySelectorAll(".sidebar-link[data-view]").forEach((link) => {
    link.addEventListener("click", () => activateSidebar(link.dataset.view));
  });

  /* ---------------- Indicadores: KPIs + heatmap real ---------------- */
  function formatNum(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return Number(n).toLocaleString("es-CO");
  }

  async function safeJson(url) {
    try {
      const res = await fetch(url);
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

  async function loadIndicadoresExtras() {
    const [indicadores, acts, learners] = await Promise.all([
      safeJson("/api/indicadores"),
      safeJson("/api/acts"),
      safeJson("/api/learners?page=1&page_size=1"),
    ]);

    if (indicadores) {
      const cert =
        indicadores.certificados ??
        indicadores.total_certificados ??
        indicadores.resumen?.certificados ??
        indicadores.kpis?.certificados;
      const por =
        indicadores.total_pendientes ??
        indicadores.por_certificar ??
        indicadores.total_por_certificar ??
        indicadores.resumen?.por_certificar ??
        indicadores.kpis?.por_certificar;
      setText("ind-metric-certificados", formatNum(cert));
      setText("ind-metric-por-certificar", formatNum(por));
    }
    if (acts) {
      const total = acts.total ?? acts.count ?? (Array.isArray(acts.items) ? acts.items.length : null);
      setText("ind-metric-actas", formatNum(total));
    }
    if (learners) {
      setText("ind-metric-learners", formatNum(learners.total ?? learners.count ?? learners.total_count));
    }

    const yearSel = document.getElementById("heatmap-year");
    const year = Number(yearSel?.value || 2026);
    await loadHeatmap(year);
  }

  const tooltip = document.getElementById("heatmap-tooltip") || createTooltip();

  function createTooltip() {
    const el = document.createElement("div");
    el.id = "heatmap-tooltip";
    el.className = "heatmap-tooltip";
    el.setAttribute("role", "tooltip");
    document.body.appendChild(el);
    return el;
  }

  function hideTooltip() {
    tooltip.classList.remove("is-visible");
    tooltip.innerHTML = "";
  }

  function positionTooltip(evt) {
    const pad = 14;
    const x = Math.min(window.innerWidth - 340, evt.clientX + pad);
    const y = Math.min(window.innerHeight - 120, evt.clientY + pad);
    tooltip.style.left = `${Math.max(8, x)}px`;
    tooltip.style.top = `${Math.max(8, y)}px`;
  }

  async function showDayDetails(day, evt) {
    positionTooltip(evt);
    tooltip.innerHTML = `<strong>${day}</strong><div>Cargando aprendices…</div>`;
    tooltip.classList.add("is-visible");

    const data = await safeJson(`/api/activity/day/${day}`);
    if (!data) {
      tooltip.innerHTML = `<strong>${day}</strong><div>Sin detalle disponible (¿endpoint activo?).</div>`;
      return;
    }

    const learners = data.learners || [];
    const imports = data.imports || [];
    let html = `<strong>${day}</strong>`;
    html += `<div style="margin-bottom:6px;opacity:.85">${learners.length} aprendiz(es) · ${imports.length} importación(es)</div>`;
    if (learners.length) {
      html += "<ul>";
      learners.slice(0, 8).forEach((l) => {
        const name = l.name || "Sin nombre";
        const id = l.identification || "";
        const st = l.certification_status || l.status || "";
        html += `<li>${name}${id ? " · " + id : ""}${st ? " · " + st : ""}</li>`;
      });
      html += "</ul>";
      if (learners.length > 8) html += `<div>… y ${learners.length - 8} más</div>`;
    } else if (imports.length) {
      html += "<ul>";
      imports.forEach((i) => {
        html += `<li>${i.file_name || "Importación"} (+${i.new_records || 0} / ~${i.updated_records || 0})</li>`;
      });
      html += "</ul>";
    } else {
      html += "<div>Sin aprendices asociados en esta fecha.</div>";
    }
    tooltip.innerHTML = html;
  }

  async function loadHeatmap(year) {
    const host = document.getElementById("indicadores-heatmap");
    const empty = document.getElementById("heatmap-empty");
    if (!host) return;
    host.replaceChildren();
    hideTooltip();

    const data = await safeJson(`/api/activity/heatmap?year=${year}`);
    if (!data || !Array.isArray(data.days) || !data.days.length) {
      if (empty) {
        empty.hidden = false;
        empty.textContent =
          "No hay actividad registrada o el endpoint /api/activity/heatmap no está disponible.";
      }
      // Fallback visual mínimo
      return;
    }
    if (empty) empty.hidden = data.total_events > 0 ? true : false;

    // Organizar en columnas semanales (GitHub-style): filas = días semana
    // Empezar alineando el primer día al weekday
    const days = data.days;
    const first = new Date(days[0].date + "T00:00:00Z");
    const pad = (first.getUTCDay() + 6) % 7; // lunes=0
    for (let i = 0; i < pad; i++) {
      const spacer = document.createElement("span");
      spacer.className = "heatmap-cell level-0";
      spacer.style.visibility = "hidden";
      host.appendChild(spacer);
    }

    days.forEach((d) => {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = `heatmap-cell level-${d.level || 0}`;
      cell.title = `${d.date}: ${d.count} evento(s)`;
      cell.setAttribute("aria-label", `${d.date}, ${d.count} eventos de actividad`);
      cell.dataset.date = d.date;
      cell.dataset.count = String(d.count || 0);

      cell.addEventListener("mouseenter", (evt) => {
        if (Number(d.count) > 0) showDayDetails(d.date, evt);
        else {
          positionTooltip(evt);
          tooltip.innerHTML = `<strong>${d.date}</strong><div>Sin actividad</div>`;
          tooltip.classList.add("is-visible");
        }
      });
      cell.addEventListener("mousemove", positionTooltip);
      cell.addEventListener("mouseleave", hideTooltip);
      cell.addEventListener("focus", (evt) => {
        if (Number(d.count) > 0) showDayDetails(d.date, evt);
      });
      cell.addEventListener("blur", hideTooltip);
      cell.addEventListener("click", (evt) => showDayDetails(d.date, evt));

      host.appendChild(cell);
    });
  }

  document.getElementById("heatmap-year")?.addEventListener("change", (e) => {
    loadHeatmap(Number(e.target.value || 2026));
  });

  // Hook into view changes
  const originalShowView = window.showView;
  if (typeof originalShowView === "function") {
    window.showView = function (viewName, updateHash) {
      originalShowView(viewName, updateHash);
      activateSidebar(viewName);
      if (viewName === "indicadores") loadIndicadoresExtras();
      if (viewName === "dashboard") {
        // dashboard fusionado → redirigir
        originalShowView("indicadores", true);
        activateSidebar("indicadores");
        loadIndicadoresExtras();
      }
    };
  }

  // Also when user hits indicadores link
  document.querySelectorAll('[data-view="indicadores"]').forEach((link) => {
    link.addEventListener("click", () => setTimeout(loadIndicadoresExtras, 50));
  });

  // Boot
  function boot() {
    observeFeedback();
    const hash = (location.hash || "").replace("#", "");
    if (hash === "indicadores" || hash === "dashboard") {
      setTimeout(loadIndicadoresExtras, 80);
    }
    // si app.js ya pintó confirmación
    if (confirmationPanel && !confirmationPanel.hidden) openImportModal();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.SenaUI = {
    showToast,
    openImportModal,
    closeImportModal,
    loadIndicadoresExtras,
    loadHeatmap,
    setProgress,
  };
})();
