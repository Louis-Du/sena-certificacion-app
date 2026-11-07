"""Pruebas de la consolidacion del dataset de informe (#46)."""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.models import ImportedRecord, ImportHistory, Learner
from app.services.indicadores import compute_indicadores_2026, compute_certificados_por_mes
from app.services.informes import _incidence_rows, _report_rows, consolidate_report_dataset


def _seed(session, information_type, records, *, source_type=None, status="completed", file_name="prueba.xlsx"):
    history = ImportHistory(
        file_name=file_name,
        information_type=information_type,
        source_type=source_type,
        status=status,
        records_count=len(records),
    )
    session.add(history)
    session.flush()
    for index, record in enumerate(records, start=2):
        session.add(
            ImportedRecord(
                import_id=history.id,
                information_type=information_type,
                record_key=f"{information_type}-{index}",
                row_number=index,
                payload=json.dumps(record),
            )
        )
    session.commit()
    return history.id


def _certificado(document, nivel, mes="JUNIO", estado="CERTIFICADOS", acta="36"):
    return {
        "nivel": nivel,
        "numero de documento": document,
        "nombre": f"Persona {document}",
        "ficha": "100",
        "acta": acta,
        "estado": estado,
        "mes de certificacion": mes,
    }


def _pendiente(document, nivel, motivo=None):
    return {
        "nivel": nivel,
        "numero de documento": document,
        "nombre": f"Persona {document}",
        "ficha": "100",
        "estado": "PENDIENTE",
        "motivo de no certificacion": motivo,
    }


def _meta(superior=None, tecnica=None, articulacion=None, complementaria=None):
    valores = {
        "superior": superior,
        "tecnica": tecnica,
        "articulacion": articulacion,
        "complementaria": complementaria,
    }
    return {k: v for k, v in valores.items() if isinstance(v, int)}


def _learner(document, reason, status="PENDIENTE"):
    return Learner(
        identification=document,
        name=f"Persona {document}",
        certification_status=status,
        non_certification_reason=reason,
    )


def _seed_incidence_learners(session):
    session.add_all(
        [
            _learner("2", "No anexa T&T, APE"),
            _learner("3", "No anexa T&T y Documento de Identidad"),
            _learner("4", "APE"),
            _learner("5", "No anexa T&T, Destrucción del Carnet"),
        ]
    )
    session.commit()


def test_sin_importaciones_advertencia_y_sin_cifras_inventadas(session_factory):
    with session_factory() as session:
        data = consolidate_report_dataset(session)

    assert data["source"] == "consolidado_lote_vigente"
    assert data["import_id"] is None
    assert data["file_name"] is None
    assert any("Sin consolidado vigente" in a for a in data["advertencias"])
    assert data["resumen_ejecutivo"]["total_meta"] is None
    assert data["resumen_ejecutivo"]["efectividad_global"] is None
    assert data["resumen_ejecutivo"]["pendientes_personas"] is None
    assert data["resumen_ejecutivo"]["certificados_personas"] == 0
    assert data["certificados_por_mes"] is not None
    assert data["causas_no_certificacion"]["motivos"] == []


def test_kpis_alineados_con_compute_indicadores(session_factory):
    with session_factory() as session:
        _seed(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        _seed(session, "pendientes", [_pendiente("2", "TÉCNICO", "APE")])
        _seed(session, "meta", [_meta(superior=100, tecnica=200, articulacion=50, complementaria=1000)])
        _seed(session, "complementaria", [{"canal": "presencial", "fecha": "2026-02-26", "cantidad": 10}])

        indicadores = compute_indicadores_2026(session)
        dataset = consolidate_report_dataset(session)

    assert dataset["resumen_ejecutivo"]["certificados_personas"] == indicadores["certificados_personas"]
    assert dataset["resumen_ejecutivo"]["pendientes_personas"] == indicadores["pendientes_personas"]
    assert dataset["resumen_ejecutivo"]["certificados_complementaria"] == indicadores["certificados_complementaria"]
    assert dataset["resumen_ejecutivo"]["avance_global"] == indicadores["avance_global"]
    assert dataset["resumen_ejecutivo"]["efectividad_global"] == indicadores["efectividad_global"]
    assert dataset["resumen_ejecutivo"]["total_meta"] == indicadores["total_meta"]
    assert dataset["desglose_por_categoria"] == indicadores["metricas"]
    assert dataset["certificados_por_mes"] == indicadores["certificados_por_mes"]
    assert dataset["causas_no_certificacion"]["motivos"] == indicadores["motivos"]
    assert dataset["actas"]["items"] == indicadores["ultimas_actas"]


def test_export_causas_reutiliza_conteo_canonico_del_indicador(session_factory):
    with session_factory() as session:
        _seed(
            session,
            "pendientes",
            [_pendiente("2", "TÉCNICO", "No anexa T&T, APE")],
        )
        dataset = consolidate_report_dataset(session)
        _, rows = _report_rows(dataset, "causas")

    assert {row["Motivo"]: row["Incidencias"] for row in rows} == {
        "No anexa T&T": 1,
        "APE": 1,
    }


def test_certificados_por_mes_presente_y_coherente(session_factory):
    with session_factory() as session:
        _seed(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        dataset = consolidate_report_dataset(session)
        cpm = compute_certificados_por_mes(session)

    assert "meses" in dataset["certificados_por_mes"]
    assert dataset["certificados_por_mes"] == cpm
    assert dataset["certificados_por_mes"]["total"] >= 0


def test_segundo_lote_usa_lote_vigente(session_factory):
    with session_factory() as session:
        id1 = _seed(
            session,
            "certificados",
            [_certificado("1", "TECNÓLOGO", "JUNIO")],
            source_type="actas_completo",
            file_name="lote1.xlsx",
        )
        _seed(session, "meta", [_meta(superior=100)], source_type="actas_completo")

        id2 = _seed(
            session,
            "certificados",
            [_certificado("2", "TÉCNICO", "JULIO"), _certificado("3", "TÉCNICO", "JULIO")],
            source_type="actas_completo",
            file_name="lote2.xlsx",
        )

        dataset = consolidate_report_dataset(session)

    assert dataset["import_id"] == id2
    assert dataset["file_name"] == "lote2.xlsx"
    assert dataset["resumen_ejecutivo"]["certificados_personas"] == 2


def test_efectividad_no_mezcla_complementaria(session_factory):
    with session_factory() as session:
        _seed(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        _seed(session, "pendientes", [_pendiente("2", "TÉCNICO", "APE")])
        _seed(session, "complementaria", [{"canal": "presencial", "fecha": "2026-02-26", "cantidad": 500}])
        _seed(session, "meta", [_meta(superior=100, tecnica=200, articulacion=50, complementaria=1000)])

        dataset = consolidate_report_dataset(session)

    assert dataset["resumen_ejecutivo"]["efectividad_global"] is not None
    # efectividad solo personas: 1 / (1+1) = 50.0
    assert dataset["resumen_ejecutivo"]["efectividad_global"] == 50.0
    assert dataset["resumen_ejecutivo"]["certificados_complementaria"] == 500


def test_endpoint_consolidado(client):
    from tests.test_informes_consolidado import _seed as seed_helper
    with client.session_factory() as session:
        seed_helper(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        seed_helper(session, "meta", [_meta(superior=100)])

    response = client.get("/api/informes/consolidado")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "consolidado_lote_vigente"
    assert "resumen_ejecutivo" in data
    assert "desglose_por_categoria" in data
    assert "certificados_por_mes" in data
    assert "causas_no_certificacion" in data
    assert "actas" in data
    assert "advertencias" in data

    resumen = client.get("/api/informes/consolidado/resumen")
    assert resumen.status_code == 200
    assert "resumen_ejecutivo" in resumen.json()


def test_endpoint_sin_lote_seguro(client):
    response = client.get("/api/informes/consolidado")
    assert response.status_code == 200
    data = response.json()
    assert any("Sin consolidado vigente" in a for a in data["advertencias"]) or data["advertencias"]
    assert data["resumen_ejecutivo"]["total_meta"] is None


def test_export_xlsx_con_datos(client):
    from tests.test_informes_consolidado import _seed as seed_helper
    with client.session_factory() as session:
        seed_helper(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        seed_helper(session, "meta", [_meta(superior=100)])

    response = client.get("/api/informes/export")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert "informe_certificacion_v1.xlsx" in response.headers["content-disposition"]

    import io
    import pandas as pd

    xls = pd.ExcelFile(io.BytesIO(response.content))
    assert set(xls.sheet_names) == {"Resumen", "Categorias", "CertificadosPorMes", "Causas", "Actas", "Advertencias"}
    categorias = pd.read_excel(xls, "Categorias")
    assert "Categoria" in categorias.columns
    assert len(categorias) >= 1
    resumen = pd.read_excel(xls, "Resumen")
    assert "Campo" in resumen.columns and "Valor" in resumen.columns


def test_export_xlsx_sin_datos(client):
    response = client.get("/api/informes/export")
    assert response.status_code == 404
    assert "No hay datos" in response.json()["detail"]


def test_exporta_csv_y_catalogo_de_informes(client):
    from tests.test_informes_consolidado import _seed as seed_helper
    with client.session_factory() as session:
        seed_helper(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        seed_helper(session, "meta", [_meta(superior=100)])

    catalog = client.get("/api/informes/formats?type=causas")
    assert catalog.status_code == 200
    assert catalog.json()["formats"] == ["pdf", "xlsx", "csv"]

    consolidated_catalog = client.get("/api/informes/formats?type=consolidado")
    assert consolidated_catalog.status_code == 200
    assert consolidated_catalog.json()["formats"] == ["pdf", "xlsx"]

    response = client.get("/api/informes/export?type=causas&format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Motivo" in response.content.decode("utf-8-sig")

    executive = client.get("/api/informes/export?type=ejecutivo&format=xlsx")
    assert executive.status_code == 200
    assert "spreadsheetml" in executive.headers["content-type"]

    pdf = client.get("/api/informes/export?type=general&format=pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    consolidated_xlsx = client.get("/api/informes/export?type=consolidado&format=xlsx")
    assert consolidated_xlsx.status_code == 200
    assert "spreadsheetml" in consolidated_xlsx.headers["content-type"]
    workbook = load_workbook(BytesIO(consolidated_xlsx.content), read_only=True)
    assert {
        "Resumen",
        "Categorias",
        "CertificadosPorMes",
        "Ejecutivo",
        "Aprendices",
        "Pendientes",
        "Causas",
        "Actas",
    } <= set(workbook.sheetnames)
    assert "Causas1" not in workbook.sheetnames
    assert "Actas1" not in workbook.sheetnames
    assert all(
        "Panel visual" not in cell.value
        for worksheet in workbook.worksheets
        for row in worksheet.iter_rows()
        for cell in row
        if isinstance(cell.value, str)
    )

    consolidated_pdf = client.get("/api/informes/export?type=consolidado&format=pdf")
    assert consolidated_pdf.status_code == 200
    assert consolidated_pdf.headers["content-type"].startswith("application/pdf")
    assert consolidated_pdf.content.startswith(b"%PDF")


def test_listados_de_informes_conservan_columnas_de_negocio():
    learner = SimpleNamespace(
        identification="1",
        name="Persona 1",
        program="Programa",
        certification_status="PENDIENTE",
        group_code="100",
        act_number="36",
        non_certification_reason="Documento pendiente",
    )
    _, aprendiz_rows = _report_rows({"_learners": [learner]}, "aprendices")
    _, pendiente_rows = _report_rows({"_learners": [learner]}, "pendientes")

    assert list(aprendiz_rows[0]) == [
        "Identificacion",
        "Nombre",
        "Programa",
        "Estado",
        "Ficha",
        "Acta",
    ]
    assert list(pendiente_rows[0]) == [
        "Identificacion",
        "Nombre",
        "Programa",
        "Estado",
        "Ficha",
        "Motivo",
    ]
    assert pendiente_rows[0]["Motivo"] == "Documento pendiente"


def test_informe_ejecutivo_expone_contexto_y_universos():
    _, rows = _report_rows(
        {
            "periodo": "Ene-Sep 2026",
            "source": "consolidado_lote_vigente",
            "file_name": "ACTAS 2026.xlsx",
            "import_id": 7,
            "resumen_ejecutivo": {
                "meta_total": 100,
                "certificados_personas": 80,
                "certificados_complementaria": 20,
                "pendientes_personas": 10,
                "avance_global": 100,
                "efectividad_global": 88.9,
                "brecha_total": 0,
            },
        },
        "ejecutivo",
    )
    values = {row["Indicador"]: row["Valor"] for row in rows}
    assert values["Periodo"] == "Ene-Sep 2026"
    assert values["Fuente"] == "consolidado_lote_vigente"
    assert values["Meta total"] == 100
    assert values["Certificados personas"] == 80
    assert values["Certificados complementaria"] == 20
    assert values["Pendientes personas"] == 10
    assert values["Brecha total"] == 0


def test_graficos_excel_tienen_una_serie_y_etiquetas_legibles(client):
    from openpyxl.chart.label import DataLabelList

    with client.session_factory() as session:
        _seed(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        _seed(session, "meta", [_meta(superior=100)])

    response = client.get("/api/informes/export")
    workbook = load_workbook(BytesIO(response.content))
    summary = workbook["Resumen"]
    assert len(summary._charts) == 2

    category_chart, month_chart = summary._charts
    assert category_chart.type == "col"
    assert category_chart.legend is None
    assert category_chart.y_axis.scaling.min == 0
    assert category_chart.y_axis.scaling.max == 100
    assert len(category_chart.ser) == 1
    assert isinstance(category_chart.dataLabels, DataLabelList)
    assert category_chart.dataLabels.showVal
    assert category_chart.dataLabels.showSerName is False
    assert category_chart.dataLabels.showCatName is False
    assert month_chart.legend is None
    assert len(month_chart.ser) == 1
    assert month_chart.dataLabels is None


def test_export_pendientes_incluye_grafico_de_incidencias_no_excluyentes(client):
    from openpyxl.chart.label import DataLabelList

    with client.session_factory() as session:
        _seed(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        _seed(session, "meta", [_meta(superior=100)])
        _seed_incidence_learners(session)

    response = client.get("/api/informes/export?type=pendientes&format=xlsx")
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    assert {"Pendientes", "IncidenciasPendientes"} <= set(workbook.sheetnames)

    data_sheet = workbook["IncidenciasPendientes"]
    counts = {
        row[0].value: row[1].value
        for row in data_sheet.iter_rows(min_row=2)
        if row[0].value
    }
    # Un aprendiz suma en cada incidencia que tenga, aunque tenga varias.
    assert counts == {
        "No anexa T&T": 3,
        "APE": 2,
        "Destrucción del carnet": 1,
        "Documento de identidad": 1,
    }

    target = workbook["Pendientes"]
    assert len(target._charts) == 1
    chart = target._charts[0]
    assert chart.type == "bar"
    assert len(chart.ser) == 1
    assert isinstance(chart.dataLabels, DataLabelList)
    assert chart.dataLabels.showVal
    assert any(
        isinstance(cell.value, str) and "no son excluyentes" in cell.value
        for row in target.iter_rows()
        for cell in row
    )


def test_export_consolidado_coloca_grafico_de_incidencias_en_resumen(client):
    with client.session_factory() as session:
        _seed(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        _seed(session, "meta", [_meta(superior=100)])
        _seed_incidence_learners(session)

    response = client.get("/api/informes/export?type=consolidado&format=xlsx")
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    assert "IncidenciasPendientes" in workbook.sheetnames

    summary = workbook["Resumen"]
    assert len(summary._charts) == 3
    assert summary._charts[-1].type == "bar"
    assert any(
        isinstance(cell.value, str) and "no son excluyentes" in cell.value
        for row in summary.iter_rows()
        for cell in row
    )


def test_incidence_rows_usa_causas_cuando_no_hay_padron_local():
    rows = _incidence_rows(
        {
            "causas_no_certificacion": {
                "motivos": [
                    {"motivo": "No anexa T&T", "cantidad": 2},
                    {"motivo": "APE", "cantidad": 1},
                ]
            }
        }
    )
    assert rows == [
        {"Incidencia": "No anexa T&T", "Aprendices": 2},
        {"Incidencia": "APE", "Aprendices": 1},
    ]
