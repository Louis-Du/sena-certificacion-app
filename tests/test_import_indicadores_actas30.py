"""Cobertura de importacion y agregacion T3 sobre el fixture de 30 registros.

El fixture ``ACTAS_2026_30_REGISTROS_completo.xlsx`` contiene una copia
reducida y controlada de ACTAS 2026 (30 certificados, 30 pendientes,
COMPLEMENTARIA y META) con las columnas que intervienen en los indicadores.
No se copia el ACTAS institucional completo.

Desglose real del fixture para T3 acumulado (2026-01-01 .. 2026-09-30):

* Titulada: superior 8, tecnica 15, articulacion 1, total 24.
* Complementaria: presencial 474, virtual 550, campesena 210,
  fullpopular 245, total 1479.
* Metas: superior 943, tecnica 1910, articulacion 1995,
  complementaria 83726, campesena 2126, fullpopular 2104.
* Pendientes del lote: 30 aprendices (los de la hoja PENDIENTES).

Las fechas de COMPLEMENTARIA son ``datetime`` reales (10 de abril y 10 de
julio). Deben conservarse en abril y julio; no pueden convertirse en octubre.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from docx import Document
from openpyxl import load_workbook

from app.models import ImportedRecord
from app.services.imports import confirm_import, stage_file
from app.services.indicadores import compute_indicadores_2026
from app.services.parsers import (
    _to_iso_date,
    parse_date_value,
    read_complementaria_records,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "archivos_prueba"
    / "correctos"
    / "ACTAS_2026_30_REGISTROS_completo.xlsx"
)


def _metricas(data: dict) -> dict[str, dict]:
    return {metrica["category"]: metrica for metrica in data["metricas"]}


def _importar(session, content: bytes) -> dict:
    staged = stage_file(FIXTURE.name, content, "actas_completo")
    return confirm_import(staged.validation_id, session)


def _copiar_fixture(tmp_path: Path, nombre: str, mutar) -> Path:
    libro = load_workbook(FIXTURE)
    mutar(libro)
    destino = tmp_path / nombre
    libro.save(destino)
    return destino


# ---------------------------------------------------------------------------
# A. Fechas de COMPLEMENTARIA
# ---------------------------------------------------------------------------
def test_datetime_abril_no_vvira_octubre():
    """Un datetime del 10 de abril se queda en abril, no pasa a octubre.

    En el fixture, campesena y fullpopular registran 10/04/2026. Si el lector
    intercambiara dia y mes, esos 60 y 40 certificados se contarian como 4 de
    octubre y quedarian fuera del T3.
    """
    registros = read_complementaria_records(FIXTURE.read_bytes())

    abril = {
        (registro["canal"], registro["cantidad"])
        for registro in registros
        if registro["fecha"] == "2026-04-10"
    }
    assert abril == {("campesena", 60), ("fullpopular", 40)}
    assert all(registro["fecha"] != "2026-10-04" for registro in registros)
    assert _to_iso_date(datetime(2026, 4, 10)) == "2026-04-10"


def test_datetime_julio_permanece_julio():
    """Un datetime del 10 de julio se queda en julio, no pasa a octubre."""
    registros = read_complementaria_records(FIXTURE.read_bytes())

    julio = {
        (registro["canal"], registro["cantidad"])
        for registro in registros
        if registro["fecha"] == "2026-07-10"
    }
    assert julio == {("campesena", 50), ("fullpopular", 55)}
    assert all(registro["fecha"] != "2026-10-07" for registro in registros)
    assert _to_iso_date(datetime(2026, 7, 10)) == "2026-07-10"


def test_texto_dd_mm_yyyy_colombia():
    """Los textos DD/MM/YYYY se leen con la convencion colombiana."""
    assert _to_iso_date("10/04/2026") == "2026-04-10"
    assert _to_iso_date("10/07/2026") == "2026-07-10"
    assert _to_iso_date("03/05/2026") == "2026-05-03"
    assert parse_date_value("10/04/2026") == "2026-04-10"
    assert parse_date_value("10/07/2026") == "2026-07-10"


# ---------------------------------------------------------------------------
# B. Importacion + indicadores T3 acumulado
# ---------------------------------------------------------------------------
def test_import_actas30_t3_acumulado_titulada(session_factory):
    """El lote importado agrega la titulada T3 en 8 / 15 / 1 / 24.

    Desglose del fixture: superior 8 (los demas tecnólogos son de octubre y
    noviembre), tecnica 15, articulacion 1.
    """
    with session_factory() as session:
        _importar(session, FIXTURE.read_bytes())
        data = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )

    metricas = _metricas(data)
    assert metricas["superior"]["certificados"] == 8
    assert metricas["tecnica"]["certificados"] == 15
    assert metricas["articulacion"]["certificados"] == 1
    assert data["certificados_personas"] == 24
    assert data["total_pendientes"] == 30
    assert data["periodo_inicio"] == "2026-01-01"
    assert data["periodo_fin"] == "2026-09-30"


def test_import_actas30_t3_acumulado_complementaria(session_factory):
    """La complementaria T3 conserva sus 4 canales y el total de 1479."""
    with session_factory() as session:
        _importar(session, FIXTURE.read_bytes())
        data = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )

    canales = data["complementaria_canales"]
    assert canales["presencial"] == 474
    assert canales["virtual"] == 550
    assert canales["campesena"] == 210
    assert canales["fullpopular"] == 245
    assert canales.get("otro", 0) == 0
    assert data["certificados_complementaria"] == 1479
    assert data["total_certificados"] == 24 + 1479
    assert _metricas(data)["complementaria"]["certificados"] == 1479


def test_metas_y_pendientes_por_cumplir(session_factory):
    """Brecha = meta anual - ejecucion, sin inventar metas ni pendientes."""
    with session_factory() as session:
        _importar(session, FIXTURE.read_bytes())
        data = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )

    metricas = _metricas(data)
    esperados = {
        "superior": (943, 8, 935),
        "tecnica": (1910, 15, 1895),
        "articulacion": (1995, 1, 1994),
        "complementaria": (83726, 1479, 82247),
    }
    for categoria, (meta, ejecucion, brecha) in esperados.items():
        metrica = metricas[categoria]
        assert metrica["meta"] == meta
        assert metrica["certificados"] == ejecucion
        assert metrica["brecha"] == brecha
        assert metrica["brecha"] == metrica["meta"] - metrica["certificados"]

    assert data["metas_canales"] == {"campesena": 2126, "fullpopular": 2104}
    # Pendientes del universo titulada: 25 superiores y 5 tecnicos.
    assert metricas["superior"]["pendientes"] == 25
    assert metricas["tecnica"]["pendientes"] == 5
    assert metricas["articulacion"]["pendientes"] == 0


# ---------------------------------------------------------------------------
# C. Escenarios adicionales
# ---------------------------------------------------------------------------
def test_octubre_no_entra_al_t3_pero_si_al_t4(session_factory, tmp_path):
    """Un tecnologo certificado en OCTUBRE no suma al T3 acumulado.

    Se agrega un certificado superior con mes OCTUBRE al fixture base. El T3
    debe seguir en 8 superiores y 24 titulada; el T4 acumulado sube de 10 a 11
    superiores porque incluye todo el ano.
    """
    def agregar_octubre(libro) -> None:
        libro["CERTIFICADOS"].append(
            [
                "TECNÓLOGO",
                "9999999999",
                "Persona Octubre",
                "Prueba",
                "9999999",
                "999999",
                "CERTIFICADOS",
                "OCTUBRE",
            ]
        )

    modificado = _copiar_fixture(
        tmp_path, "actas_30_registros_octubre.xlsx", agregar_octubre
    )

    with session_factory() as session:
        _importar(session, modificado.read_bytes())
        t3 = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )
        t4 = compute_indicadores_2026(
            session, trimestre="T4", modo="acumulado"
        )

    assert _metricas(t3)["superior"]["certificados"] == 8
    assert t3["certificados_personas"] == 24
    assert _metricas(t4)["superior"]["certificados"] == 11
    assert t4["certificados_personas"] == 31


def test_reimportar_fixture_no_duplica_indicadores(session_factory):
    """La segunda importacion actualiza el lote vigente sin duplicar cifras."""
    with session_factory() as session:
        primera = _importar(session, FIXTURE.read_bytes())
        antes = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )

        segunda = _importar(session, FIXTURE.read_bytes())
        despues = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )

        assert session.query(ImportedRecord).count() == 81

    assert primera["new_records"] == 81
    assert primera["updated_records"] == 0
    assert segunda["new_records"] == 0
    assert segunda["updated_records"] == 81

    campos = (
        "certificados_personas",
        "certificados_complementaria",
        "total_certificados",
        "total_pendientes",
        "complementaria_canales",
    )
    for campo in campos:
        assert despues[campo] == antes[campo], campo
    assert [
        (metrica["category"], metrica["certificados"], metrica["brecha"])
        for metrica in despues["metricas"]
    ] == [
        (metrica["category"], metrica["certificados"], metrica["brecha"])
        for metrica in antes["metricas"]
    ]


def test_meta_incompleta_sin_tecnico_no_falla(session_factory, tmp_path):
    """Sin meta de tecnica se informa No disponible, sin traceback."""
    def quitar_meta_tecnica(libro) -> None:
        libro["META"].cell(row=3, column=1).value = None

    modificado = _copiar_fixture(
        tmp_path, "actas_30_registros_sin_meta_tecnica.xlsx", quitar_meta_tecnica
    )

    with session_factory() as session:
        _importar(session, modificado.read_bytes())
        data = compute_indicadores_2026(
            session, trimestre="T3", modo="acumulado"
        )

    tecnica = _metricas(data)["tecnica"]
    assert tecnica["certificados"] == 15
    assert tecnica["meta"] is None
    assert tecnica["brecha"] is None
    assert tecnica["warning"] == (
        "Meta no disponible en las fuentes: no se puede calcular el avance."
    )
    assert any(
        "No se encontro la meta de: Técnica Laboral y Otros" in advertencia
        for advertencia in data["advertencias"]
    )


# ---------------------------------------------------------------------------
# D. DOCX (opcional): las cifras clave llegan al informe de gestion
# ---------------------------------------------------------------------------
def test_docx_informe_gestion_incluye_cifras_clave(client):
    """El Word T3 acumulado muestra 943/8/935 y la complementaria 1479."""
    with client.session_factory() as session:
        _importar(session, FIXTURE.read_bytes())

    response = client.get("/api/informes/word")
    assert response.status_code == 200, response.text

    document = Document(BytesIO(response.content))
    tabla = document.tables[1]
    # Fila 1: Educacion Superior (meta, ejecucion, brecha, avance).
    assert [celda.text for celda in tabla.rows[1].cells[1:]] == [
        "943",
        "8",
        "935",
        "0,8",
    ]
    # Fila 10: Complementaria (meta, ejecucion, brecha, avance).
    assert [celda.text for celda in tabla.rows[10].cells[1:]] == [
        "83.726",
        "1.479",
        "82.247",
        "1,8",
    ]
    texto = "\n".join(parrafo.text for parrafo in document.paragraphs)
    assert "30 de septiembre de 2026" in texto
