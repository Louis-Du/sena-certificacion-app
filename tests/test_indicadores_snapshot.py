"""Regresiones de cálculo e importación para el cierre previo a #46.

Cubre los bloqueadores B1-B5 documentados en la auditoría:

* B1: efectividad global solo sobre personas titulada (sin complementaria).
* B2: reimportar ACTAS 2026 se comporta como snapshot (no acumula).
* B3: un documento en CERTIFICADOS y PENDIENTES no cuenta dos veces; la
  resolución manual se aplica al cálculo.
* B4: la meta del lote vigente gana y nunca se suman dos filas META.
* B5: certificados por mes sale del consolidado y del mes de certificación.

Los datos son mínimos y controlados: no representan cifras institucionales.
"""

from __future__ import annotations

import json
from io import BytesIO

import pandas as pd

from app.models import ImportHistory, ImportedRecord, Learner
from app.services.imports import confirm_import, stage_file
from app.services.indicadores import (
    compute_certificados_por_mes,
    compute_indicadores_2026,
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _seed(session, information_type: str, records: list[dict]) -> None:
    history = ImportHistory(
        file_name="prueba.xlsx",
        information_type=information_type,
        source_type=information_type,
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


def _certificado(document: str, nivel: str = "TECNÓLOGO", mes: str = "JUNIO") -> dict:
    return {
        "nivel": nivel,
        "numero de documento": document,
        "nombre": f"Persona {document}",
        "ficha": "100",
        "acta": "36",
        "estado": "CERTIFICADOS",
        "mes de certificacion": mes,
    }


def _pendiente(document: str, nivel: str = "TECNÓLOGO") -> dict:
    return {
        "nivel": nivel,
        "numero de documento": document,
        "nombre": f"Persona {document}",
        "ficha": "100",
        "estado": "PENDIENTE",
        "motivo de no certificacion": "APE",
    }


def _meta(
    superior: int | None = None,
    tecnica: int | None = None,
    articulacion: int | None = None,
    complementaria: int | None = None,
) -> dict:
    values = {
        "superior": superior,
        "tecnica": tecnica,
        "articulacion": articulacion,
        "complementaria": complementaria,
    }
    return {key: value for key, value in values.items() if isinstance(value, int)}


def _metricas(data: dict) -> dict[str, dict]:
    return {item["category"]: item for item in data["metricas"]}


def _full_actas_xlsx(
    certificados: list[dict],
    pendientes: list[dict],
    complementaria: list[list] | None = None,
    meta_values: tuple[int, int, int, int] = (100, 200, 50, 1000),
) -> bytes:
    """ACTAS 2026 mínimo: CERTIFICADOS, PENDIENTES, COMPLEMENTARIA y META."""
    superior, tecnica, articulacion, complementaria_meta = meta_values
    meta_rows = [
        ["METAS DE CERTIFICACIÓN"],
        [
            "TECNICO LABORAL Y OTROS",
            "ARTICULACION CON LA MEDIA",
            "EDUCACIÓN SUPERIOR",
            "TOTAL TITULADA",
            "TOTAL COMPLEMENTARIA",
            "TOTAL FORMACIÓN PROFESIONAL",
        ],
        [tecnica, articulacion, superior, tecnica + articulacion + superior, complementaria_meta],
    ]
    complementaria_rows = complementaria or [
        ["2026-02-26", 10, None, "2026-02-26", 20, None, None, None, None, None, None, None]
    ]
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(certificados).to_excel(writer, sheet_name="CERTIFICADOS", index=False)
        pd.DataFrame(pendientes).to_excel(writer, sheet_name="PENDIENTES", index=False)
        pd.DataFrame(complementaria_rows).to_excel(
            writer, sheet_name="COMPLEMENTARIA", header=False, index=False
        )
        pd.DataFrame(meta_rows).to_excel(writer, sheet_name="META", header=False, index=False)
    return buffer.getvalue()


def _importar(session, content: bytes) -> dict:
    staged = stage_file("ACTAS 2026.xlsx", content, "actas_completo")
    return confirm_import(staged.validation_id, session)


# ---------------------------------------------------------------------------
# B1: efectividad homogénea (solo personas titulada)
# ---------------------------------------------------------------------------
def test_b1_efectividad_no_mezcla_complementaria(session_factory):
    with session_factory() as session:
        _seed(session, "certificados", [_certificado("1", "TECNÓLOGO", "JUNIO")])
        _seed(session, "pendientes", [_pendiente("2", "TECNÓLOGO")])
        _seed(
            session,
            "complementaria",
            [{"canal": "presencial", "fecha": "2026-02-26", "cantidad": 80}],
        )
        _seed(
            session,
            "meta",
            [_meta(superior=100, tecnica=200, articulacion=50, complementaria=1000)],
        )
        data = compute_indicadores_2026(session)

    assert data["certificados_personas"] == 1
    assert data["certificados_complementaria"] == 80
    assert data["pendientes_personas"] == 1
    # total_certificados conserva el avance global (personas + complementaria),
    # pero la efectividad NO lo usa.
    assert data["total_certificados"] == 81
    assert data["efectividad_global"] == 50.0
    assert data["formula_efectividad_global"]["numerador"] == 1
    assert data["formula_efectividad_global"]["denominador"] == 2
    assert "complementaria" in data["universo_efectividad"]
    # La categoría complementaria no inventa pendientes comparables.
    assert _metricas(data)["complementaria"]["efectividad"] is None


def test_b1_sin_pendientes_no_inventa_efectividad(session_factory):
    with session_factory() as session:
        _seed(session, "certificados", [_certificado("1")])
        _seed(session, "complementaria", [{"canal": "virtual", "fecha": "2026-03-01", "cantidad": 10}])
        data = compute_indicadores_2026(session)

    assert data["total_pendientes"] is None
    assert data["efectividad_global"] is None
    assert any("PENDIENTES" in aviso for aviso in data["advertencias"])


# ---------------------------------------------------------------------------
# B3: conflicto CERTIFICADOS/PENDIENTES aplicado al cálculo
# ---------------------------------------------------------------------------
def test_b3_conflicto_sin_resolver_no_infla_ningun_total(session_factory):
    with session_factory() as session:
        _seed(
            session,
            "certificados",
            [_certificado("5555"), _certificado("6666")],
        )
        _seed(
            session,
            "pendientes",
            [_pendiente("5555"), _pendiente("7777")],
        )
        data = compute_indicadores_2026(session)

    assert data["conflictos_certificados_pendientes"] == 1
    assert data["conflictos"]["sin_resolver"] == 1
    # 5555 se excluye de ambos universos: queda 6666 certificado y 7777 pendiente.
    assert data["certificados_personas"] == 1
    assert data["total_pendientes"] == 1
    assert data["efectividad_global"] == 50.0
    assert any("sin resolver" in aviso for aviso in data["advertencias"])


def test_b3_resolucion_certificado_cuenta_una_vez(session_factory):
    with session_factory() as session:
        _seed(session, "certificados", [_certificado("5555"), _certificado("6666")])
        _seed(session, "pendientes", [_pendiente("5555"), _pendiente("7777")])
        session.add(
            Learner(
                identification="5555",
                name="Persona 5555",
                conflict_resolution="CERTIFICADOS",
                certification_status="CERTIFICADOS",
            )
        )
        session.commit()
        data = compute_indicadores_2026(session)

    assert data["certificados_personas"] == 2
    assert data["total_pendientes"] == 1
    assert data["efectividad_global"] == 66.7
    assert data["conflictos"]["resueltos"] == 1
    assert data["conflictos"]["sin_resolver"] == 0


def test_b3_resolucion_pendiente_cuenta_una_vez(session_factory):
    with session_factory() as session:
        _seed(session, "certificados", [_certificado("5555"), _certificado("6666")])
        _seed(session, "pendientes", [_pendiente("5555"), _pendiente("7777")])
        session.add(
            Learner(
                identification="5555",
                name="Persona 5555",
                conflict_resolution="PENDIENTE",
                certification_status="PENDIENTE",
            )
        )
        session.commit()
        data = compute_indicadores_2026(session)

    assert data["certificados_personas"] == 1
    assert data["total_pendientes"] == 2
    assert data["efectividad_global"] == 33.3
    assert data["conflictos"]["resueltos"] == 1


# ---------------------------------------------------------------------------
# B2/B4: snapshot de lote y meta vigente
# ---------------------------------------------------------------------------
def test_b2_reimportar_mismo_archivo_es_idempotente(session_factory):
    content = _full_actas_xlsx(
        certificados=[_certificado("1"), _certificado("2", "TÉCNICO")],
        pendientes=[_pendiente("3")],
        meta_values=(100, 200, 50, 1000),
    )
    with session_factory() as session:
        _importar(session, content)
        primero = compute_indicadores_2026(session)
        _importar(session, content)
        segundo = compute_indicadores_2026(session)

    assert segundo["certificados_personas"] == primero["certificados_personas"] == 2
    assert segundo["total_pendientes"] == primero["total_pendientes"] == 1
    assert segundo["certificados_complementaria"] == primero["certificados_complementaria"] == 30
    assert segundo["total_meta"] == primero["total_meta"] == 1350
    assert segundo["lote_vigente_id"] != primero["lote_vigente_id"]


def test_b2_archivo_corregido_reemplaza_y_no_suma(session_factory):
    original = _full_actas_xlsx(
        certificados=[_certificado("1"), _certificado("2", "TÉCNICO")],
        pendientes=[_pendiente("3")],
        meta_values=(100, 200, 50, 1000),
    )
    corregido = _full_actas_xlsx(
        certificados=[_certificado("1")],
        pendientes=[_pendiente("3")],
        complementaria=[
            ["2026-03-10", 5, None, "2026-03-10", 7, None, None, None, None, None, None, None]
        ],
        meta_values=(300, 400, 60, 2000),
    )
    with session_factory() as session:
        _importar(session, original)
        original_data = compute_indicadores_2026(session)
        assert original_data["certificados_personas"] == 2
        assert original_data["certificados_complementaria"] == 30
        assert original_data["total_meta"] == 1350

        _importar(session, corregido)
        corregido_data = compute_indicadores_2026(session)

    # El documento 2 ya no viene: no queda como fantasma del lote anterior.
    assert corregido_data["certificados_personas"] == 1
    assert corregido_data["certificados_complementaria"] == 12
    # La meta nueva reemplaza a la vieja: no se suma 1350 + 2760.
    assert corregido_data["total_meta"] == 300 + 400 + 60 + 2000
    assert corregido_data["conflictos"]["detectados"] == 0


def test_b4_meta_anterior_no_gana_y_no_se_suman_dos_filas(session_factory):
    with session_factory() as session:
        _seed(session, "meta", [_meta(superior=100, tecnica=200, articulacion=50, complementaria=1000)])
        _seed(session, "meta", [_meta(superior=300, tecnica=400, articulacion=60, complementaria=2000)])
        data = compute_indicadores_2026(session)

    assert data["total_meta"] == 300 + 400 + 60 + 2000
    # Si en un mismo lote hubiera dos filas META, se elige la última; nunca se suman.
    with session_factory() as session:
        _seed(
            session,
            "meta",
            [
                _meta(superior=10, tecnica=20, articulacion=30, complementaria=40),
                _meta(superior=1, tecnica=2, articulacion=3, complementaria=4),
            ],
        )
        data = compute_indicadores_2026(session)

    assert data["total_meta"] == 1 + 2 + 3 + 4


# ---------------------------------------------------------------------------
# B5: certificados por mes desde el consolidado vigente
# ---------------------------------------------------------------------------
def test_b5_certificados_por_mes_usa_mes_de_certificacion_del_consolidado(session_factory):
    with session_factory() as session:
        _seed(
            session,
            "certificados",
            [
                _certificado("1", mes="MARZO"),
                _certificado("2", mes="MARZO"),
                _certificado("3", mes="JUNIO"),
                _certificado("4", mes="OCTUBRE"),  # fuera de periodo
                _certificado("5", mes=None),       # sin mes
            ],
        )
        data = compute_certificados_por_mes(session)

    por_mes = {item["mes"]: item["certificados"] for item in data["meses"]}
    assert data["universo"] == "consolidado"
    assert data["total"] == 3
    assert por_mes["marzo"] == 2
    assert por_mes["junio"] == 1
    # OCTUBRE esta fuera del corte Ene-Sep: no se dibuja como cero porque si
    # hay un certificado, solo que se informa aparte para no inflar el total.
    assert "octubre" not in por_mes
    assert data["fuera_de_periodo"] == 1
    assert data["sin_mes"] == 1
    assert "CERTIFICADOS" in data["fuente"]


def test_b5_corregir_mes_en_reimportacion_mueve_el_grafico(session_factory):
    with session_factory() as session:
        _importar(
            session,
            _full_actas_xlsx(
                certificados=[_certificado("1", mes="JUNIO")],
                pendientes=[],
            ),
        )
        junio = compute_certificados_por_mes(session)
        _importar(
            session,
            _full_actas_xlsx(
                certificados=[_certificado("1", mes="ENERO")],
                pendientes=[],
            ),
        )
        enero = compute_certificados_por_mes(session)

    assert {m["mes"]: m["certificados"] for m in junio["meses"]}["junio"] == 1
    assert {m["mes"]: m["certificados"] for m in enero["meses"]}["junio"] == 0
    assert {m["mes"]: m["certificados"] for m in enero["meses"]}["enero"] == 1


def test_b5_endpoint_expone_el_consolidado_no_el_padron_local(client):
    with client.session_factory() as session:
        _seed(session, "certificados", [_certificado("1", mes="ABRIL")])
        # Un aprendiz del padrón local con otro mes no debe alterar el gráfico.
        session.add(
            Learner(
                identification="9999",
                name="Padrón local",
                certification_month="DICIEMBRE",
            )
        )
        session.commit()

    data = client.get("/api/indicadores/certificados-por-mes").json()
    por_mes = {item["mes"]: item["certificados"] for item in data["meses"]}
    assert data["universo"] == "consolidado"
    assert por_mes["abril"] == 1
    # DICIEMBRE solo existe en el padron local; el grafico consolidado no lo
    # inventa ni lo mezcla con ACTAS 2026.
    assert "diciembre" not in por_mes
    assert data["total"] == 1
