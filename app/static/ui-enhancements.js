/**
 * SENA Certificación - UI Enhancements & Toast System
 * Proporciona notificaciones flotantes (toasts) y observa los estados de feedback
 * para reducir el ruido visual en pantalla sin interferir con la lógica de app.js.
 */

(function () {
  "use strict";

  const ICONS = {
    success: "✓",
    error: "✕",
    warning: "⚠",
    info: "ℹ",
  };

  const TITLES = {
    success: "Éxito",
    error: "Error",
    warning: "Atención",
    info: "Información",
  };

  function getContainer() {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      container.setAttribute("aria-live", "polite");
      container.setAttribute("aria-atomic", "true");
      document.body.appendChild(container);
    }
    return container;
  }

  function normalizeType(type) {
    if (!type) return "info";
    const t = String(type).toLowerCase().trim();
    if (t === "ok" || t === "success" || t === "exito") return "success";
    if (t === "error" || t === "danger" || t === "fail") return "error";
    if (t === "warning" || t === "warn" || t === "alerta") return "warning";
    return "info";
  }

  /**
   * Muestra un toast flotante en la interfaz.
   * @param {string} message - Texto del mensaje a mostrar.
   * @param {string} [type='info'] - 'success' | 'error' | 'warning' | 'info'.
   * @param {Object} [options] - Opciones adicionales ({ title, duration }).
   * @returns {Object} { element, dismiss }
   */
  function showToast(message, type = "info", options = {}) {
    if (!message || typeof message !== "string") return null;

    const container = getContainer();
    const finalType = normalizeType(type);
    const duration = typeof options.duration === "number" ? options.duration : 4500;
    const titleText = options.title !== undefined ? options.title : TITLES[finalType];

    const toast = document.createElement("div");
    toast.className = `toast toast-${finalType}`;
    toast.setAttribute("role", finalType === "error" ? "alert" : "status");

    // Icon
    const iconEl = document.createElement("span");
    iconEl.className = "toast-icon";
    iconEl.setAttribute("aria-hidden", "true");
    iconEl.textContent = ICONS[finalType] || ICONS.info;

    // Body
    const bodyEl = document.createElement("div");
    bodyEl.className = "toast-body";

    if (titleText) {
      const titleEl = document.createElement("div");
      titleEl.className = "toast-title";
      titleEl.textContent = titleText;
      bodyEl.appendChild(titleEl);
    }

    const messageEl = document.createElement("div");
    messageEl.className = "toast-message";
    messageEl.textContent = message;
    bodyEl.appendChild(messageEl);

    // Close button
    const closeBtn = document.createElement("button");
    closeBtn.className = "toast-close";
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Cerrar notificación");
    closeBtn.textContent = "×";

    toast.appendChild(iconEl);
    toast.appendChild(bodyEl);
    toast.appendChild(closeBtn);

    let dismissed = false;
    let timer = null;

    function dismiss() {
      if (dismissed) return;
      dismissed = true;
      if (timer) clearTimeout(timer);
      toast.classList.add("is-leaving");
      toast.addEventListener(
        "animationend",
        () => {
          if (toast.parentElement) toast.parentElement.removeChild(toast);
        },
        { once: true }
      );
    }

    closeBtn.addEventListener("click", dismiss);

    if (duration > 0) {
      timer = setTimeout(dismiss, duration);
    }

    container.appendChild(toast);
    return { element: toast, dismiss };
  }

  // Exponer globalmente para uso directo en consola o cualquier módulo
  window.showToast = showToast;

  /**
   * Observa el elemento #feedback de la vista de carga para reflejar
   * los mensajes importantes como toasts.
   */
  function setupFeedbackObserver() {
    const feedbackEl = document.getElementById("feedback");
    if (!feedbackEl) return;

    let lastText = "";
    let lastTime = 0;

    const observer = new MutationObserver(() => {
      const text = (feedbackEl.textContent || "").trim();
      const isVisible = feedbackEl.classList.contains("visible");
      const now = Date.now();

      // Ignora mensajes vacíos, estados no visibles o repeticiones inmediatas (< 500ms)
      if (!isVisible || !text) {
        if (!isVisible) lastText = "";
        return;
      }

      if (text === lastText && now - lastTime < 1000) {
        return;
      }

      lastText = text;
      lastTime = now;

      const isError = feedbackEl.classList.contains("error");
      const lower = text.toLowerCase();

      let type = "info";
      if (isError) {
        type = "error";
      } else if (
        lower.includes("procesad") ||
        lower.includes("completad") ||
        lower.includes("éxito") ||
        lower.includes("exito") ||
        lower.includes("correctamente") ||
        lower.includes("guardad")
      ) {
        type = "success";
      } else if (lower.includes("revisa") || lower.includes("advertencia") || lower.includes("atención")) {
        type = "warning";
      }

      showToast(text, type);
    });

    observer.observe(feedbackEl, {
      childList: true,
      characterData: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  /**
   * Observa feedbacks secundarios (actas, aprendices) para también reflejarlos como toasts.
   */
  function setupSecondaryFeedbackObservers() {
    const targets = [
      { id: "act-form-feedback", successMatch: "guardada" },
      { id: "act-detail-feedback", successMatch: "correctamente" },
    ];

    targets.forEach(({ id, successMatch }) => {
      const el = document.getElementById(id);
      if (!el) return;

      let lastMsg = "";
      const observer = new MutationObserver(() => {
        const text = (el.textContent || "").trim();
        if (!text || text === lastMsg) return;
        lastMsg = text;

        const isSuccess = text.toLowerCase().includes(successMatch);
        const type = isSuccess ? "success" : "error";
        showToast(text, type);
      });

      observer.observe(el, { childList: true, characterData: true, subtree: true });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      setupFeedbackObserver();
      setupSecondaryFeedbackObservers();
    });
  } else {
    setupFeedbackObserver();
    setupSecondaryFeedbackObservers();
  }
})();
