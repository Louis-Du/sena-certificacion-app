from pathlib import Path

from tests.conftest import csv_bytes


def _validate_file(page, app_url, file_path: Path, information_type: str) -> None:
    page.goto(app_url)
    page.click(f'.category-option[data-type="{information_type}"]')
    page.set_input_files("#file-input", str(file_path))
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")


def test_import_success_banner_hides_flow_and_resets_without_losing_type(
    page, app_url, tmp_path
):
    file_path = tmp_path / "df14a.csv"
    file_path.write_bytes(
        csv_bytes(
            "identificacion,nombre,programa,FICHA\n"
            "7101,Laura,Software,4501\n"
            "7102,Mario,Redes,4502\n"
        )
    )
    _validate_file(page, app_url, file_path, "df14a")
    page.click("#modal-confirm-button")
    page.wait_for_selector("#import-success-banner:not([hidden])")
    page.wait_for_selector("#history-list .history-item")

    # Cierre de tarea: banner, pasos completados y sin acciones del flujo previo.
    banner = page.locator("#import-success-banner")
    assert "Importación completada" in banner.text_content()
    meta = page.locator("#import-success-meta").text_content()
    assert "df14a.csv" in meta
    assert "2 registros procesados" in meta
    assert "+2 nuevos" in meta
    assert "is-import-success" in (page.locator("#carga-view").get_attribute("class") or "")
    assert page.locator(".steps .step.done").count() == 3
    assert page.locator(".steps .step.active").count() == 0
    assert page.locator(".type-panel").is_hidden()
    assert page.locator(".upload-panel").is_hidden()
    assert page.locator("#file-panel").is_hidden()
    assert page.locator("#validation-panel").is_hidden()
    assert page.locator(".actions").is_hidden()

    # El historial lateral refleja la importación recién confirmada.
    history = page.locator("#history-list").text_content()
    assert "df14a.csv" in history
    assert "Éxito" in history

    # CTA contextual y foco anunciable al entrar en éxito.
    assert page.locator("#view-imported-button").text_content() == "Ver aprendices"
    page.wait_for_function(
        "() => document.activeElement.id === 'import-success-banner'"
    )

    # Navegación al destino contextual y regreso conservando el estado de éxito.
    page.click("#view-imported-button")
    page.wait_for_selector("#aprendices-view:not([hidden])")
    page.wait_for_selector("#learners-list .detail-button")
    assert "Laura" in page.locator("#learners-list").text_content()
    page.click('a[data-view="carga"]')
    page.wait_for_selector("#carga-view:not([hidden])")
    assert not page.locator("#import-success-banner").is_hidden()

    # Nueva importación limpia solo la UI y conserva el tipo elegido.
    page.click("#new-import-button")
    assert page.locator("#import-success-banner").is_hidden()
    assert "is-import-success" not in (
        page.locator("#carga-view").get_attribute("class") or ""
    )
    assert page.locator(".type-panel").is_visible()
    assert page.locator(".upload-panel").is_visible()
    assert page.locator(".actions").is_visible()
    assert page.locator("#file-panel").is_hidden()
    assert page.locator("#validation-panel").is_hidden()
    assert page.locator("#validate-button").is_disabled()
    assert page.locator('.category-option[data-type="df14a"].selected').count() == 1
    assert page.locator(".steps .step.active").text_content().strip() == "1 Seleccionar"
    page.wait_for_function("() => document.activeElement.id === 'drop-zone'")
    assert page.input_value("#file-input") == ""


def test_acta_import_success_offers_act_view(page, app_url):
    correctos = Path(__file__).resolve().parents[2] / "archivos_prueba" / "correctos"
    _validate_file(
        page,
        app_url,
        correctos / "Acta_certificacion_correcto.pdf",
        "acta",
    )
    page.click("#modal-confirm-button")
    page.wait_for_selector("#import-success-banner:not([hidden])")
    page.wait_for_selector("#history-list .history-item")

    meta = page.locator("#import-success-meta").text_content()
    assert "Acta_certificacion_correcto.pdf" in meta
    assert "aprendices vinculados" in meta
    view_button = page.locator("#view-imported-button")
    assert view_button.text_content() == "Ver actas"
    view_button.click()
    page.wait_for_selector("#actas-view:not([hidden])")
    page.wait_for_selector("#acts-list tr")
    assert "101-2026" in page.locator("#acts-list").text_content()
