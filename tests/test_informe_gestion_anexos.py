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
from pathlib import Path

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


def _docx_minimo(texto: str = "Anexo DOCX") -> bytes:
    document = Document()
    document.add_paragraph(texto)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


DOCX_MINIMO = _docx_minimo()


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
    # El código se conserva como referencia, pero no reemplaza el número.
    assert segundo.json()["codigo"] == "A-2"
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
        codigo="1",
    )
    assert creado.status_code == 201, creado.text
    payload = creado.json()
    assert payload["titulo"] == "Actas con aprendices por certificar"
    assert payload["codigo"] == "ANEXO 1"
    assert payload["numero"] == 1
    assert payload["rotulo"] == "ANEXO 1"


def test_codigo_manual_no_altera_la_numeracion_estable(client):
    """Los códigos manuales no generan huecos ni saltos en el catálogo."""
    primero = _crear_anexo(client, titulo="Primero")  # posición 1
    segundo = _crear_anexo(client, titulo="Segundo", codigo="N° 5")  # posición 2
    tercero = _crear_anexo(client, titulo="Tercero")  # posición 3

    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["codigo"] == "ANEXO 5"
    numeros = [
        primero.json()["numero"],
        segundo.json()["numero"],
        tercero.json()["numero"],
    ]
    assert numeros == [1, 2, 3]

    items = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["items"]
    assert [item["numero"] for item in items] == [1, 2, 3]
    assert [item["rotulo"] for item in items] == [
        "ANEXO 1",
        "ANEXO 2",
        "ANEXO 3",
    ]
    assert items[1]["codigo"] == "ANEXO 5"


def test_codigo_duplicado_se_rechaza_en_crear_y_actualizar(client):
    primero = _crear_anexo(client, titulo="Uno", codigo="ANEXO 1")
    segundo = _crear_anexo(client, titulo="Dos", codigo="2")
    assert primero.status_code == 201, primero.text
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["codigo"] == "ANEXO 2"

    duplicado = _crear_anexo(client, titulo="Tres", codigo="1")
    assert duplicado.status_code == 400, duplicado.text
    assert "ya está usado" in duplicado.json()["detail"]

    colision = client.patch(
        f"/api/informes/anexos/{segundo.json()['id']}",
        data={"codigo": "ANEXO 1"},
    )
    assert colision.status_code == 400, colision.text

    # El propio código del registro no cuenta como colisión.
    propio = client.patch(
        f"/api/informes/anexos/{segundo.json()['id']}",
        data={"codigo": "ANEXO 2"},
    )
    assert propio.status_code == 200, propio.text

    # Un anexo sin código evita el 1 y el 2 ya reservados.
    automatico = _crear_anexo(client, titulo="Automático")
    assert automatico.json()["numero"] == 3


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
    assert response.json()["nombre_archivo"] == "nueva.png"
    # El binario anterior se elimina al confirmar el reemplazo y la descarga
    # apunta al archivo nuevo.
    assert not archivo_viejo.exists()
    archivo_nuevo = next(storage_dir().glob("2026-T3-*.png"))
    assert archivo_nuevo.read_bytes() == PNG_1X1
    descarga = client.get(f"/api/informes/anexos/{creado['id']}/download")
    assert descarga.status_code == 200, descarga.text
    assert descarga.content == PNG_1X1
    assert "nueva.png" in descarga.headers.get("content-disposition", "")


@pytest.mark.parametrize(
    ("nombre_archivo", "contenido", "content_type", "patron"),
    [
        ("captura.png", PNG_1X1, "image/png", "2026-T3-*.png"),
        ("soporte.pdf", PDF_MINIMO, "application/pdf", "2026-T3-*.pdf"),
        (
            "ANEXO 5.docx",
            DOCX_MINIMO,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "2026-T3-*.docx",
        ),
    ],
    ids=["png", "pdf", "docx"],
)
def test_eliminar_anexo_borra_registro_y_archivo(
    client,
    session_factory,
    nombre_archivo,
    contenido,
    content_type,
    patron,
):
    creado = _crear_anexo(
        client,
        titulo=f"Se va a eliminar {nombre_archivo}",
        archivo=(nombre_archivo, contenido, content_type),
    ).json()
    archivo = next(storage_dir().glob(patron))
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


def test_eliminar_anexo_no_falla_si_el_archivo_esta_bloqueado(
    client, session_factory, monkeypatch
):
    """Un DOCX/PDF abierto en Windows no convierte el DELETE en un 500."""
    creado = _crear_anexo(
        client,
        titulo="Archivo bloqueado",
        archivo=("bloqueado.pdf", PDF_MINIMO, "application/pdf"),
    ).json()
    archivo = next(storage_dir().glob("2026-T3-*.pdf"))
    original = Path.unlink

    def bloqueado(self, *args, **kwargs):
        if self == archivo:
            raise PermissionError("El archivo está en uso por otro proceso.")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", bloqueado)
    response = client.delete(f"/api/informes/anexos/{creado['id']}")
    monkeypatch.setattr(Path, "unlink", original)

    assert response.status_code == 204, response.text
    with session_factory() as session:
        assert session.query(InformeGestionAnexo).count() == 0
    assert (
        client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["total"] == 0
    )
    # La limpieza manual evita dejar basura del test (el archivo quedó bloqueado).
    archivo.unlink(missing_ok=True)


def test_archivo_disponible_refleja_si_el_binario_sigue_en_disco(client):
    creado = _crear_anexo(client, titulo="Binario perdido").json()
    assert creado["archivo_disponible"] is True
    archivo = next(storage_dir().glob("2026-T3-*.png"))
    archivo.unlink()

    items = client.get("/api/informes/anexos?anio=2026&trimestre=T3").json()["items"]
    assert items[0]["archivo_disponible"] is False


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

    codigo_cero = _crear_anexo(client, titulo="Código cero", codigo="0")
    assert codigo_cero.status_code == 400, codigo_cero.text

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


def test_docx_numeracion_sin_doble_prefijo(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(
        client,
        titulo="ANEXO 1. Actas por certificar",
        codigo="ANEXO 1",
    )
    _crear_anexo(client, titulo="Soportes de articulación")

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    texto = _texto_docx(contenido)
    assert "ANEXO 1. Actas por certificar" in texto
    assert "ANEXO 1. ANEXO 1." not in texto
    assert "ANEXO 2. Soportes de articulación" in texto
    assert texto.count("ANEXO 1.") == 1


def test_docx_ignora_codigos_heredados_y_numera_por_orden(client, session_factory):
    """Filas antiguas con códigos repetidos se numeran por posición 1..N."""
    with session_factory() as session:
        _seed_periodo(session)
        session.add_all(
            [
                InformeGestionAnexo(
                    anio=2026,
                    trimestre="T3",
                    codigo="ANEXO 3",
                    titulo="Primero heredado",
                    nombre_archivo="a.pdf",
                    content_type="application/pdf",
                    ruta_archivo="a.pdf",
                    tamano=1,
                    orden=1,
                ),
                InformeGestionAnexo(
                    anio=2026,
                    trimestre="T3",
                    codigo="ANEXO 3",
                    titulo="Segundo heredado",
                    nombre_archivo="b.pdf",
                    content_type="application/pdf",
                    ruta_archivo="b.pdf",
                    tamano=1,
                    orden=2,
                ),
            ]
        )
        session.commit()

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    texto = _texto_docx(contenido)
    assert "ANEXO 1. Primero heredado" in texto
    assert "ANEXO 2. Segundo heredado" in texto
    assert "ANEXO 3." not in texto


def test_docx_tres_anexos_en_orden_estable_1_2_3(client):
    """§5 lista 1..N aunque los códigos manuales sean 5, 3, 4."""
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(client, titulo="[[PRIMERO_ORDEN]]", codigo="5", orden=1)
    _crear_anexo(client, titulo="[[SEGUNDO_ORDEN]]", codigo="3", orden=2)
    _crear_anexo(client, titulo="[[TERCERO_ORDEN]]", codigo="4", orden=3)

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    texto = _texto_docx(contenido)
    assert texto.index("ANEXO 1. [[PRIMERO_ORDEN]]") < texto.index(
        "ANEXO 2. [[SEGUNDO_ORDEN]]"
    ) < texto.index("ANEXO 3. [[TERCERO_ORDEN]]")
    assert "ANEXO 5." not in texto
    assert "ANEXO 4." not in texto


def test_docx_orden_por_campo_orden_y_luego_id(client):
    """El número sigue ``orden`` (no el id) y desempata por id."""
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(client, titulo="[[ULTIMO_POR_ID]]", orden=30)
    _crear_anexo(client, titulo="[[PRIMERO_POR_ORDEN]]", orden=10)
    _crear_anexo(client, titulo="[[SEGUNDO_POR_ORDEN]]", orden=20)

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    texto = _texto_docx(contenido)
    assert texto.index("ANEXO 1. [[PRIMERO_POR_ORDEN]]") < texto.index(
        "ANEXO 2. [[SEGUNDO_POR_ORDEN]]"
    ) < texto.index("ANEXO 3. [[ULTIMO_POR_ID]]")


def test_docx_pdf_solo_lista_titulo_y_descripcion(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(
        client,
        titulo="Informe escaneado",
        descripcion="Soporte en PDF del periodo.",
        archivo=("soporte.pdf", PDF_MINIMO, "application/pdf"),
    )

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    document = Document(BytesIO(contenido))
    texto = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "ANEXO 1. Informe escaneado" in texto
    assert "Soporte en PDF del periodo." in texto
    # Decisión de producto: no se embebe el binario PDF en el Word.
    assert len(document.inline_shapes) == 0
    assert "Soporte en archivo" not in texto


def test_docx_imagen_se_inserta_con_aspecto(client):
    with client.session_factory() as session:
        _seed_periodo(session)
    _crear_anexo(client, titulo="Captura cuadrada")

    from app.services.informes import export_report_docx

    with client.session_factory() as session:
        contenido = export_report_docx(
            session, anio=2026, trimestre="T3", modo="acumulado"
        )

    document = Document(BytesIO(contenido))
    assert len(document.inline_shapes) == 1
    shape = document.inline_shapes[0]
    assert shape.width > 0 and shape.height > 0
    # El PNG de prueba es cuadrado: se conserva la proporción al escalarlo.
    assert abs(shape.width - shape.height) <= 10000
    assert "ANEXO 1. Captura cuadrada" in "\n".join(
        paragraph.text for paragraph in document.paragraphs
    )


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
