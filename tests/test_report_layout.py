from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.services.informes import consolidate_report_dataset
from app.services.report_xlsx import build_report_xlsx


@pytest.mark.parametrize(
    "report_type",
    [
        "causas",
        "aprendices",
        "consolidado",
        "ejecutivo",
        "actas",
        "pendientes",
    ],
)
def test_informes_sin_freeze_agresivo(session_factory, report_type):
    """Los informes generados no congelan filas/columnas de forma agresiva.

    Antes la prueba dependía de archivos ``informe_*.xlsx`` sueltos en la raíz
    del repositorio. Ahora se generan en memoria con el mismo servicio que usa
    la exportación real, de modo que la prueba es reproducible.
    """
    with session_factory() as session:
        dataset = consolidate_report_dataset(session)

    content = build_report_xlsx(dataset, report_type)
    workbook = load_workbook(BytesIO(content))
    for worksheet in workbook.worksheets:
        assert worksheet.freeze_panes is None, (
            report_type,
            worksheet.title,
            worksheet.freeze_panes,
        )
