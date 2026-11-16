"""Anexos del Informe de Gestión: solo imágenes, multi-archivo y orden manual.

Cubre:
* validación de tipo (PDF/DOCX se rechazan con 400);
* alta de un anexo con varias imágenes;
* numeración automática ``ANEXO 1..N`` sin código ni orden manual;
* reordenamiento por lista de ids (drag-and-drop);
* añadir/eliminar imágenes y la regla de no dejar un anexo vacío;
* borrado del anexo con todos sus binarios;
* presencia de títulos, descripciones y **todas** las imágenes en §5 del DOCX;
* aislamiento entre trimestres y compatibilidad con filas heredadas PDF/DOCX.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

from app.models import InformeGestionAnexo, InformeGestionAnexoArchivo
from app.services.informe_gestion_anexos import storage_dir
from app.services.informe_gestion_estrategias import save_estrategias
from tests.test_informes_trimestres import _seed_periodo

# PNG 1x1 válido (firma PNG real, necesario para que python-docx lo inserte).
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PDF_MINIMO = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF\n"


def _docx_minimo(texto: str = "Anexo DOCX") -> bytes:
    document = Document()
    document.add_paragraph(texto)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


DOCX_MINIMO = _docx_minimo()


def _webp_bytes() -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (4, 4), (20, 120, 90)).save(buffer, format="WEBP")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def anexos_dir(tmp_path, monkeypatch):
    """Aísla los binarios: nunca se escribe en ``data/`` durante las pruebas."""
    destino = tmp_path / "anexos"
    monkeypatch.setenv("INFORME_ANEXOS_DIR", str(destino))
    return destino


def _texto_docx(content: bytes) -> str:
    document = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _crear_anexo(
    client,
    *,
    titulo: str = "Anexo de prueba",
    trimestre: str = "T3",
    anio: int = 2026,
    descripcion: str | None = None,
    archivos: list[tuple[str, bytes, str]] | None = None,
    extra: dict[str, str] | None = None,
):
    data = {
        "anio": str(anio),
        "trimestre": trimestre,
        "titulo": titulo,
    }
    if descripcion is not None:
        data["descripcion"] = descripcion
    if extra:
        data.update(extra)
    seleccion = archivos or [("captura.png", PNG_1X1, "image/png")]
    return client.post(
        "/api/informes/anexos",
        data=data,
        files=[("files", archivo) for archivo in seleccion],
    )


def _exportar(client, trimestre: str = "T3") -> bytes:
    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        return export_report_docx(
            session, anio=2026, trimestre=trimestre, modo="acumulado"
        )


# ---------------------------------------------------------------------------
# Alta, validación y aislamiento por periodo
# ---------------------------------------------------------------------------
def test_crear_anexo_con_varias_imagenes_y_listar_solo_en_su_trimestre(client):
    response = _crear_anexo(
        client,
        titulo="[[ANEXO_MULTI]]",
        descripcion="Capturas del trimestre.",
        archivos=[
            ("actas.png", PNG_1X1, "image/png"),
            ("resumen.png", PNG_1X1, "image/png"),
        ],
    )
    assert response.status_code == 201, response.text
    creado = response.json()
    assert creado["anio"] == 2026
    assert creado["trimestre"] == "T3"
    assert creado["titulo"] == "[[ANEXO_MULTI]]"
    assert creado["numero"] == 1
    assert creado["rotulo"] == "ANEXO 1"
    assert creado["total_archivos"] == 2
    assert len(creado["archivos"]) == 2
    assert [archivo["nombre_archivo"] for archivo in creado["archivos"]] == [
        "actas.png",
        "resumen.png",
    ]
    assert all(
        archivo["content_type"] == "image/png"
        for archivo in creado["archivos"]
    )
    assert all(
        archivo["download_url"].endswith("/download")
        for archivo in creado["archivos"]
    )
    assert creado["download_url"] == creado["archivos"][0]["download_url"]

    # El binario se guarda en disco, no en la base de datos.
    guardados = sorted(storage_dir().glob("2026-T3-*.png"))
    assert len(guardados) == 2
    assert all(archivo.read_bytes() == PNG_1X1 for archivo in guardados)

    t3 = client.get("/api/informes/anexos?anio=2026&trimestre=T3")
    assert t3.status_code == 200, t3.text
    assert t3.json()["total"] == 1
    item = t3.json()["items"][0]
    assert item["id"] == creado["id"]
    assert item["numero"] == 1
    assert item["rotulo"] == "ANEXO 1"
    assert item["titulo"] == "[[ANEXO_MULTI]]"

    t2 = client.get("/api/informes/anexos?anio=2026&trimestre=T2")
    assert t2.json() == {"anio": 2026, "trimestre": "T2", "total": 0, "items": []}


def test_orden_automatico_sin_codigo_ni_orden_manual(client):
    primero = _crear_anexo(client, titulo="Primero")
    # Aunque un cliente antiguo envíe los campos retirados, se ignoran.
    segundo = _crear_anexo(
        client,
        titulo="Segundo",
        extra={"codigo": "A-2", "orden": "9"},
    )
    assert primero.status_code == 201, primero.text
    assert segundo.status_code == 201, segundo.text

    assert primero.json()["orden"] == 1
    assert segundo.json()["orden"] == 2
    assert "codigo" not in primero.json()
    assert "codigo" not in segundo.json()
    assert segundo.json()["numero"] == 2
    assert segundo.json()["rotulo"] == "ANEXO 2"

    items = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["items"]
    assert [item["titulo"] for item in items] == ["Primero", "Segundo"]
    assert [item["numero"] for item in items] == [1, 2]
    assert [item["rotulo"] for item in items] == ["ANEXO 1", "ANEXO 2"]


def test_titulo_no_repite_el_prefijo_anexo(client):
    creado = _crear_anexo(
        client,
        titulo="ANEXO 1. Actas con aprendices por certificar",
    )
    assert creado.status_code == 201, creado.text
    payload = creado.json()
    assert payload["titulo"] == "Actas con aprendices por certificar"
    assert payload["numero"] == 1
    assert payload["rotulo"] == "ANEXO 1"


@pytest.mark.parametrize(
    ("nombre", "contenido", "content_type"),
    [
        ("soporte.pdf", PDF_MINIMO, "application/pdf"),
        (
            "soporte.docx",
            DOCX_MINIMO,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("notas.txt", b"texto plano", "text/plain"),
    ],
    ids=["pdf", "docx", "txt"],
)
def test_solo_se_aceptan_imagenes(client, nombre, contenido, content_type):
    response = _crear_anexo(
        client, archivos=[(nombre, contenido, content_type)]
    )
    assert response.status_code == 400, response.text
    assert "PNG" in response.json()["detail"]
    assert list(storage_dir().glob("*")) == []


def test_alta_sin_imagenes_es_invalida(client):
    response = client.post(
        "/api/informes/anexos",
        data={"anio": "2026", "trimestre": "T3", "titulo": "Sin soporte"},
    )
    assert response.status_code == 400, response.text
    assert "al menos una imagen" in response.json()["detail"]


def test_webp_se_acepta_y_se_inserta_en_el_docx(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    creado = _crear_anexo(
        client,
        titulo="[[ANEXO_WEBP]]",
        archivos=[("captura.webp", _webp_bytes(), "image/webp")],
    )
    assert creado.status_code == 201, creado.text
    assert creado.json()["archivos"][0]["content_type"] == "image/webp"

    document = Document(BytesIO(_exportar(client)))
    texto = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "[[ANEXO_WEBP]]" in texto
    # python-docx no lee WEBP: se convierte a PNG para no perder la imagen.
    assert len(document.inline_shapes) == 1


# ---------------------------------------------------------------------------
# Metadatos, imágenes y borrado
# ---------------------------------------------------------------------------
def test_actualizar_metadatos_sin_tocar_imagenes(client):
    creado = _crear_anexo(client, titulo="Título original").json()

    response = client.patch(
        f"/api/informes/anexos/{creado['id']}",
        data={
            "titulo": "Título editado",
            "descripcion": "Descripción editada",
            "codigo": "ANEXO 9",
            "orden": "7",
        },
    )
    assert response.status_code == 200, response.text
    actualizado = response.json()
    assert actualizado["titulo"] == "Título editado"
    assert actualizado["descripcion"] == "Descripción editada"
    assert actualizado["orden"] == 1  # el orden manual se ignora
    assert "codigo" not in actualizado
    assert actualizado["total_archivos"] == 1
    assert actualizado["archivos"][0]["id"] == creado["archivos"][0]["id"]

    catalogo = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()
    assert catalogo["items"][0]["titulo"] == "Título editado"
    assert catalogo["items"][0]["descripcion"] == "Descripción editada"


def test_agregar_imagenes_a_un_anexo_existente(client):
    creado = _crear_anexo(client, titulo="Crece").json()

    response = client.post(
        f"/api/informes/anexos/{creado['id']}/imagenes",
        files=[("files", ("nueva.png", PNG_1X1, "image/png"))],
    )
    assert response.status_code == 201, response.text
    actualizado = response.json()
    assert actualizado["total_archivos"] == 2
    assert [archivo["nombre_archivo"] for archivo in actualizado["archivos"]] == [
        "captura.png",
        "nueva.png",
    ]
    assert [archivo["orden"] for archivo in actualizado["archivos"]] == [0, 1]
    assert len(list(storage_dir().glob("2026-T3-*.png"))) == 2


def test_eliminar_imagen_concreta_y_proteger_la_ultima(client):
    creado = _crear_anexo(
        client,
        titulo="Dos imágenes",
        archivos=[
            ("uno.png", PNG_1X1, "image/png"),
            ("dos.png", PNG_1X1, "image/png"),
        ],
    ).json()
    archivos = creado["archivos"]
    assert len(list(storage_dir().glob("2026-T3-*.png"))) == 2

    response = client.delete(
        f"/api/informes/anexos/{creado['id']}/imagenes/{archivos[0]['id']}"
    )
    assert response.status_code == 200, response.text
    restante = response.json()
    assert restante["total_archivos"] == 1
    assert restante["archivos"][0]["nombre_archivo"] == "dos.png"
    assert len(list(storage_dir().glob("2026-T3-*.png"))) == 1

    ultima = client.delete(
        f"/api/informes/anexos/{creado['id']}/imagenes/{archivos[1]['id']}"
    )
    assert ultima.status_code == 400, ultima.text
    assert "última imagen" in ultima.json()["detail"]
    assert (
        client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["items"][0][
            "total_archivos"
        ]
        == 1
    )


def test_eliminar_anexo_borra_todas_sus_imagenes(client, session_factory):
    creado = _crear_anexo(
        client,
        titulo="Se va completo",
        archivos=[
            ("uno.png", PNG_1X1, "image/png"),
            ("dos.png", PNG_1X1, "image/png"),
        ],
    ).json()
    guardados = list(storage_dir().glob("2026-T3-*.png"))
    assert len(guardados) == 2

    response = client.delete(f"/api/informes/anexos/{creado['id']}")
    assert response.status_code == 204, response.text
    assert all(not archivo.exists() for archivo in guardados)

    with session_factory() as session:
        assert session.query(InformeGestionAnexo).count() == 0
        assert session.query(InformeGestionAnexoArchivo).count() == 0
    assert (
        client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["total"] == 0
    )
    assert client.delete(f"/api/informes/anexos/{creado['id']}").status_code == 404


def test_eliminar_anexo_no_falla_si_una_imagen_esta_bloqueada(
    client, session_factory, monkeypatch
):
    """Un archivo abierto en Windows no convierte el DELETE en un 500."""
    creado = _crear_anexo(client, titulo="Archivo bloqueado").json()
    archivo = next(storage_dir().glob("2026-T3-*.png"))
    original = Path.unlink

    def bloqueado(self, *args, **kwargs):
        if self == archivo:
            raise PermissionError("El archivo está en uso por otro proceso.")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", bloqueado)
    try:
        response = client.delete(f"/api/informes/anexos/{creado['id']}")
    finally:
        monkeypatch.setattr(Path, "unlink", original)

    assert response.status_code == 204, response.text
    with session_factory() as session:
        assert session.query(InformeGestionAnexo).count() == 0
    archivo.unlink(missing_ok=True)


def test_archivo_disponible_refleja_si_el_binario_sigue_en_disco(client):
    creado = _crear_anexo(client, titulo="Binario perdido").json()
    assert creado["archivo_disponible"] is True
    archivo = next(storage_dir().glob("2026-T3-*.png"))
    archivo.unlink()

    items = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["items"]
    assert items[0]["archivo_disponible"] is False
    assert items[0]["archivos"][0]["archivo_disponible"] is False


def test_descarga_de_una_imagen_concreta(client):
    creado = _crear_anexo(client, titulo="Descargable").json()
    archivo = creado["archivos"][0]

    descarga = client.get(
        f"/api/informes/anexos/{creado['id']}/archivos/{archivo['id']}/download"
    )
    assert descarga.status_code == 200, descarga.text
    assert descarga.content == PNG_1X1
    assert "captura.png" in descarga.headers.get("content-disposition", "")

    # El atajo del catálogo devuelve la primera imagen del anexo.
    primera = client.get(f"/api/informes/anexos/{creado['id']}/download")
    assert primera.status_code == 200, primera.text
    assert primera.content == PNG_1X1


# ---------------------------------------------------------------------------
# Reordenamiento
# ---------------------------------------------------------------------------
def test_reordenar_actualiza_numeros_y_el_docx(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    a = _crear_anexo(client, titulo="[[ANEXO_A]]").json()
    b = _crear_anexo(client, titulo="[[ANEXO_B]]").json()

    response = client.put(
        "/api/informes/anexos/orden",
        json={
            "anio": 2026,
            "trimestre": "T3",
            "anexo_ids": [b["id"], a["id"]],
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["id"] for item in items] == [b["id"], a["id"]]
    assert [item["numero"] for item in items] == [1, 2]
    assert [item["rotulo"] for item in items] == ["ANEXO 1", "ANEXO 2"]
    assert [item["orden"] for item in items] == [1, 2]

    # El catálogo y el DOCX leen el mismo orden persistido.
    catalogo = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()
    assert [item["titulo"] for item in catalogo["items"]] == [
        "[[ANEXO_B]]",
        "[[ANEXO_A]]",
    ]

    texto = _texto_docx(_exportar(client))
    assert texto.index("ANEXO 1. [[ANEXO_B]]") < texto.index(
        "ANEXO 2. [[ANEXO_A]]"
    )

    document = Document(BytesIO(_exportar(client)))
    marcadores = _marcadores_anexo(document)
    # El marcador sigue el orden 1..N y apunta al encabezado correcto.
    assert marcadores["anexo-1"] == "ANEXO 1. [[ANEXO_B]]"
    assert marcadores["anexo-2"] == "ANEXO 2. [[ANEXO_A]]"


def test_reordenar_acepta_lista_directa_y_rechaza_listas_invalidas(client):
    a = _crear_anexo(client, titulo="A").json()
    b = _crear_anexo(client, titulo="B").json()

    directa = client.patch(
        "/api/informes/anexos/orden",
        json=[b["id"], a["id"]],
    )
    assert directa.status_code == 200, directa.text
    assert [item["id"] for item in directa.json()["items"]] == [b["id"], a["id"]]

    incompleta = client.put(
        "/api/informes/anexos/orden",
        json={"anio": 2026, "trimestre": "T3", "anexo_ids": [a["id"]]},
    )
    assert incompleta.status_code == 400, incompleta.text

    duplicada = client.put(
        "/api/informes/anexos/orden",
        json={"anio": 2026, "trimestre": "T3", "anexo_ids": [a["id"], a["id"]]},
    )
    assert duplicada.status_code == 400, duplicada.text


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def test_docx_incluye_titulos_descripciones_y_todas_las_imagenes(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    primero = _crear_anexo(
        client,
        titulo="[[ANEXO_T3_UNO]] Actas con aprendices por certificar",
        descripcion="[[DESCRIPCION_ANEXO_UNO]]",
        archivos=[
            ("actas-1.png", PNG_1X1, "image/png"),
            ("actas-2.png", PNG_1X1, "image/png"),
        ],
    )
    segundo = _crear_anexo(
        client,
        titulo="[[ANEXO_T3_DOS]] Soporte de articulación",
        archivos=[("soporte.png", PNG_1X1, "image/png")],
    )
    assert primero.status_code == 201, primero.text
    assert segundo.status_code == 201, segundo.text

    contenido = _exportar(client)
    document = Document(BytesIO(contenido))
    texto = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "[[ANEXO_T3_UNO]]" in texto
    assert "[[ANEXO_T3_DOS]]" in texto
    assert "[[DESCRIPCION_ANEXO_UNO]]" in texto
    assert "ANEXO 1. [[ANEXO_T3_UNO]]" in texto
    assert "ANEXO 2. [[ANEXO_T3_DOS]]" in texto
    # Los títulos aparecen después del encabezado ANEXOS y antes de la firma.
    assert (
        texto.index("ANEXOS")
        < texto.index("[[ANEXO_T3_UNO]]")
        < texto.index("[[ANEXO_T3_DOS]]")
        < texto.index("Presentó:")
    )
    # El listado genérico se reemplaza y se insertan las 3 imágenes (2 + 1).
    assert "ANEXO 15." not in texto
    assert len(document.inline_shapes) == 3
    # T2 no recibe los anexos de T3.
    assert (
        client.get("/api/informes/anexos?anio=2026&trimestre=T2").json()["total"] == 0
    )


def test_descripcion_anexo_admite_negrita_cursiva_y_listas(client):
    """La descripción del anexo usa el mismo HTML restringido que estrategias."""
    with client.session_factory() as session:
        _seed_periodo(session)

    descripcion = (
        "<p>Texto <strong>negrita</strong> y <em>cursiva</em></p>"
        "<ul><li>Primer punto</li><li>Segundo punto</li></ul>"
        "<script>alert('x')</script>"
    )
    response = _crear_anexo(
        client,
        titulo="[[ANEXO_DESCRIPCION_RICA]]",
        descripcion=descripcion,
    )
    assert response.status_code == 201, response.text
    creado = response.json()
    assert "<strong>negrita</strong>" in creado["descripcion"]
    assert "<em>cursiva</em>" in creado["descripcion"]
    assert "<li>Primer punto</li>" in creado["descripcion"]
    assert "<script" not in creado["descripcion"]
    assert "alert" not in creado["descripcion"]

    # El PATCH también sanea y conserva el formato.
    actualizado = client.patch(
        f"/api/informes/anexos/{creado['id']}",
        data={
            "titulo": "[[ANEXO_DESCRIPCION_RICA]]",
            "descripcion": "<p>Nota <b>fuerte</b> e <i>inclinada</i></p>",
        },
    )
    assert actualizado.status_code == 200, actualizado.text
    assert actualizado.json()["descripcion"] == (
        "<p>Nota <strong>fuerte</strong> e <em>inclinada</em></p>"
    )

    document = Document(BytesIO(_exportar(client)))
    parrafo = next(
        p
        for p in document.paragraphs
        if "Nota fuerte e inclinada" in p.text.replace("\xa0", " ")
    )
    runs = {run.text: run for run in parrafo.runs}
    assert runs["fuerte"].bold is True
    assert runs["inclinada"].italic is True


def test_docx_sin_anexos_conserva_el_listado_institucional(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    texto = _texto_docx(_exportar(client))
    assert "ANEXO 1." in texto
    assert "ANEXO 15." in texto


def test_docx_ignora_filas_heredadas_pdf_o_docx(client, session_factory):
    """Las filas antiguas no-imagen no entran al catálogo ni a §5."""
    with session_factory() as session:
        _seed_periodo(session)
        heredado = InformeGestionAnexo(
            anio=2026,
            trimestre="T3",
            titulo="[[ANEXO_HEREDADO_PDF]]",
            orden=1,
        )
        heredado.archivos.append(
            InformeGestionAnexoArchivo(
                nombre_archivo="antiguo.pdf",
                content_type="application/pdf",
                ruta_archivo="antiguo.pdf",
                tamano=1,
                orden=0,
            )
        )
        session.add(heredado)
        session.commit()

    catalogo = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()
    assert catalogo["total"] == 0

    texto = _texto_docx(_exportar(client))
    assert "[[ANEXO_HEREDADO_PDF]]" not in texto
    assert "ANEXO 1." in texto  # se conserva el listado de la plantilla


def test_regresion_estrategias_siguen_en_el_docx_con_anexos(client):
    with client.session_factory() as session:
        _seed_periodo(session)
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={"3.1.1": "[[ESTRATEGIA_SUPERIOR_T3]] sigue aquí"},
        )

    _crear_anexo(client, titulo="[[ANEXO_CON_ESTRATEGIA]]")

    texto = _texto_docx(_exportar(client))
    assert texto.count("[[ESTRATEGIA_SUPERIOR_T3]]") == 1
    assert "[[ANEXO_CON_ESTRATEGIA]]" in texto
    assert "Pendiente de registro por la dependencia." in texto


def test_docx_numeracion_sin_doble_prefijo(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(client, titulo="ANEXO 1. Actas por certificar")
    _crear_anexo(client, titulo="Soportes de articulación")

    texto = _texto_docx(_exportar(client))
    assert "ANEXO 1. Actas por certificar" in texto
    assert "ANEXO 1. ANEXO 1." not in texto
    assert "ANEXO 2. Soportes de articulación" in texto
    # Aparece dos veces: una en el índice de §5 y otra como encabezado del
    # detalle posterior a la firma.
    assert texto.count("ANEXO 1. Actas por certificar") == 2


def _marcadores_anexo(document) -> dict[str, str]:
    """Mapea ``anexo-N`` al texto del párrafo que lo contiene."""
    marcadores: dict[str, str] = {}
    for paragraph in document.paragraphs:
        for start in paragraph._p.findall(qn("w:bookmarkStart")):
            nombre = start.get(qn("w:name")) or ""
            if nombre.startswith("anexo-"):
                marcadores[nombre] = paragraph.text.strip()
    return marcadores


def _parrafos_con_imagen(document) -> list[int]:
    return [
        index
        for index, paragraph in enumerate(document.paragraphs)
        if paragraph._p.findall(".//" + qn("w:drawing"))
        or paragraph._p.findall(".//" + qn("w:pict"))
    ]


def test_docx_indice_pre_firma_y_detalle_post_firma_con_bookmark(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(
        client,
        titulo="[[ANEXO_INDICE]] Actas del trimestre",
        descripcion="[[DESCRIPCION_DETALLE]]",
    )

    document = Document(BytesIO(_exportar(client)))
    parrafos = [paragraph.text.strip() for paragraph in document.paragraphs]
    primer_anexos = parrafos.index("ANEXOS")
    firma = next(
        index
        for index, texto in enumerate(parrafos)
        if texto.startswith("Presentó:")
    )
    segundo_anexos = next(
        index
        for index, texto in enumerate(parrafos)
        if index > firma and texto == "ANEXOS"
    )
    indice = next(
        index
        for index, texto in enumerate(parrafos)
        if "[[ANEXO_INDICE]]" in texto
    )
    detalle = next(
        index
        for index, texto in enumerate(parrafos)
        if index > segundo_anexos and "[[ANEXO_INDICE]]" in texto
    )

    # §5 antes de la firma: solo rótulo + título, sin descripción ni imágenes.
    assert primer_anexos < indice < firma
    assert parrafos[indice] == "ANEXO 1. [[ANEXO_INDICE]] Actas del trimestre"
    assert not any(
        "[[DESCRIPCION_DETALLE]]" in texto
        for texto in parrafos[primer_anexos:firma]
    )
    assert not [
        index
        for index in _parrafos_con_imagen(document)
        if primer_anexos < index < firma
    ]

    # Después de la firma: encabezado, descripción e imagen.
    assert firma < segundo_anexos < detalle
    assert parrafos[detalle] == "ANEXO 1. [[ANEXO_INDICE]] Actas del trimestre"
    assert any(
        "[[DESCRIPCION_DETALLE]]" in texto
        for texto in parrafos[segundo_anexos:]
    )
    assert any(
        index > segundo_anexos for index in _parrafos_con_imagen(document)
    )
    assert _marcadores_anexo(document) == {
        "anexo-1": "ANEXO 1. [[ANEXO_INDICE]] Actas del trimestre"
    }


def test_docx_separacion_entre_imagen_de_anexo_y_siguiente_titulo(client):
    """La última captura de un anexo no queda pegada al ANEXO siguiente."""
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(
        client,
        titulo="[[ANEXO_SEP_1]] Primer soporte",
        archivos=[
            ("uno.png", PNG_1X1, "image/png"),
            ("dos.png", PNG_1X1, "image/png"),
        ],
    )
    _crear_anexo(client, titulo="[[ANEXO_SEP_2]] Segundo soporte")

    document = Document(BytesIO(_exportar(client)))
    parrafos = document.paragraphs
    textos = [paragraph.text.strip() for paragraph in parrafos]

    # Encabezados del detalle post-firma: la última aparición de cada título.
    titulo_2 = max(
        index
        for index, texto in enumerate(textos)
        if texto.startswith("ANEXO 2.") and "[[ANEXO_SEP_2]]" in texto
    )
    titulo_1 = max(
        index
        for index, texto in enumerate(textos)
        if index < titulo_2
        and texto.startswith("ANEXO 1.")
        and "[[ANEXO_SEP_1]]" in texto
    )

    imagenes_1 = [
        index
        for index in _parrafos_con_imagen(document)
        if titulo_1 < index < titulo_2
    ]
    assert len(imagenes_1) == 2

    # Entre fotos del mismo anexo basta un espacio pequeño.
    for index in imagenes_1:
        espacio = parrafos[index].paragraph_format.space_after
        assert espacio is not None and espacio > 0

    # Entre el grupo de imágenes y el título siguiente hay una línea en blanco.
    ultima_imagen = max(imagenes_1)
    assert titulo_2 - ultima_imagen >= 2
    separador = parrafos[titulo_2 - 1]
    assert not separador.text.strip()
    assert not separador._p.findall(".//" + qn("w:drawing"))
    assert not separador._p.findall(".//" + qn("w:numPr"))

    # El orden y los bookmarks no cambian por agregar la separación.
    assert _marcadores_anexo(document) == {
        "anexo-1": "ANEXO 1. [[ANEXO_SEP_1]] Primer soporte",
        "anexo-2": "ANEXO 2. [[ANEXO_SEP_2]] Segundo soporte",
    }


def test_docx_estrategia_con_anexo_genera_hipervinculo_interno(client):
    with client.session_factory() as session:
        _seed_periodo(session)
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={
                "3.1.1": (
                    "[[ESTRATEGIA_REF]] Se sustenta en ANEXO 1. "
                    "y también en ANEXO 9."
                )
            },
        )
    _crear_anexo(client, titulo="[[ANEXO_REF]] Soporte del indicador")

    document = Document(BytesIO(_exportar(client)))
    objetivo = next(
        paragraph
        for paragraph in document.paragraphs
        if "[[ESTRATEGIA_REF]]" in paragraph.text
    )
    assert "ANEXO 1." in objetivo.text
    assert "ANEXO 9." in objetivo.text

    enlaces = objetivo._p.findall(qn("w:hyperlink"))
    assert [enlace.get(qn("w:anchor")) for enlace in enlaces] == ["anexo-1"]
    assert enlaces[0].text == "ANEXO 1."
    # N inexistente: texto plano, sin hipervínculo ni error de generación.
    assert all(enlace.get(qn("w:anchor")) != "anexo-9" for enlace in enlaces)
    assert _marcadores_anexo(document) == {
        "anexo-1": "ANEXO 1. [[ANEXO_REF]] Soporte del indicador"
    }


def test_docx_referencia_anexo_sin_anexos_queda_como_texto(client):
    with client.session_factory() as session:
        _seed_periodo(session)
        save_estrategias(
            session,
            anio=2026,
            trimestre="T3",
            secciones={"3.1.2": "[[ESTRATEGIA_SIN_ANEXO]] Ver ANEXO 1."},
        )

    document = Document(BytesIO(_exportar(client)))
    objetivo = next(
        paragraph
        for paragraph in document.paragraphs
        if "[[ESTRATEGIA_SIN_ANEXO]]" in paragraph.text
    )
    assert "ANEXO 1." in objetivo.text
    assert objetivo._p.findall(qn("w:hyperlink")) == []
    assert _marcadores_anexo(document) == {}
    # Sin anexos se conserva el listado institucional de la plantilla.
    assert "ANEXO 15." in _texto_docx(_exportar(client))


def test_anexos_no_dependen_del_modo_de_exportacion(client):
    """solo_trimestre y acumulado comparten los mismos anexos del periodo."""
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(client, titulo="[[ANEXO_MODO]]")

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        acumulado = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )
    with client.session_factory() as session:
        solo = export_report_docx(
            session, anio=2026, trimestre="T3", modo="solo_trimestre"
        )

    assert "[[ANEXO_MODO]]" in _texto_docx(acumulado)
    assert "[[ANEXO_MODO]]" in _texto_docx(solo)
