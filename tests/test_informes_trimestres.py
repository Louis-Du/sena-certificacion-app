"""Pruebas del informe de gestión por trimestre (Parte B).

Cubren:
* el mapa T1-T4 y los modos ``acumulado`` / ``solo_trimestre``;
* el filtrado de CERTIFICADOS por mes y de COMPLEMENTARIA por fecha;
* que la META siga siendo anual en todos los periodos;
* la generación del Word T2 acumulado (corte 30 de junio, Trimestre II y
  cifras filtradas ene-jun).
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from app.models import ImportedRecord, ImportHistory
from app.services.indicadores import compute_indicadores_2026, resolver_periodo
from app.services.parsers import read_complementaria_records, read_meta_sheet


def _seed(session, information_type: str, records: list[dict]) -> None:
    history = ImportHistory(
        file_name="prueba.xlsx",
        information_type=information_type,
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


def _certificado(document: str, nivel: str, mes: str) -> dict:
    return {
        "nivel": nivel,
        "numero de documento": document,
        "nombre": f"Persona {document}",
        "ficha": "100",
        "acta": "36",
        "estado": "CERTIFICADOS",
        "mes de certificacion": mes,
    }


def _complementaria(canal: str, fecha: str, cantidad: int) -> dict:
    return {"canal": canal, "fecha": fecha, "cantidad": cantidad}


def _meta(
    superior: int = 100,
    tecnica: int = 200,
    articulacion: int = 50,
    complementaria: int = 1000,
    campesena: int = 300,
    fullpopular: int = 400,
) -> dict:
    return {
        "superior": superior,
        "tecnica": tecnica,
        "articulacion": articulacion,
        "complementaria": complementaria,
        "campesena": campesena,
        "fullpopular": fullpopular,
    }


def _seed_periodo(session) -> None:
    _seed(
        session,
        "certificados",
        [
            _certificado("1", "TECNÓLOGO", "ENERO"),
            _certificado("2", "TECNÓLOGO", "MARZO"),
            _certificado("3", "TÉCNICO", "ABRIL"),
            _certificado("4", "TÉCNICO", "JUNIO"),
            _certificado("5", "MEDIA TÉCNICA", "JULIO"),
            _certificado("6", "TECNÓLOGO", "SEPTIEMBRE"),
            _certificado("7", "TECNÓLOGO", "OCTUBRE"),
        ],
    )
    _seed(
        session,
        "complementaria",
        [
            _complementaria("presencial", "2026-01-15", 10),
            _complementaria("virtual", "2026-03-15", 20),
            _complementaria("presencial", "2026-04-15", 30),
            _complementaria("virtual", "2026-06-15", 40),
            _complementaria("campesena", "2026-07-15", 50),
            _complementaria("fullpopular", "2026-09-15", 60),
            _complementaria("presencial", "2026-10-01", 70),
        ],
    )
    _seed(session, "meta", [_meta()])


@pytest.mark.parametrize(
    ("trimestre", "modo", "inicio", "fin", "meses", "periodo"),
    [
        ("T1", "acumulado", "2026-01-01", "2026-03-31", 3, "Enero - Marzo 2026"),
        ("T1", "solo_trimestre", "2026-01-01", "2026-03-31", 3, "Enero - Marzo 2026"),
        ("T2", "solo_trimestre", "2026-04-01", "2026-06-30", 3, "Abril - Junio 2026"),
        ("T2", "acumulado", "2026-01-01", "2026-06-30", 6, "Enero - Junio 2026"),
        ("T3", "solo_trimestre", "2026-07-01", "2026-09-30", 3, "Julio - Septiembre 2026"),
        ("T3", "acumulado", "2026-01-01", "2026-09-30", 9, "Enero - Septiembre 2026"),
        ("T4", "solo_trimestre", "2026-10-01", "2026-12-31", 3, "Octubre - Diciembre 2026"),
        ("T4", "acumulado", "2026-01-01", "2026-12-31", 12, "Enero - Diciembre 2026"),
    ],
)
def test_resolver_periodo_t1_t4_y_modos(trimestre, modo, inicio, fin, meses, periodo):
    data = resolver_periodo(trimestre, modo, 2026)

    assert data["inicio"] == inicio
    assert data["fin"] == fin
    assert data["periodo"] == periodo
    assert len(data["meses"]) == meses
    assert data["trimestre_codigo"] == trimestre
    assert data["modo"] == modo


def test_resolver_periodo_default_es_t3_acumulado_y_valida_entradas():
    default = resolver_periodo()
    assert default["trimestre_codigo"] == "T3"
    assert default["modo"] == "acumulado"
    assert default["inicio"] == "2026-01-01"
    assert default["fin"] == "2026-09-30"
    assert default["fecha_corte_texto"] == "30 de septiembre de 2026"

    with pytest.raises(ValueError):
        resolver_periodo("T5")
    with pytest.raises(ValueError):
        resolver_periodo("T2", "otro_modo")


def test_complementaria_y_certificados_se_filtran_por_periodo(session_factory):
    with session_factory() as session:
        _seed_periodo(session)

        t2_solo = compute_indicadores_2026(
            session, trimestre="T2", modo="solo_trimestre"
        )
        t2_acum = compute_indicadores_2026(
            session, trimestre="T2", modo="acumulado"
        )
        t3_acum = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )
        t4_acum = compute_indicadores_2026(
            session, trimestre="T4", modo="acumulado"
        )

    assert t2_solo["periodo"] == "Abril - Junio 2026"
    assert t2_solo["certificados_personas"] == 2  # abril + junio
    assert t2_solo["certificados_complementaria"] == 70  # 30 + 40

    assert t2_acum["periodo"] == "Enero - Junio 2026"
    assert t2_acum["certificados_personas"] == 4  # ene, mar, abr, jun
    assert t2_acum["certificados_complementaria"] == 100  # 10+20+30+40

    assert t3_acum["periodo"] == "Enero - Septiembre 2026"
    assert t3_acum["certificados_personas"] == 6  # excluye octubre
    assert t3_acum["certificados_complementaria"] == 210  # excluye 70 de oct

    assert t4_acum["periodo"] == "Enero - Diciembre 2026"
    assert t4_acum["certificados_personas"] == 7
    assert t4_acum["certificados_complementaria"] == 280


FIXTURE_COMPLEMENTARIA_30 = (
    Path(__file__).resolve().parents[1]
    / "archivos_prueba"
    / "correctos"
    / "ACTAS_2026_30_REGISTROS_fechas_datetime.xlsx"
)


def test_complementaria_30_registros_datetime_correctos_en_t3_acumulado(session_factory):
    """Regresion: las fechas datetime correctas no deben salirse del T3.

    Fixture basado en ACTAS_2026_30_REGISTROS (COMPLEMENTARIA + META). Antes de
    corregir el swap, el 10 de abril se interpretaba como 4 de octubre y el 10
    de julio como 7 de octubre, dejando fuera del corte 30/09 parte de
    Campesena y Full Popular.
    """
    content = FIXTURE_COMPLEMENTARIA_30.read_bytes()
    registros = read_complementaria_records(content)
    metas = read_meta_sheet(content)
    assert metas["campesena"] == 2126
    assert metas["fullpopular"] == 2104

    with session_factory() as session:
        _seed(
            session,
            "complementaria",
            [
                {
                    "canal": registro["canal"],
                    "fecha": registro["fecha"],
                    "cantidad": registro["cantidad"],
                }
                for registro in registros
            ],
        )
        _seed(session, "meta", [metas])
        data = compute_indicadores_2026(session, trimestre="T3", modo="acumulado")

    canales = data["complementaria_canales"]
    assert canales["presencial"] == 474
    assert canales["virtual"] == 550
    assert canales["campesena"] == 210
    assert canales["fullpopular"] == 245
    assert data["certificados_complementaria"] == 1479
    assert data["metas_canales"] == {"campesena": 2126, "fullpopular": 2104}


def test_metas_anuales_no_cambian_entre_trimestres(session_factory):
    with session_factory() as session:
        _seed_periodo(session)
        periodos = [
            compute_indicadores_2026(session, trimestre=trimestre, modo=modo)
            for trimestre, modo in [
                ("T1", "acumulado"),
                ("T2", "solo_trimestre"),
                ("T3", "acumulado"),
                ("T4", "acumulado"),
            ]
        ]

    for data in periodos:
        metas = {item["category"]: item["meta"] for item in data["metricas"]}
        assert metas == {
            "superior": 100,
            "tecnica": 200,
            "articulacion": 50,
            "complementaria": 1000,
        }
        assert data["metas_canales"] == {"campesena": 300, "fullpopular": 400}


def test_docx_t2_acumulado_usa_corte_trimestre_y_cifras_ene_jun(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    response = client.get(
        "/api/informes/word?trimestre=T2&modo=acumulado"
    )
    assert response.status_code == 200, response.text

    document = Document(BytesIO(response.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Presentar la gestión realizada" in text
    assert "Trimestre II de 2026" in text
    assert "30 de junio de 2026" in text
    assert "¿Cómo fue la gestión en el periodo II para el Indicador: “Certificación - Educación Superior”" in text
    assert "Dependencia de las actas de certificación" in text
    assert "Cantidad de aprendices relacionados en las actas" in text
    assert "SOFIA Plus" in text
    assert "Pendiente de registro por la dependencia." in text
    assert "Enero - Septiembre 2026" not in text
    for prohibido in (
        "registrados en el sistema",
        "fuentes institucionales cargadas",
        "El sistema no almacena",
        "consolidado ACTAS",
        "Resultados del indicador",
        "aplicativo",
        "no se registran en las fuentes",
    ):
        assert prohibido not in text

    indicators = document.tables[1]
    # Educación Superior: 2 certificados (enero y marzo).
    assert [cell.text for cell in indicators.rows[1].cells[1:]] == [
        "100",
        "2",
        "98",
        "2",
    ]
    # Complementaria: 10 + 20 + 30 + 40 = 100 (no incluye jul/sep/oct).
    assert [cell.text for cell in indicators.rows[10].cells[1:]] == [
        "1.000",
        "100",
        "900",
        "10",
    ]
    # Total FPI = 4 personas + 100 complementaria.
    assert [cell.text for cell in indicators.rows[12].cells[1:]] == [
        "1.350",
        "104",
        "1.246",
        "7,7",
    ]

    # Consistencia numérica entre tabla y narrativa.
    assert "equivale al 2%" in text
    assert "ejecución del 10%" in text
    assert "ejecución del 7,7%" in text
    assert "avance del 7,7%" in text
    # Se conserva el listado de anexos, pero no las evidencias del T2 de ejemplo.
    assert "ANEXO 15." in text
    assert "ANEXO 2. Aunque" not in text
    # La firma cierra el documento; no queda una página en blanco al final.
    assert document.paragraphs[-1].text == "Coordinador de Administración Educativa"


def test_docx_t3_acumulado_conserva_comportamiento_historico(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    response = client.get("/api/informes/word")
    assert response.status_code == 200, response.text

    document = Document(BytesIO(response.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Presentar la gestión realizada" in text
    assert "30 de septiembre de 2026" in text
    assert "Trimestre III de 2026" in text
    assert "¿Cómo fue la gestión en el periodo III" in text

    indicators = document.tables[1]
    assert [cell.text for cell in indicators.rows[10].cells[1:]] == [
        "1.000",
        "210",
        "790",
        "21",
    ]


def test_docx_t3_solo_trimestre_conserva_estructura_institucional(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    response = client.get("/api/informes/word?trimestre=T3&modo=solo_trimestre")
    assert response.status_code == 200, response.text

    document = Document(BytesIO(response.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Presentar la gestión realizada" in text
    assert "Trimestre III de 2026" in text
    assert "30 de septiembre de 2026" in text
    assert "¿Cómo fue la gestión en el periodo III" in text
    assert "Dependencia de las actas de certificación" in text
    assert "SOFIA Plus" in text
    for prohibido in (
        "registrados en el sistema",
        "fuentes institucionales cargadas",
        "El sistema no almacena",
        "consolidado ACTAS",
        "Resultados del indicador",
        "aplicativo",
    ):
        assert prohibido not in text

    indicators = document.tables[1]
    assert [cell.text for cell in indicators.rows[10].cells[1:]] == [
        "1.000",
        "110",
        "890",
        "11",
    ]
    assert [cell.text for cell in indicators.rows[12].cells[1:]] == [
        "1.350",
        "112",
        "1.238",
        "8,3",
    ]
    assert "ejecución del 11%" in text
    assert "ejecución del 8,3%" in text


def test_regla_semaforizacion_usa_prorrateo_del_periodo():
    from app.services.report_word import _lectura_avance

    assert _lectura_avance(50, 50) == ("buena", "verde")
    assert _lectura_avance(49.9, 50) == ("baja", "rojo")
    assert _lectura_avance(25, 25) == ("buena", "verde")
    assert _lectura_avance(24.9, 25) == ("baja", "rojo")
    assert _lectura_avance(None, 50) == ("sin información", "sin semaforización")
