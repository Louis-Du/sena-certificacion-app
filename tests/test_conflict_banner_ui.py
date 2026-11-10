"""Regresiones de la UI de resolución de conflictos.

Estas pruebas no levantan un navegador: verifican el contrato estático del
markup y del JavaScript que sostiene el modal de decisiones explícitas.
"""

from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
UI_JS = (ROOT / "app" / "static" / "ui-enhancements.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


def test_banner_markup_has_resolution_and_dismiss_actions():
    assert 'id="global-conflict-banner"' in INDEX
    assert 'id="global-conflict-resolve"' in INDEX
    assert 'id="global-conflict-later"' in INDEX
    assert "Resolver ahora" in INDEX
    assert "Más tarde" in INDEX


def test_banner_is_fixed_on_top_without_blocking_layout():
    assert ".global-conflict-banner" in STYLES
    assert "position: fixed" in STYLES
    assert "body.has-conflict-banner .shell" in STYLES
    assert "--conflict-banner-height" in STYLES


def test_frontend_polls_and_exposes_bridge_entrypoint():
    assert "CONFLICT_POLL_INTERVAL_MS = 12000" in APP_JS
    assert "window.SenaConflictBanner" in APP_JS
    assert "openResolution: openPendingConflictResolution" in APP_JS
    assert "pywebviewready" in APP_JS


def test_resolution_does_not_depend_on_history_replace_state():
    """Browser Guard lanza 'Breaking Browser Locker Behavior detected'.

    El flujo de resolución debe seguir abriendo el modal aunque un bloqueador
    intercepte history.replaceState. Por eso solo existe una llamada directa,
    encapsulada en el helper seguro, y la vista se cambia sin actualizar hash.
    """

    assert APP_JS.count("history.replaceState(null") == 1
    assert "function replaceLocationHash(hash)" in APP_JS
    assert 'showView("carga", false);' in APP_JS
    assert "replaceHashSafely" in UI_JS


def test_conflict_panel_only_contains_the_state_decision():
    start = INDEX.index('id="coherence-conflicts"')
    end = INDEX.index("</section>", start)
    panel = INDEX[start:end]

    assert 'id="open-conflict-resolution"' in panel
    assert "Certificado" not in panel  # las opciones las construye app.js
    assert "solo lee Google Sheets" not in panel
    assert "sheets-manual-cleanup" not in panel
    assert "corrección manual" not in panel


def test_each_requirement_has_three_explicit_exclusive_options():
    # La decisión nunca se deduce por clic/no clic: las tres opciones se pintan
    # como botones excluyentes y "no tocar" deja el conflicto sin resolver.
    assert (
        'const REQUIREMENT_CONFLICT_STATUS_OPTIONS = ["Pendiente", "Cumplido", "No aplica"];'
        in APP_JS
    )
    assert "REQUIREMENT_CONFLICT_STATUS_OPTIONS.forEach" in APP_JS
    assert 'button.dataset.statusOption = status;' in APP_JS
    assert 'button.setAttribute("aria-pressed", "false");' in APP_JS
    assert "No tocar una opción deja el conflicto sin resolver" in INDEX
    assert '<span class="conflict-status-chip is-pending">Pendiente</span>' in INDEX
    assert '<span class="conflict-status-chip is-fulfilled">Cumplido</span>' in INDEX
    assert '<span class="conflict-status-chip is-na">No aplica</span>' in INDEX


def test_requirement_modal_has_groups_filters_batch_actions_and_progress():
    assert 'id="conflict-resolution-modal"' in INDEX
    assert 'id="conflict-tab-status"' in INDEX
    assert 'id="conflict-tab-requirement"' in INDEX
    assert 'id="requirement-conflict-list"' in INDEX
    assert 'id="requirement-conflict-search"' in INDEX
    assert 'id="requirement-conflict-group-filter"' in INDEX
    assert 'id="requirement-conflict-type-filter"' in INDEX
    assert 'id="requirement-conflict-state-filter"' in INDEX
    assert 'id="requirement-conflict-visible-count"' in INDEX
    assert 'id="requirement-batch-suggest"' in INDEX
    assert 'id="requirement-batch-motivo"' in INDEX
    assert 'id="requirement-batch-column"' in INDEX
    assert 'id="requirement-batch-tyt"' in INDEX
    assert 'id="conflict-progress-bar"' in INDEX
    assert 'id="conflict-progress-text"' in INDEX
    assert "Continuar a confirmación" in INDEX

    assert "Alta confianza / auto-sugerible" in INDEX
    assert '<option value="medium">Media</option>' in INDEX
    assert '<option value="review">Requiere revisión</option>' in INDEX
    assert "Aplicar sugerencia" in INDEX
    assert "El motivo manda" in INDEX
    assert "La columna manda" in INDEX
    assert "TyT no TGO → No aplica" in INDEX


def test_progress_uses_rule_manual_and_unresolved_counters():
    assert "function conflictProgressMessage(counters)" in APP_JS
    assert "`Estados: ${counters.statusResolved}/${counters.statusTotal} resueltos · `" in APP_JS
    assert (
        "`Requisitos: ${counters.rule} por regla, ${counters.manual} manuales, `"
        in APP_JS
    )
    assert "`${counters.unresolved} sin resolver`" in APP_JS
    assert "Estados: 0/0 resueltos · Requisitos: 0 por regla, 0 manuales, 0 sin resolver" in INDEX


def test_requirement_groups_are_rendered_from_the_backend_classification():
    assert "REQUIREMENT_CONFLICT_GROUP_META" in APP_JS
    assert "const groupOrder = [\"high\", \"medium\", \"review\"];" in APP_JS
    assert "item.group || \"review\"" in APP_JS
    assert "renderRequirementConflictGroups" in APP_JS
    assert "visibleRequirementConflictItems" in APP_JS
    assert "requirementItemMatchesFilters" in APP_JS
    assert "Mostrando ${visible.length} de ${requirementConflictItems.length}" in APP_JS


def test_requirement_conflicts_are_submitted_with_source_and_fingerprint():
    assert "requirementConflicts" in APP_JS
    assert "requirement_conflict_resolutions" in APP_JS
    assert "collectRequirementConflictResolutions" in APP_JS
    # Solo se envían decisiones explícitas; reglas y guardadas las reaplica el
    # backend sin convertirlas en una decisión nueva.
    assert "if (!decision || !decision.explicit || !isRequirementDecisionResolved(decision))" in APP_JS
    assert 'source: decision.source === "bulk" ? "bulk" : "user"' in APP_JS
    assert "conflict_fingerprint: item.fingerprint || undefined" in APP_JS


def test_bulk_actions_respect_the_visible_filter_and_do_not_override_rules():
    assert "function applyRequirementBulkAction(action)" in APP_JS
    assert "const visible = visibleRequirementConflictItems();" in APP_JS
    assert "setRequirementConflictDecision(item, status, \"bulk\");" in APP_JS
    assert "alreadyRule" in APP_JS
    assert "Se aplican solo a los conflictos visibles con el filtro actual." in INDEX
    for action in ("suggest", "motivo", "column", "tyt"):
        assert f'applyRequirementBulkAction("{action}")' in APP_JS


def test_second_confirmation_has_summary_and_conditional_sheets_warning():
    assert 'id="conflict-confirm-modal"' in INDEX
    assert "Antes de confirmar" in INDEX
    assert 'id="conflict-confirm-summary"' in INDEX
    assert "Resumen antes de confirmar" in APP_JS
    assert '["Por regla automática", String(counters.rule)]' in APP_JS
    assert '["Manuales o guardados", String(counters.manual)]' in APP_JS
    assert '["Sin resolver", String(counters.unresolved)]' in APP_JS
    assert "Esta aplicación solo lee Google Sheets" in INDEX
    assert "el cruce permanecerá allí" in INDEX
    assert "corríjala o elimine el registro duplicado de forma manual" in INDEX
    assert "la app tomará ese estado y descartará el desempate anterior" in INDEX
    assert "Ya corregí o eliminé el registro duplicado en Google Sheets" in INDEX
    assert "Solo documental en la app; no modifica Google Sheets." in INDEX
    assert ">Volver</button>" in INDEX
    assert ">Confirmar de todos modos</button>" in INDEX


def test_sheets_warning_only_appears_when_there_are_status_conflicts():
    assert "const hasStatusConflicts = counters.statusTotal > 0;" in APP_JS
    assert "conflictConfirmSheetsCopy.hidden = !hasStatusConflicts;" in APP_JS
    assert "conflictConfirmAck.hidden = !hasStatusConflicts;" in APP_JS
    assert "const hasRequirementConflicts = counters.requirementTotal > 0;" in APP_JS


def test_import_post_blocks_unresolved_and_waits_for_second_confirmation():
    assert "function openConflictConfirmModal()" in APP_JS
    assert "const pendingDecisions = counters.statusPending + counters.unresolved;" in APP_JS
    assert "if (pendingDecisions > 0)" in APP_JS
    assert "if (needsConflictConfirmation && !conflictConfirmBypass)" in APP_JS
    assert "openConflictConfirmModal();" in APP_JS
    assert "conflictConfirmBypass = true;" in APP_JS
    assert "conflictConfirmBypass = false;" in APP_JS
    assert "sheets_manual_cleanup_acknowledged" in APP_JS
    assert "payload.sheets_manual_cleanup_acknowledged" in APP_JS
    assert 'const endpoint = isSheetsResolve' in APP_JS
    assert '? "/api/sheets/sync/resolve"' in APP_JS


def test_warning_modal_escape_does_not_cancel_import_review():
    assert 'getElementById("conflict-confirm-modal")' in UI_JS
    assert 'warningModal?.classList.contains("is-open")' in UI_JS


def test_banner_text_mentions_resolution_and_google_sheets():
    assert "de resolución (Google Sheets)" in APP_JS
    assert "conflictCountLabel(count)" in APP_JS


def test_styles_cover_groups_filters_batch_and_responsive_modal():
    assert ".conflict-resolution-dialog" in STYLES
    assert ".requirement-conflict-group" in STYLES
    assert ".requirement-conflict-card" in STYLES
    assert ".requirement-status-option" in STYLES
    assert ".requirement-batch-bar" in STYLES
    assert ".conflict-progress-bar" in STYLES
    assert "@media" in STYLES
