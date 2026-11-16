/**
 * SENA Certificación — actualizaciones automáticas.
 *
 * Consulta `/api/updates/check` al arrancar y cuando la ventana recupera el
 * foco. Si hay una versión nueva muestra un toast nativo (pywebview) y un modal
 * con las novedades, desde el cual se puede descargar e iniciar el instalador.
 */
(function () {
  "use strict";

  const POLL_INTERVAL_MS = 6 * 60 * 60 * 1000;
  const SHOWN_PREFIX = "sena.update.shown.";
  const NOTIFIED_PREFIX = "sena.update.notified.";
  const DISMISSED_KEY = "sena.update.dismissed";
  const FOCUS_RECHECK_MS = 15 * 60 * 1000;

  const versionButton = document.getElementById("app-version");
  const modal = document.getElementById("update-modal");
  const modalClose = document.getElementById("update-modal-close");
  const modalLater = document.getElementById("update-modal-later");
  const applyButton = document.getElementById("update-apply");
  const releaseButton = document.getElementById("update-release-link");
  const notesList = document.getElementById("update-notes");
  const statusEl = document.getElementById("update-status");
  const currentVersionEl = document.getElementById("update-current-version");
  const latestVersionEl = document.getElementById("update-latest-version");
  const metaEl = document.getElementById("update-meta");

  let currentInfo = null;
  let pendingCheck = null;
  let applying = false;
  let pollTimer = null;
  let lastCheckAt = 0;

  function readSession(key) {
    try {
      return window.sessionStorage.getItem(key) || "";
    } catch (error) {
      return "";
    }
  }

  function writeSession(key, value) {
    try {
      window.sessionStorage.setItem(key, value);
    } catch (error) {
      // sessionStorage puede estar restringido; no es crítico.
    }
  }

  function versionLabel(value) {
    return value ? `v${String(value).replace(/^v/i, "")}` : "—";
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    try {
      return date.toLocaleDateString("es-CO", {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
    } catch (error) {
      return date.toISOString().slice(0, 10);
    }
  }

  function setStatus(message, type) {
    if (!statusEl) return;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("is-error", type === "error");
    statusEl.classList.toggle("is-success", type === "success");
  }

  function showToast(message, type) {
    if (typeof window.showToast === "function") {
      window.showToast(message, type || "info");
    }
  }

  function desktopBridge() {
    return window.pywebview && window.pywebview.api
      ? window.pywebview.api
      : null;
  }

  function openExternal(url) {
    if (!url) return;
    const bridge = desktopBridge();
    if (bridge && typeof bridge.open_external === "function") {
      Promise.resolve(bridge.open_external(url)).catch(() => {});
      return;
    }
    window.open(url, "_blank", "noopener");
  }

  function dismissedVersion() {
    return currentInfo?.dismissed_version || readSession(DISMISSED_KEY);
  }

  function markDismissed(version) {
    if (!version) return;
    writeSession(DISMISSED_KEY, String(version));
    if (currentInfo) currentInfo.dismissed_version = String(version);
  }

  function wasShown(version) {
    return readSession(SHOWN_PREFIX + version) === "1";
  }

  function markShown(version) {
    if (version) writeSession(SHOWN_PREFIX + version, "1");
  }

  function wasNotified(version) {
    return readSession(NOTIFIED_PREFIX + version) === "1";
  }

  function markNotified(version) {
    if (version) writeSession(NOTIFIED_PREFIX + version, "1");
  }

  function anotherModalOpen() {
    return Boolean(document.querySelector(".modal-root.is-open"));
  }

  function renderNotes(info) {
    if (!notesList) return;
    notesList.replaceChildren();
    const items = Array.isArray(info?.notes_items) ? info.notes_items : [];
    if (!items.length) {
      const empty = document.createElement("li");
      empty.className = "update-notes-empty";
      empty.textContent = info?.update_available
        ? "El release no publicó notas de cambios."
        : "No hay novedades pendientes.";
      notesList.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      notesList.appendChild(li);
    });
  }

  function fillModal(info) {
    if (currentVersionEl) {
      currentVersionEl.textContent = versionLabel(info?.current_version);
    }
    if (latestVersionEl) {
      latestVersionEl.textContent = versionLabel(info?.latest_version);
    }
    renderNotes(info);

    if (metaEl) {
      const parts = [];
      if (info?.published_at) {
        parts.push(`Publicada el ${formatDate(info.published_at)}`);
      }
      if (info?.source === "github-api") {
        parts.push("Datos tomados de GitHub Releases");
      }
      metaEl.textContent = parts.join(" · ");
    }

    const available = Boolean(info?.update_available);
    if (applyButton) {
      applyButton.hidden = !available;
      applyButton.textContent = info?.can_self_update
        ? "Actualizar ahora"
        : "Descargar instalador";
    }
    if (releaseButton) {
      releaseButton.hidden = !info?.release_url;
    }
  }

  function updateVersionBadge(info) {
    if (!versionButton) return;
    const available = Boolean(info?.update_available);
    versionButton.classList.toggle("has-update", available);
    if (available) {
      versionButton.title = `Actualización ${versionLabel(info.latest_version)} disponible`;
      versionButton.setAttribute(
        "aria-label",
        `Versión ${versionLabel(info.current_version)}. Actualización ${versionLabel(info.latest_version)} disponible.`,
      );
    } else {
      versionButton.title = "Buscar actualizaciones";
      versionButton.setAttribute(
        "aria-label",
        `Versión ${versionLabel(info?.current_version)} de la aplicación. Buscar actualizaciones.`,
      );
    }
  }

  function notifyNative(info) {
    if (!info?.update_available || !info.latest_version) return;
    if (wasNotified(info.latest_version)) return;
    const bridge = desktopBridge();
    if (!bridge || typeof bridge.notify_update !== "function") return;

    markNotified(info.latest_version);
    const summary = (info.notes_items || []).slice(0, 3).join(" · ");
    Promise.resolve(
      bridge.notify_update(
        info.latest_version,
        `SENA Certificación ${versionLabel(info.latest_version)} disponible`,
        summary
          || "Abre la aplicación para ver las novedades e instalar la actualización.",
      ),
    ).catch(() => {});
  }

  function openModal() {
    if (!modal) return;
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    if (applyButton && !applyButton.hidden) {
      applyButton.focus();
    } else if (modalClose) {
      modalClose.focus();
    }
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function maybeNotify(info) {
    if (!info?.update_available || !info.latest_version) return;
    notifyNative(info);

    if (info.latest_version === dismissedVersion()) return;
    if (wasShown(info.latest_version)) return;
    if (anotherModalOpen()) return;
    if (info.error) return;

    markShown(info.latest_version);
    window.setTimeout(() => {
      if (modal?.classList.contains("is-open")) return;
      if (anotherModalOpen()) return;
      fillModal(currentInfo || info);
      setStatus("", "");
      openModal();
    }, 1200);
  }

  function handleResult(info) {
    updateVersionBadge(info);
    if (modal?.classList.contains("is-open")) {
      fillModal(info);
    }
    maybeNotify(info);
  }

  async function runCheck(force) {
    if (pendingCheck) return pendingCheck;
    pendingCheck = (async () => {
      let info;
      try {
        const url = force
          ? "/api/updates/check?force=1"
          : "/api/updates/check";
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          throw new Error("No se pudo consultar el servidor de actualizaciones.");
        }
        info = await response.json();
      } catch (error) {
        info = {
          ...(currentInfo || {}),
          update_available: false,
          error: error.message || "No se pudo consultar el servidor de actualizaciones.",
        };
      }
      currentInfo = { ...(currentInfo || {}), ...info };
      pendingCheck = null;
      lastCheckAt = Date.now();
      handleResult(currentInfo);
      return currentInfo;
    })();
    return pendingCheck;
  }

  async function open(forceRequest) {
    openModal();
    fillModal(currentInfo);
    if (currentInfo) updateVersionBadge(currentInfo);
    setStatus("Buscando actualizaciones…", "info");

    const info = await runCheck(Boolean(forceRequest));
    if (info.latest_version) markShown(info.latest_version);
    fillModal(info);

    if (info.error) {
      setStatus(
        "No se pudo consultar GitHub. Revisa la conexión e inténtalo de nuevo.",
        "error",
      );
      return;
    }
    if (!info.update_available) {
      setStatus(
        `Ya tienes la última versión (${versionLabel(info.current_version)}).`,
        "success",
      );
      return;
    }
    setStatus("", "");
  }

  async function dismiss() {
    const version = currentInfo?.latest_version;
    closeModal();
    if (!version) return;
    markDismissed(version);
    try {
      await fetch("/api/updates/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version }),
      });
    } catch (error) {
      // La marca local evita que el modal reaparezca en esta sesión.
    }
  }

  async function apply() {
    if (applying) return;
    const info = currentInfo;
    if (!info?.update_available) {
      setStatus("No hay una actualización pendiente.", "info");
      return;
    }

    if (!info.can_self_update) {
      const target = info.setup_url || info.release_url;
      if (!target) {
        setStatus("El release no publica un instalador descargable.", "error");
        return;
      }
      openExternal(target);
      setStatus(
        "Se abrió la descarga del instalador en el navegador. Ciérrala y ejecútala para actualizar.",
        "info",
      );
      return;
    }

    const confirmed = window.confirm(
      `Se descargará la versión ${versionLabel(info.latest_version)} y la aplicación se cerrará para instalar la actualización. ¿Continuar?`,
    );
    if (!confirmed) return;

    applying = true;
    const originalLabel = applyButton ? applyButton.textContent : "";
    if (applyButton) {
      applyButton.disabled = true;
      applyButton.textContent = "Descargando…";
    }
    setStatus(
      "Descargando y verificando el instalador. Esto puede tardar unos minutos…",
      "info",
    );

    try {
      const response = await fetch("/api/updates/apply", {
        method: "POST",
        headers: { "X-Requested-With": "SENACertificacion" },
      });
      let data = {};
      try {
        data = await response.json();
      } catch (error) {
        data = {};
      }
      if (!response.ok) {
        throw new Error(data.detail || "No se pudo iniciar la actualización.");
      }
      if (data.launched) {
        setStatus(
          "Instalador iniciado. La aplicación se cerrará para completar la actualización.",
          "success",
        );
        showToast("La actualización se está instalando.", "success");
        return;
      }
      if (data.reason === "manual") {
        openExternal(data.setup_url || info.setup_url || info.release_url);
        setStatus(
          "Modo manual: sigue el instalador que se abrió en el navegador.",
          "info",
        );
        return;
      }
      if (data.reason === "up-to-date") {
        setStatus(
          `Ya tienes la última versión (${versionLabel(info.current_version)}).`,
          "success",
        );
        return;
      }
      throw new Error("No se pudo iniciar la actualización.");
    } catch (error) {
      setStatus(
        error.message || "No se pudo iniciar la actualización.",
        "error",
      );
    } finally {
      applying = false;
      if (applyButton) {
        applyButton.disabled = false;
        applyButton.textContent = originalLabel;
      }
    }
  }

  if (versionButton) {
    versionButton.addEventListener("click", () => {
      open(true);
    });
  }
  if (modalClose) modalClose.addEventListener("click", closeModal);
  if (modalLater) modalLater.addEventListener("click", dismiss);
  if (applyButton) applyButton.addEventListener("click", apply);
  if (releaseButton) {
    releaseButton.addEventListener("click", () => {
      openExternal(currentInfo?.release_url);
    });
  }
  modal?.querySelectorAll("[data-close-update-modal]").forEach((element) => {
    element.addEventListener("click", closeModal);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal?.classList.contains("is-open")) {
      closeModal();
    }
  });

  // API para el bridge nativo y la bandeja del sistema.
  window.SenaUpdates = {
    open: () => open(false),
    check: () => runCheck(true),
    apply,
  };

  window.addEventListener("pywebviewready", () => {
    if (currentInfo) handleResult(currentInfo);
    else runCheck(false);
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (Date.now() - lastCheckAt < FOCUS_RECHECK_MS) return;
    runCheck(false);
  });

  function startPolling() {
    if (pollTimer) return;
    pollTimer = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      runCheck(false);
    }, POLL_INTERVAL_MS);
  }

  runCheck(false);
  startPolling();
})();
