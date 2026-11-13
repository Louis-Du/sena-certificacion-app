"""Estrategias del Informe de Gestión por año/trimestre y su inserción DOCX.

Cubre:
* persistencia única por ``(año, trimestre)`` y aislamiento entre periodos;
* API REST mínima (GET/PUT/listado de periodos);
* inserción de los textos en 3.1.x y 3.2 sin heredar la negrita del rótulo;
* placeholder institucional cuando la sección está vacía;
* idempotencia al regenerar el mismo periodo;
* regresión de indicadores T3 acumulado y un periodo adicional T3 solo
  trimestre sobre el fixture de 30 registros.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document

from app.models import InformeGestionEstrategia
from app.services.imports import confirm_import, stage_file
from app.services.indicadores import compute_indicadores_2026
from app.services.informe_gestion_estrategias import (
    get_estrategias,
    list_periodos,
    save_estrategias,
)
from tests.test_informes_trimestres import _seed_periodo

FIXTURE_30 = (
    Path(__file__).resolve().parents[1]
    / "archivos_prueba"
    / "correctos"
    / "ACTAS_2026_30_REGISTROS_completo.xlsx"
)

SECCIONES_EJEMPLO = {
    "3.1.1": "Estrategia T3 de Educación Superior: acompañamiento a coordinaciones.",
    "3.1.2": "Estrategia T3 de Técnico Laboral: revisión semanal de actas.",
    "3.1.3": "Estrategia T3 de Articulación: mesas con instituciones educativas.",
    "3.1.4": "Estrategia T3 de Complementaria: jornadas de inscripción.",
    "3.1.5": "Estrategia T3 de Certificación Total: seguimiento a actas.",
    "3.2": "Otras actividades T3: inducción de aprendices y atención al usuario.",
}


def _texto_docx(content: bytes) -> str:
    document = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _parrafo_con_fragmento(content: bytes, fragment: str):
    document = Document(BytesIO(content))
    for paragraph in document.paragraphs:
        if fragment in paragraph.text:
            return paragraph
    raise AssertionError(f"No se encontró el fragmento {fragment!r} en el DOCX.")


def _metricas(data: dict) -> dict[str, dict]:
    return {metrica["category"]: metrica for metrica in data["metricas"]}


def _importar_fixture_30(session) -> None:
    staged = stage_file(FIXTURE_30.name, FIXTURE_30.read_bytes(), "actas_completo")
    confirm_import(staged.validation_id, session)


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def test_guardar_y_recuperar_estrategias_por_periodo(session_factory):
    with session_factory() as session:
        guardado = save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={"3.1.1": "Texto T3 superior", "3.2": "Otras T3"},
        )
        recuperado = get_estrategias(session, anio=2026, trimestre="T3")
        otro_trimestre = get_estrategias(session, anio=2026, trimestre="T2")
        otro_anio = get_estrategias(session, anio=2025, trimestre="T3")

        assert guardado["existe"] is True
        assert guardado["anio"] == 2026
        assert guardado["trimestre"] == "T3"
        assert recuperado["secciones"]["3.1.1"] == "Texto T3 superior"
        assert recuperado["secciones"]["3.2"] == "Otras T3"
        # Las secciones no enviadas quedan vacías, no se mezclan con otro periodo.
        assert recuperado["secciones"]["3.1.4"] == ""
        assert otro_trimestre["existe"] is False
        assert otro_trimestre["secciones"]["3.1.1"] == ""
        assert otro_anio["existe"] is False
        assert session.query(InformeGestionEstrategia).count() == 1


def test_actualizar_periodo_no_duplica_y_lista_periodos(session_factory):
    with session_factory() as session:
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={"3.1.1": "Versión 1"},
        )
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={"3.1.1": "Versión 2"},
        )
        save_estrategias(
            session,
            anio=2026,
            trimestre="T2",
            secciones={"3.1.1": "Texto T2"},
        )

        assert session.query(InformeGestionEstrategia).count() == 2
        assert get_estrategias(session, anio=2026, trimestre="T3")["secciones"][
            "3.1.1"
        ] == "Versión 2"
        periodos = list_periodos(session, anio=2026)
        assert [(item["trimestre"], item["anio"]) for item in periodos] == [
            ("T2", 2026),
            ("T3", 2026),
        ]


def test_api_put_get_y_listado_de_estrategias(client):
    payload = {
        "anio": 2026,
        "trimestre": "T3",
        "secciones": {
            "3.1.1": "Texto API superior",
            "3.2": "Otras actividades API",
        },
    }
    saved = client.put("/api/informes/estrategias", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["secciones"]["3.1.1"] == "Texto API superior"

    loaded = client.get(
        "/api/informes/estrategias", params={"anio": 2026, "trimestre": "T3"}
    )
    assert loaded.status_code == 200, loaded.text
    data = loaded.json()
    assert data["existe"] is True
    assert data["secciones"]["3.1.1"] == "Texto API superior"
    assert data["secciones"]["3.2"] == "Otras actividades API"

    empty = client.get(
        "/api/informes/estrategias", params={"anio": 2026, "trimestre": "T4"}
    )
    assert empty.status_code == 200
    assert empty.json()["existe"] is False
    assert empty.json()["secciones"]["3.1.1"] == ""

    periods = client.get("/api/informes/estrategias/periodos", params={"anio": 2026})
    assert periods.status_code == 200
    assert len(periods.json()) == 1
    assert periods.json()[0]["anio"] == 2026
    assert periods.json()[0]["trimestre"] == "T3"
    assert periods.json()[0]["actualizado_en"]


def test_api_rechaza_trimestre_o_seccion_invalidos(client):
    bad_trimestre = client.get(
        "/api/informes/estrategias", params={"anio": 2026, "trimestre": "T5"}
    )
    assert bad_trimestre.status_code == 400
    assert "Trimestre" in bad_trimestre.json()["detail"]

    bad_seccion = client.put(
        "/api/informes/estrategias",
        json={"anio": 2026, "trimestre": "T3", "secciones": {"3.9": "No existe"}},
    )
    assert bad_seccion.status_code == 400
    assert "3.9" in bad_seccion.json()["detail"]


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def test_docx_inserta_estrategias_guardadas_y_usa_placeholder_si_faltan(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    # 3.1.4 y 3.1.5 quedan vacías a propósito para validar el placeholder.
    secciones = {
        "3.1.1": "Texto único 3.1.1 para el informe T3.",
        "3.1.2": "Texto único 3.1.2 para el informe T3.",
        "3.1.3": "Texto único 3.1.3 para el informe T3.",
        "3.2": "Texto único 3.2 para las otras actividades del T3.",
    }
    saved = client.put(
        "/api/informes/estrategias",
        json={"anio": 2026, "trimestre": "T3", "secciones": secciones},
    )
    assert saved.status_code == 200, saved.text

    response = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    assert response.status_code == 200, response.text
    text = _texto_docx(response.content)

    for expected in secciones.values():
        assert expected in text

    # Sección vacía => placeholder institucional, sin inventar actividades.
    assert "Pendiente de registro por la dependencia." in text
    assert text.count("Pendiente de registro por la dependencia.") == 2

    # El cuerpo insertado no hereda la negrita del rótulo.
    for fragment in secciones.values():
        paragraph = _parrafo_con_fragmento(response.content, fragment)
        runs = [run for run in paragraph.runs if fragment in run.text]
        assert runs, fragment
        assert all(run.bold is not True for run in runs), fragment
        assert all(run.italic is not True for run in runs), fragment

    # Las cifras siguen calculándose igual con estrategias guardadas.
    document = Document(BytesIO(response.content))
    indicators = document.tables[1]
    assert [cell.text for cell in indicators.rows[10].cells[1:]] == [
        "1.000",
        "210",
        "790",
        "21",
    ]


def test_docx_sin_estrategias_conserva_placeholder(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    response = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    assert response.status_code == 200, response.text
    text = _texto_docx(response.content)
    assert text.count("Pendiente de registro por la dependencia.") == 6


def test_docx_mismo_periodo_es_idempotente_y_el_modo_no_duplica_textos(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    client.put(
        "/api/informes/estrategias",
        json={
            "anio": 2026,
            "trimestre": "T3",
            "secciones": {"3.1.1": "Texto idempotente 3.1.1"},
        },
    )

    primera = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    segunda = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    solo_trimestre = client.get("/api/informes/word?trimestre=T3&modo=solo_trimestre")
    for response in (primera, segunda, solo_trimestre):
        assert response.status_code == 200, response.text
        text = _texto_docx(response.content)
        assert text.count("Texto idempotente 3.1.1") == 1

    with client.session_factory() as session:
        # El modo solo/acumulado no crea otro juego de textos.
        assert session.query(InformeGestionEstrategia).count() == 1


# ---------------------------------------------------------------------------
# Regresión de indicadores y periodo adicional
# ---------------------------------------------------------------------------
def test_fixture_30_t3_acumulado_mantiene_titulada_y_complementaria(session_factory):
    """Línea base del fixture: titulada 8/15/1/24 y complementaria 1479.

    Desglose complementaria T3 acumulado: presencial 474, virtual 550,
    campesena 210, fullpopular 245.
    """
    with session_factory() as session:
        _importar_fixture_30(session)
        data = compute_indicadores_2026(session, trimestre="T3", modo="acumulado")

    metricas = _metricas(data)
    assert [metricas[key]["certificados"] for key in (
        "superior",
        "tecnica",
        "articulacion",
    )] == [8, 15, 1]
    assert data["certificados_personas"] == 24
    assert data["complementaria_canales"] == {
        "presencial": 474,
        "virtual": 550,
        "campesena": 210,
        "fullpopular": 245,
        "otro": 0,
    }
    assert data["certificados_complementaria"] == 1479
    assert data["periodo_inicio"] == "2026-01-01"
    assert data["periodo_fin"] == "2026-09-30"


def test_fixture_30_t3_solo_trimestre_valores_documentados(session_factory):
    """Periodo adicional: T3 solo trimestre (julio-septiembre).

    Desglose sobre el mismo fixture de 30 registros:
    * titulada: superior 2, tecnica 4, articulacion 0, total 6;
    * complementaria: presencial 0, virtual 115, campesena 50,
      fullpopular 55, total 220;
    * por tanto total certificados del bloque = 6 + 220 = 226.

    Este caso protege que el filtro de meses no se aplique también a la meta
    anual ni arrastre certificados de enero-junio.
    """
    with session_factory() as session:
        _importar_fixture_30(session)
        data = compute_indicadores_2026(
            session, trimestre="T3", modo="solo_trimestre"
        )

    metricas = _metricas(data)
    assert data["periodo"] == "Julio - Septiembre 2026"
    assert data["periodo_inicio"] == "2026-07-01"
    assert data["periodo_fin"] == "2026-09-30"
    assert [metricas[key]["certificados"] for key in (
        "superior",
        "tecnica",
        "articulacion",
    )] == [2, 4, 0]
    assert data["certificados_personas"] == 6
    assert data["complementaria_canales"] == {
        "presencial": 0,
        "virtual": 115,
        "campesena": 50,
        "fullpopular": 55,
        "otro": 0,
    }
    assert data["certificados_complementaria"] == 220
    assert data["total_certificados"] == 226
    # La meta institucional es anual y no se prorratea en el cálculo.
    assert metricas["superior"]["meta"] == 943
    assert metricas["complementaria"]["meta"] == 83726


# ---------------------------------------------------------------------------
# Contrato estático de la UI
# ---------------------------------------------------------------------------
def test_ui_incluye_navegacion_y_pantalla_de_informe_gestion():
    root = Path(__file__).resolve().parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    ui_js = (root / "app" / "static" / "ui-enhancements.js").read_text(
        encoding="utf-8"
    )

    assert 'href="#informe-gestion"' in index
    assert 'data-view="informe-gestion"' in index
    assert 'id="informe-gestion-view"' in index
    assert 'id="informe-panel-estrategias"' in index
    assert 'id="informe-panel-anexos"' in index
    assert 'id="informe-panel-exportar"' in index
    assert index.count("data-estrategia-seccion=") == 6
    assert 'id="report-open-estrategias"' in index
    # La vista nueva debe sobrevivir al router y cargar sus datos.
    assert '"informe-gestion"' in app_js
    assert "/api/informes/estrategias" in ui_js
    assert "/api/informes/word" in ui_js
