"""Anexos del Informe de Gestión por (año, trimestre) y su presencia en §5.

Cubre:
* CRUD por API con archivo real en un directorio temporal (``tmp_path``);
* aislamiento entre trimestres (T3 vs T2);
* actualización de metadatos y borrado del registro + archivo;
* inserción de títulos/descripciones en la sección ANEXOS del DOCX;
* generación sin anexos sin romper el listado institucional de la plantilla;
* regresión: las estrategias guardadas siguen apareciendo en el DOCX.
"""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from docx import Document

from app.models import InformeGestionAnexo
from app.services.informe_gestion_anexos import storage_dir
from app.services.informe_gestion_estrategias import save_estrategias
from tests.test_informes_trimestres import _seed_periodo

# PNG 1x1 válido (firma PNG real, necesario para que python-docx lo inserte).
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PDF_MINIMO = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF\n"


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
    codigo: str | None = None,
    orden: int | None = None,
    archivo: tuple[str, bytes, str] = ("captura.png", PNG_1X1, "image/png"),
):
    data = {
        "anio": str(anio),
        "trimestre": trimestre,
        "titulo": titulo,
    }
    if descripcion is not None:
        data["descripcion"] = descripcion
    if codigo is not None:
        data["codigo"] = codigo
    if orden is not None:
        data["orden"] = str(orden)
    return client.post(
        "/api/informes/anexos",
        data=data,
        files={"file": archivo},
    )


# ---------------------------------------------------------------------------
# CRUD y aislamiento por periodo
# ---------------------------------------------------------------------------
def test_crear_anexo_y_listar_solo_en_su_trimestre(client):
    response = _crear_anexo(
        client,
        titulo="[[ANEXO_T3_CAPTURA]]",
        descripcion="Captura de actas del trimestre.",
    )
    assert response.status_code == 201, response.text
    creado = response.json()
    assert creado["anio"] == 2026
    assert creado["trimestre"] == "T3"
    assert creado["titulo"] == "[[ANEXO_T3_CAPTURA]]"
    assert creado["content_type"] == "image/png"
    assert creado["nombre_archivo"] == "captura.png"
    assert creado["download_url"].endswith("/download")

    t3 = client.get("/api/informes/anexos?anio=2026&trimestre=T3")
    assert t3.status_code == 200, t3.text
    assert t3.json()["total"] == 1
    assert t3.json()["items"][0]["id"] == creado["id"]

    t2 = client.get("/api/informes/anexos?anio=2026&trimestre=T2")
    assert t2.status_code == 200, t2.text
    assert t2.json()["total"] == 0
    assert t2.json()["items"] == []

    # El binario se guarda en el directorio configurado, no en la BD.
    guardados = list(storage_dir().glob("2026-T3-*.png"))
    assert len(guardados) == 1
    assert guardados[0].read_bytes() == PNG_1X1


def test_orden_automatico_y_codigo_manual(client):
    primero = _crear_anexo(client, titulo="Primero")
    segundo = _crear_anexo(client, titulo="Segundo", codigo="A-2")
    assert primero.json()["orden"] == 1
    assert segundo.json()["orden"] == 2
    assert segundo.json()["codigo"] == "A-2"

    items = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["items"]
    assert [item["titulo"] for item in items] == ["Primero", "Segundo"]
    assert [item["numero"] for item in items] == [1, 2]


# ---------------------------------------------------------------------------
# Metadatos y borrado
# ---------------------------------------------------------------------------
def test_actualizar_metadatos_sin_reemplazar_archivo(client):
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
    assert actualizado["codigo"] == "ANEXO 9"
    assert actualizado["orden"] == 7
    # El archivo original no se reemplaza si no se envía uno nuevo.
    assert actualizado["nombre_archivo"] == creado["nombre_archivo"]

    catalogo = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()
    assert catalogo["items"][0]["titulo"] == "Título editado"
    assert catalogo["items"][0]["descripcion"] == "Descripción editada"


def test_reemplazar_archivo_desde_patch(client):
    creado = _crear_anexo(
        client, archivo=("documento.pdf", PDF_MINIMO, "application/pdf")
    ).json()
    archivo_viejo = next(storage_dir().glob("2026-T3-*.pdf"))
    assert archivo_viejo.exists()

    response = client.patch(
        f"/api/informes/anexos/{creado['id']}",
        files={"file": ("nueva.png", PNG_1X1, "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["content_type"] == "image/png"
    # El binario anterior se elimina al confirmar el reemplazo.
    assert not archivo_viejo.exists()
    assert list(storage_dir().glob("2026-T3-*.png"))


def test_eliminar_anexo_borra_registro_y_archivo(client, session_factory):
    creado = _crear_anexo(client, titulo="Se va a eliminar").json()
    archivo = next(storage_dir().glob("2026-T3-*.png"))
    assert archivo.exists()

    response = client.delete(f"/api/informes/anexos/{creado['id']}")
    assert response.status_code == 204, response.text
    assert not archivo.exists()

    with session_factory() as session:
        assert session.query(InformeGestionAnexo).count() == 0
    assert (
        client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["total"] == 0
    )
    assert client.delete(f"/api/informes/anexos/{creado['id']}").status_code == 404


def test_validaciones_de_tipo_titulo_y_descarga(client):
    invalido = _crear_anexo(
        client, archivo=("notas.txt", b"texto plano", "text/plain")
    )
    assert invalido.status_code == 415, invalido.text

    sin_titulo = client.post(
        "/api/informes/anexos",
        data={"anio": "2026", "trimestre": "T3", "titulo": "   "},
        files={"file": ("captura.png", PNG_1X1, "image/png")},
    )
    assert sin_titulo.status_code == 400, sin_titulo.text

    creado = _crear_anexo(client, titulo="Descargable").json()
    descarga = client.get(f"/api/informes/anexos/{creado['id']}/download")
    assert descarga.status_code == 200, descarga.text
    assert descarga.content == PNG_1X1
    assert "captura.png" in descarga.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def test_docx_incluye_anexos_del_trimestre_en_seccion_5(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    primero = _crear_anexo(
        client,
        titulo="[[ANEXO_T3_UNO]] Actas con aprendices por certificar",
        descripcion="[[DESCRIPCION_ANEXO_UNO]]",
        orden=1,
    )
    segundo = _crear_anexo(
        client,
        titulo="[[ANEXO_T3_DOS]] Soporte de articulación",
        orden=2,
        archivo=("soporte.pdf", PDF_MINIMO, "application/pdf"),
    )
    assert primero.status_code == 201, primero.text
    assert segundo.status_code == 201, segundo.text

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    document = Document(BytesIO(contenido))
    texto = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "[[ANEXO_T3_UNO]]" in texto
    assert "[[ANEXO_T3_DOS]]" in texto
    assert "[[DESCRIPCION_ANEXO_UNO]]" in texto
    assert "ANEXO 1. [[ANEXO_T3_UNO]]" in texto
    assert "ANEXO 2. [[ANEXO_T3_DOS]]" in texto
    # Los títulos aparecen después del encabezado ANEXOS y antes de la firma.
    posicion_encabezado = texto.index("ANEXOS")
    posicion_uno = texto.index("[[ANEXO_T3_UNO]]")
    posicion_dos = texto.index("[[ANEXO_T3_DOS]]")
    posicion_firma = texto.index("Presentó:")
    assert posicion_encabezado < posicion_uno < posicion_dos < posicion_firma
    # El listado genérico de la plantilla se reemplazó y la imagen se incrustó.
    assert "ANEXO 15." not in texto
    assert len(document.inline_shapes) >= 1

    # T2 no recibe los anexos de T3.
    assert (
        client.get("/api/informes/anexos?anio=2026&trimestre=T2").json()["total"] == 0
    )


def test_docx_sin_anexos_no_rompe_y_conserva_listado(client):
    with client.session_factory() as session:
        _seed_periodo(session)

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    texto = _texto_docx(contenido)
    # Decisión v1: sin anexos se conserva el listado institucional de plantilla.
    assert "ANEXO 1." in texto
    assert "ANEXO 15." in texto


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

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    texto = _texto_docx(contenido)
    assert texto.count("[[ESTRATEGIA_SUPERIOR_T3]]") == 1
    assert "[[ANEXO_CON_ESTRATEGIA]]" in texto
    # Las secciones sin texto conservan el placeholder institucional.
    assert "Pendiente de registro por la dependencia." in texto


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
