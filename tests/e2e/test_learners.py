from pathlib import Path

from tests.conftest import csv_bytes


def _write_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _import_learners(page, app_url, tmp_path, content: bytes) -> None:
    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    file_path = _write_file(tmp_path, "df14a.csv", content)
    page.set_input_files("#file-input", str(file_path))
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")
    page.click("#confirm-button")
    page.wait_for_selector("#confirm-button", state="hidden")


def test_learners_table_loads_after_import(page, app_url, tmp_path):
    _import_learners(
        page,
        app_url,
        tmp_path,
        csv_bytes("identificacion,nombre,programa\n3001,Carla,Software\n3002,Diego,Redes\n"),
    )
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list tr")
    assert "Carla" in page.locator("#learners-list").text_content()
    assert "Diego" in page.locator("#learners-list").text_content()


def test_learner_search_filters_results(page, app_url, tmp_path):
    _import_learners(
        page,
        app_url,
        tmp_path,
        csv_bytes("identificacion,nombre,programa\n4001,Elena,Software\n4002,Fabio,Redes\n"),
    )
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list tr")
    page.fill("#learner-search", "Elena")
    page.wait_for_timeout(300)
    page.wait_for_selector("#learners-list tr")
    text = page.locator("#learners-list").text_content()
    assert "Elena" in text
    assert "Fabio" not in text


def test_open_learner_detail_shows_basic_info(page, app_url, tmp_path):
    _import_learners(
        page,
        app_url,
        tmp_path,
        csv_bytes("identificacion,nombre,programa\n5001,Gema,Logistica\n"),
    )
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list tr")
    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-detail-content:not([hidden])")
    assert "Gema" in page.locator("#learner-detail-title").text_content()
    assert "5001" in page.locator("#learner-basic-info").text_content()
    page.click("#back-to-learners")
    page.wait_for_selector("#learner-detail", state="hidden")
