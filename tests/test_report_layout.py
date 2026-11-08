from io import BytesIO

from openpyxl import load_workbook


def _assert_no_freeze(path):
    wb = load_workbook(path)
    for ws in wb.worksheets:
        assert ws.freeze_panes is None, (path, ws.title, ws.freeze_panes)


def test_informes_sin_freeze_agresivo():
    for path in [
        "informe_causas.xlsx",
        "informe_aprendices.xlsx",
        "informe_consolidado.xlsx",
        "informe_ejecutivo.xlsx",
        "informe_actas.xlsx",
        "informe_pendientes.xlsx",
    ]:
        _assert_no_freeze(path)

