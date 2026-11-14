"""Estrategias del Informe de Gestión por año/trimestre y su inserción DOCX.

Cubre:
* persistencia única por ``(año, trimestre)`` y aislamiento entre periodos;
* HTML restringido (negrita, cursiva y listas) con saneado en guardado/lectura;
* API REST mínima (GET/PUT/listado de periodos);
* inserción de los textos en 3.1.x y 3.2 sin heredar la negrita del rótulo;
* runs con negrita/cursiva y listas con sangría en el DOCX;
* placeholder institucional cuando la sección está vacía;
* idempotencia al regenerar el mismo periodo;
* regresión de indicadores T3 acumulado y un periodo adicional T3 solo
  trimestre sobre el fixture de 30 registros.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from app.models import InformeGestionEstrategia
from app.services.imports import confirm_import, stage_file
from app.services.indicadores import compute_indicadores_2026
from app.services.informe_gestion_estrategias import (
    get_estrategias,
    list_periodos,
    save_estrategias,
)
from app.services.rich_text import sanitize_estrategia_html
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

PLACEHOLDER_ESTRATEGIAS = "Pendiente de registro por la dependencia."

# Marcadores inequívocos por sección y periodo. Se usan para comprobar que el
# DOCX inserta los textos de la BD en el periodo correcto y sin duplicarlos.
MARCADORES_T3 = {
    "3.1.1": "[[ESTRATEGIA_SUPERIOR_T3]]",
    "3.1.2": "[[ESTRATEGIA_TECNICA_T3]]",
    "3.1.3": "[[ESTRATEGIA_ARTICULACION_T3]]",
    "3.1.4": "[[ESTRATEGIA_COMPLEMENTARIA_T3]]",
    "3.1.5": "[[ESTRATEGIA_CERTIFICACION_TOTAL_T3]]",
    "3.2": "[[ESTRATEGIA_OTRAS_ACTIVIDADES_T3]]",
}

MARCADORES_T2 = {
    "3.1.1": "[[ESTRATEGIA_SUPERIOR_T2]]",
    "3.1.2": "[[ESTRATEGIA_TECNICA_T2]]",
    "3.1.3": "[[ESTRATEGIA_ARTICULACION_T2]]",
    "3.1.4": "[[ESTRATEGIA_COMPLEMENTARIA_T2]]",
    "3.1.5": "[[ESTRATEGIA_CERTIFICACION_TOTAL_T2]]",
    "3.2": "[[ESTRATEGIA_OTRAS_ACTIVIDADES_T2]]",
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


def _run_con_formato(content: bytes, fragment: str, *, bold=None, italic=None):
    document = Document(BytesIO(content))
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            if fragment not in run.text:
                continue
            if bold is not None and run.bold is not bold:
                continue
            if italic is not None and run.italic is not italic:
                continue
            return paragraph, run
    raise AssertionError(
        f"No se encontró un run con {fragment!r} "
        f"(bold={bold!r}, italic={italic!r}) en el DOCX."
    )


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


def test_guardar_y_recuperar_estrategias_con_formato(session_factory):
    """El HTML allowlist (negrita + lista) sobrevive a guardar y recuperar."""
    html = (
        "<p>Actividades <strong>prioritarias</strong> del periodo</p>"
        "<ul><li>Primer ítem</li><li>Segundo ítem</li></ul>"
    )
    with session_factory() as session:
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={"3.1.1": html},
        )
        recuperado = get_estrategias(session, anio=2026, trimestre="T3")

    valor = recuperado["secciones"]["3.1.1"]
    assert valor == html
    assert "<strong>prioritarias</strong>" in valor
    assert valor.count("<li>") == 2


def test_sanitiza_html_de_estrategias_en_guardado_y_lectura(client):
    """Se elimina lo ejecutable y se conserva solo el formato permitido."""
    payload = (
        '<p onclick="alert(1)">Hola <strong>mundo</strong>'
        "<script>alert(2)</script></p>"
        '<iframe src="https://example.com"></iframe>'
        '<span style="color:red">texto</span>'
    )
    saved = client.put(
        "/api/informes/estrategias",
        json={"anio": 2026, "trimestre": "T3", "secciones": {"3.1.1": payload}},
    )
    assert saved.status_code == 200, saved.text
    valor = saved.json()["secciones"]["3.1.1"]

    assert "<script" not in valor
    assert "<iframe" not in valor
    assert "onclick" not in valor
    assert "style=" not in valor
    assert "alert(2)" not in valor
    assert "<p>Hola <strong>mundo</strong></p>" in valor
    assert "texto" in valor

    loaded = client.get(
        "/api/informes/estrategias", params={"anio": 2026, "trimestre": "T3"}
    )
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["secciones"]["3.1.1"] == valor


def test_sanitizador_normaliza_etiquetas_y_conserva_texto_plano():
    assert (
        sanitize_estrategia_html("<b>uno</b> <i>dos</i>")
        == "<strong>uno</strong> <em>dos</em>"
    )
    assert sanitize_estrategia_html("<div>párrafo</div>") == "<p>párrafo</p>"
    # Texto histórico sin etiquetas: no se altera (incluye comparaciones < 5).
    assert sanitize_estrategia_html("Legado con < 5 casos") == "Legado con < 5 casos"
    # Idempotencia del saneado.
    saneado = sanitize_estrategia_html("<p><strong>x</strong></p>")
    assert sanitize_estrategia_html(saneado) == saneado


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


def test_docx_sin_estrategias_usa_placeholder(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    response = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    assert response.status_code == 200, response.text
    text = _texto_docx(response.content)
    assert text.count(PLACEHOLDER_ESTRATEGIAS) == 6


def test_docx_convierte_negrita_cursiva_y_listas_de_estrategias(client):
    """El HTML guardado se traduce a runs/párrafos, no a marcado visible."""
    with client.session_factory() as session:
        _seed_periodo(session)

    secciones = {
        "3.1.1": (
            "<p>Introducción <strong>[[NEGRITA_T3]]</strong> del periodo.</p>"
            "<ul><li>[[VINETA_T3]] primera acción</li>"
            "<li>Segunda acción</li></ul>"
        ),
        "3.1.2": (
            "<ol><li>[[NUMERADA_T3]] primera acción</li>"
            "<li>Segunda acción</li></ol>"
        ),
        "3.1.3": "Texto plano de articulación.",
        "3.1.4": "<p><em>[[CURSIVA_T3]]</em> jornada de inscripción.</p>",
        "3.1.5": "Texto plano de certificación total.",
        "3.2": "<p>[[OTRAS_T3]] actividades adicionales.</p>",
    }
    saved = client.put(
        "/api/informes/estrategias",
        json={"anio": 2026, "trimestre": "T3", "secciones": secciones},
    )
    assert saved.status_code == 200, saved.text

    response = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    assert response.status_code == 200, response.text
    contenido = response.content
    texto = _texto_docx(contenido)

    # Negrita y cursiva reales en los runs.
    _, run_negrita = _run_con_formato(contenido, "[[NEGRITA_T3]]", bold=True)
    assert run_negrita.bold is True
    _, run_cursiva = _run_con_formato(contenido, "[[CURSIVA_T3]]", italic=True)
    assert run_cursiva.italic is True

    # Viñeta con sangría francesa y numeración legible.
    parrafo_vineta = _parrafo_con_fragmento(contenido, "[[VINETA_T3]]")
    assert parrafo_vineta.text.startswith("• [[VINETA_T3]]")
    assert parrafo_vineta.paragraph_format.left_indent is not None
    assert parrafo_vineta.paragraph_format.first_line_indent is not None
    assert int(parrafo_vineta.paragraph_format.first_line_indent) < 0

    parrafo_numerada = _parrafo_con_fragmento(contenido, "[[NUMERADA_T3]]")
    assert parrafo_numerada.text.startswith("1. [[NUMERADA_T3]]")

    # Nunca se vuelca el HTML como texto visible.
    for etiqueta in ("<p>", "<strong>", "<ul>", "<li>", "<em>", "<ol>"):
        assert etiqueta not in texto

    # El cuerpo de una estrategia sin marcas no hereda negrita ni cursiva.
    parrafo_plano = _parrafo_con_fragmento(contenido, "Texto plano de articulación.")
    assert all(
        run.bold is not True and run.italic is not True
        for run in parrafo_plano.runs
        if run.text.strip()
    )


def test_docx_convierte_markdown_legado_en_formato_real(client):
    """Los textos históricos con ``**``/``*``/``***``/``1\\.`` se interpretan."""
    with client.session_factory() as session:
        _seed_periodo(session)

    secciones = {
        "3.1.1": (
            "Prue**bfsgs** jjs*sss* ***hshs***\n"
            "1\\. sss\n"
            "2. otra cosa"
        ),
        "3.1.2": "<p>Intro **fuerte**<br>• viñeta uno<br>• viñeta dos</p>",
        "3.1.3": "<p>**negrita** y 1\\. escape</p>",
        "3.1.4": "Texto plano sin marcas.",
        "3.1.5": "Otro texto plano.",
        "3.2": "<p>Otras actividades.</p>",
    }
    saved = client.put(
        "/api/informes/estrategias",
        json={"anio": 2026, "trimestre": "T3", "secciones": secciones},
    )
    assert saved.status_code == 200, saved.text

    response = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    assert response.status_code == 200, response.text
    contenido = response.content
    texto = _texto_docx(contenido)

    # Ningún marcador de Markdown queda visible en el Word.
    assert "**" not in texto
    assert "***" not in texto
    assert "1\\." not in texto
    for fragmento in ("Prue", "bfsgs", "jjs", "sss", "hshs"):
        assert fragmento in texto

    # Negrita, cursiva y ambas en runs reales, sin los asteriscos.
    _, run_negrita = _run_con_formato(contenido, "bfsgs", bold=True)
    assert run_negrita.text == "bfsgs"
    _, run_cursiva = _run_con_formato(contenido, "sss", italic=True)
    assert run_cursiva.text == "sss"
    _, run_ambas = _run_con_formato(contenido, "hshs", bold=True, italic=True)
    assert run_ambas.text == "hshs"

    # La numeración escrita como texto se convierte en ítems independientes.
    assert (
        _parrafo_con_fragmento(contenido, "1. sss").text.strip() == "1. sss"
    )
    assert (
        _parrafo_con_fragmento(contenido, "2. otra cosa").text.strip()
        == "2. otra cosa"
    )

    # Las viñetas dentro de un párrafo con ``<br>`` también se separan.
    assert (
        _parrafo_con_fragmento(contenido, "• viñeta uno").text.strip()
        == "• viñeta uno"
    )
    assert (
        _parrafo_con_fragmento(contenido, "• viñeta dos").text.strip()
        == "• viñeta dos"
    )


def test_docx_estrategia_con_solo_marcado_usa_placeholder(client):
    """Un editor vacío puede guardar ``<p><br></p>``; el DOCX usa placeholder."""
    with client.session_factory() as session:
        _seed_periodo(session)
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={"3.1.1": "<p><br></p>"},
        )

    response = client.get("/api/informes/word?trimestre=T3&modo=acumulado")
    assert response.status_code == 200, response.text
    assert _texto_docx(response.content).count(PLACEHOLDER_ESTRATEGIAS) == 6


def test_t2_no_devuelve_ni_exporta_textos_de_t3(client):
    """El periodo es una clave estricta: T2 no hereda nada de T3."""
    with client.session_factory() as session:
        _seed_periodo(session)
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones=MARCADORES_T3,
        )

    t2 = client.get(
        "/api/informes/estrategias", params={"anio": 2026, "trimestre": "T2"}
    )
    assert t2.status_code == 200, t2.text
    cuerpo_t2 = "\n".join(t2.json()["secciones"].values())
    assert t2.json()["existe"] is False
    for marcador in MARCADORES_T3.values():
        assert marcador not in cuerpo_t2

    docx_t2 = client.get("/api/informes/word?trimestre=T2&modo=acumulado")
    assert docx_t2.status_code == 200, docx_t2.text
    texto_t2 = _texto_docx(docx_t2.content)
    for marcador in MARCADORES_T3.values():
        assert marcador not in texto_t2
    assert texto_t2.count(PLACEHOLDER_ESTRATEGIAS) == 6


@pytest.mark.parametrize(
    ("trimestre", "marcadores"),
    [
        ("T3", MARCADORES_T3),
        ("T2", MARCADORES_T2),
    ],
    ids=["t3-acumulado", "t2-acumulado"],
)
def test_docx_incluye_estrategias_guardadas(
    client, trimestre, marcadores
):
    """El DOCX lee de BD el periodo seleccionado, sin depender de la UI.

    El guardado se hace directamente en la base de datos y la exportación se
    pide por API, sin visitar la pestaña Estrategias ni un GET previo.
    """
    with client.session_factory() as session:
        _seed_periodo(session)
        save_estrategias(
            session,
            anio=2026,
            trimestre=trimestre,
            secciones=marcadores,
        )

    response = client.get(
        f"/api/informes/word?trimestre={trimestre}&modo=acumulado"
    )
    assert response.status_code == 200, response.text
    contenido = response.content
    texto = _texto_docx(contenido)

    for marcador in marcadores.values():
        assert texto.count(marcador) == 1, marcador
        assert marcador in _parrafo_con_fragmento(contenido, marcador).text
    assert PLACEHOLDER_ESTRATEGIAS not in texto


def test_generar_docx_lee_estrategias_desde_persistencia(client):
    """Cubre el bug: Exportar no depende del estado de sesión de la UI.

    Se guarda por servicio, sin GET ni pestaña Estrategias, y se piden ambas
    rutas DOCX (la de la pestaña Exportar y la del modal de informes).
    """
    with client.session_factory() as session:
        _seed_periodo(session)
        save_estrategias(
            session, anio=2026, trimestre="T3", secciones=MARCADORES_T3
        )

    word = client.get(
        "/api/informes/word",
        params={"anio": 2026, "trimestre": "T3", "modo": "acumulado"},
    )
    export = client.get(
        "/api/informes/export",
        params={
            "type": "consolidado",
            "format": "docx",
            "anio": 2026,
            "trimestre": "T3",
            "modo": "acumulado",
        },
    )

    for response in (word, export):
        assert response.status_code == 200, response.text
        texto = _texto_docx(response.content)
        for marcador in MARCADORES_T3.values():
            assert texto.count(marcador) == 1, marcador


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


def test_ui_rediseno_incluye_acordeones_y_borradores_rapidos():
    root = Path(__file__).resolve().parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    ui_js = (root / "app" / "static" / "ui-enhancements.js").read_text(
        encoding="utf-8"
    )

    # Los seis bloques se presentan como acordeones contraídos por defecto.
    assert index.count("data-accordion-toggle") == 6
    assert index.count('aria-expanded="false"') >= 6
    assert index.count('class="informe-accordion-panel"') == 6
    # Un borrador rápido por sección, separado de los seis editores persistidos.
    assert index.count("data-estrategia-quick=") == 6
    assert index.count("data-estrategia-seccion=") == 6
    assert index.count('contenteditable="true"') == 6
    assert '<textarea id="estrategia' not in index
    assert "Redactar estrategia aquí..." in index
    # El icono informativo se retiró; el borrador rápido se oculta al expandir.
    assert "informe-info-icon" not in index
    assert ".informe-accordion.is-open .informe-quick-input" in css
    assert "display: none;" in css
    # El comportamiento vive en el JS: abrir/cerrar, sincronizar borrador y badge.
    assert "function alternarAcordeon(button)" in ui_js
    assert 'button.setAttribute("aria-expanded", String(!abierto));' in ui_js
    assert "function sincronizarBorradoresRapidos(secciones)" in ui_js
    assert 'informeBadge.textContent = dirty ? "SIN GUARDAR" : "GUARDADO";' in ui_js


def test_ui_editor_restringido_con_negrita_cursiva_y_listas():
    """Cada sección expone un editor contenteditable con barra compacta."""
    root = Path(__file__).resolve().parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    ui_js = (root / "app" / "static" / "ui-enhancements.js").read_text(
        encoding="utf-8"
    )

    assert index.count("informe-editor-toolbar") == 6
    for comando in (
        "bold",
        "italic",
        "insertUnorderedList",
        "insertOrderedList",
        "undo",
        "redo",
    ):
        assert f'data-editor-command="{comando}"' in index
    assert index.count("data-placeholder=") >= 6
    # No hay controles de color, tablas ni imágenes en la v1.
    assert "contenteditable" in index
    assert "execCommand" not in index

    # El editor usa contenteditable controlado, sin dependencias nuevas.
    assert "function normalizarHtmlEstrategia(value)" in ui_js
    assert "function textoPlanoEstrategia(value)" in ui_js
    assert 'document.execCommand("styleWithCSS", false, false);' in ui_js
    assert 'editor.addEventListener("paste"' in ui_js
    assert 'getData("text/plain")' in ui_js
    # El pegado conserva el formato de Word mediante text/html saneado.
    assert 'getData("text/html")' in ui_js
    assert "function htmlParaPegadoEstrategia(value)" in ui_js
    assert "function textoPlanoAHtmlEstrategia(texto)" in ui_js
    assert 'document.execCommand("insertHTML", false, htmlSeguro);' in ui_js
    assert "secciones[editor.dataset.estrategiaSeccion] = normalizarHtmlEstrategia(" in ui_js

    for selector in (
        ".informe-editor",
        ".informe-editor-toolbar",
        ".informe-editor-button",
        ".informe-editor-button.is-active",
        ".informe-editor-area",
        ".informe-editor-area.is-empty::before",
    ):
        assert selector in css


def test_ui_contexto_estadistico_usa_el_consolidado_por_seccion():
    root = Path(__file__).resolve().parents[1]
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    ui_js = (root / "app" / "static" / "ui-enhancements.js").read_text(
        encoding="utf-8"
    )

    # Contexto por bloque: 3.1.1 a 3.1.5; 3.2 queda como sección informativa.
    assert index.count("data-context-section=") == 5
    assert index.count("data-context-badge") == 5
    assert "Contexto de Certificación" in index
    assert "Meta Anual" in index
    assert "Ejecución" in index
    assert "informe-progress-bar" in index

    # Mapeo explícito a las categorías del dataset consolidado.
    assert '"3.1.1": "superior"' in ui_js
    assert '"3.1.2": "tecnica"' in ui_js
    assert '"3.1.3": "articulacion"' in ui_js
    assert '"3.1.4": "complementaria"' in ui_js
    assert 'renderContextoSeccion("3.1.5"' in ui_js
    assert "/api/informes/consolidado" in ui_js
    assert "async function cargarContextoInforme()" in ui_js
    # El modo de exportación cambia las cifras y debe recargar el contexto.
    assert "informeExportMode?.addEventListener(\"change\"" in ui_js
    assert "function severidadContexto(avance, esperado = null)" in ui_js


def test_ui_rediseno_conserva_estilos_principales():
    root = Path(__file__).resolve().parents[1]
    css = (root / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    for selector in (
        ".informe-gestion-view",
        ".informe-hero",
        ".informe-banner",
        ".informe-accordion",
        ".informe-quick-input",
        ".informe-context-card",
        ".informe-severity.is-critical",
        ".informe-progress-bar",
        ".informe-estrategia-field",
        ".informe-editor",
        ".informe-editor-toolbar",
        ".informe-editor-area",
        ".informe-save-button",
    ):
        assert selector in css

    assert ".informe-info-icon" not in css


def test_ui_periodo_compartido_confirma_antes_de_cambiar():
    """Año/trimestre es único para Estrategias, Anexos y Exportar.

    Al cambiarlo se recargan las estrategias del nuevo periodo y, si hay
    cambios sin guardar, se confirma antes de abandonar el periodo actual.
    """
    root = Path(__file__).resolve().parents[1]
    ui_js = (root / "app" / "static" / "ui-enhancements.js").read_text(
        encoding="utf-8"
    )

    assert "window.confirm" in ui_js
    assert "Se guardarán antes de cambiar de periodo" in ui_js
    assert "function restaurarPeriodoInforme(periodo)" in ui_js
    assert "function mismoPeriodo(primero, segundo)" in ui_js
    assert "await cargarEstrategias();" in ui_js
    # Entrar en Exportar refresca el resumen sin pisar borradores.
    assert 'if (nombre === "exportar" && !informeDirty)' in ui_js
    # Cambiar periodo recarga estrategias y el contexto numérico del corte.
    assert "function cargarContextoInforme()" in ui_js
    assert "cargarContextoInforme();" in ui_js
    # El DOCX se pide por periodo y el servidor lee las estrategias de la BD.
    assert 'trimestre: periodo.trimestre' in ui_js
    assert "/api/informes/word" in ui_js
    # Semáforo alineado con el prorrateo del informe (25 % por trimestre).
    assert "function prorrateoEsperado(trimestre, modo)" in ui_js
    assert "return 25 * Math.min(4, Math.max(1, ordinal || 3));" in ui_js
    assert "severidadContexto(avance, esperado)" in ui_js


def test_ui_router_no_degrada_informe_gestion_a_carga():
    """Regresión: ui-enhancements envuelve showView y debe conocer la vista.

    Si su lista blanca no incluye ``informe-gestion``, el clic en el menú
    termina mostrando la vista de carga.
    """
    root = Path(__file__).resolve().parents[1]
    ui_js = (root / "app" / "static" / "ui-enhancements.js").read_text(
        encoding="utf-8"
    )

    wrapper_start = ui_js.index("window.showView = function (viewName, updateHash)")
    wrapper_end = ui_js.index("/* ---------------- Boot ---------------- */", wrapper_start)
    wrapper = ui_js[wrapper_start:wrapper_end]
    assert '"informe-gestion"' in wrapper
    assert 'originalShowView(target, updateHash)' in wrapper
    # También debe respetarse al entrar directo con #informe-gestion.
    boot = ui_js[wrapper_end:]
    assert '"informe-gestion"' in boot
