"""
Pruebas del calculo de indicadores (``app.services.indicadores``).

Que se verifica aqui
--------------------
* Que los indicadores se calculen SOLO a partir de los registros importados
  (ya no hay cifras escritas en el codigo).
* La clasificacion misional por categoria y la regla de "no asignar por defecto".
* El filtrado del periodo 2026-01-01 a 2026-09-30 y la exclusion de lo que queda
  fuera.
* La deduplicacion de aprendices y la diferencia entre PERSONAS pendientes e
  INCIDENCIAS de motivos.
* Que un dato que no se puede calcular se informe como ``None`` (no como 0).
* La respuesta del endpoint ``GET /api/indicadores``.
* La prevencion de duplicados al importar dos veces el mismo archivo.

Los registros de prueba son pequenos y controlados: NO representan cifras
institucionales reales.
"""

from __future__ import annotations

import json
from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from app.models import ImportedRecord, ImportHistory
from app.services.imports import confirm_import, stage_file
from app.services.indicadores import compute_indicadores_2026


# ---------------------------------------------------------------------------
# Utilidades para sembrar registros importados en la base de datos de prueba
# ---------------------------------------------------------------------------
def _seed(session, information_type: str, records: list[dict]) -> None:
    """
    Guarda registros como si el usuario los hubiera importado.

    Se usa el mismo formato que produce la importacion real: cada registro va
    serializado como JSON en ``ImportedRecord.payload``. Asi las pruebas
    ejercitan el mismo camino de lectura que la aplicacion.
    """
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


def _certificado(
    document: str,
    nivel: str,
    mes: str = "JUNIO",
    estado: str = "CERTIFICADOS",
    acta: str | None = "36",
) -> dict:
    return {
        "nivel": nivel,
        "numero de documento": document,
        "nombre": f"Persona {document}",
        "ficha": "100",
        "acta": acta,
        "estado": estado,
        "mes de certificacion": mes,
    }


def _pendiente(document: str, nivel: str, motivo: str | None) -> dict:
    return {
        "nivel": nivel,
        "numero de documento": document,
        "nombre": f"Persona {document}",
        "ficha": "100",
        "estado": "PENDIENTE",
        "motivo de no certificacion": motivo,
    }


def _meta(superior=None, tecnica=None, articulacion=None, complementaria=None) -> dict:
    """Un registro de metas con las claves que usa el servicio (o ``None`` si falta)."""
    valores = {
        "superior": superior,
        "tecnica": tecnica,
        "articulacion": articulacion,
        "complementaria": complementaria,
    }
    return {clave: valor for clave, valor in valores.items() if isinstance(valor, int)}


def _metricas_por_categoria(data: dict) -> dict[str, dict]:
    return {metrica["category"]: metrica for metrica in data["metricas"]}


# ---------------------------------------------------------------------------
# 1. Sin datos: no se inventan cifras (se informa "no calculable")
# ---------------------------------------------------------------------------
def test_sin_datos_no_inventa_cifras(session_factory):
    with session_factory() as session:
        data = compute_indicadores_2026(session)

    assert data["datos_suficientes"] is False
    # Nada de metas: no se puede calcular el total ni el avance.
    assert data["total_meta"] is None
    assert data["avance_global"] is None
    # Nada de pendientes: no se puede calcular la efectividad.
    assert data["total_pendientes"] is None
    assert data["efectividad_global"] is None
    # Si no hay certificados, el total SI es un cero real (no es un dato faltante).
    assert data["total_certificados"] == 0
    assert data["motivos"] == []
    assert data["advertencias"], "Debe advertir que no hay documentos cargados"
    assert all(m["meta"] is None for m in data["metricas"])
    assert all(m["avance"] is None for m in data["metricas"])


# ---------------------------------------------------------------------------
# 2. Clasificacion misional + periodo (incluye y excluye)
# ---------------------------------------------------------------------------
def test_clasificacion_misional_y_filtrado_por_periodo(session_factory):
    registros = [
        _certificado("1", "TECNÓLOGO", "JUNIO"),            # superior
        _certificado("2", "TÉCNICO", "JUNIO"),              # tecnica
        _certificado("3", "AUXILIAR", "JUNIO"),             # tecnica
        _certificado("4", "SENATIC", "JUNIO"),              # tecnica
        _certificado("5", "PROFUNDIZACIÓN TÉCNICA", "JUNIO"),  # tecnica
        _certificado("6", "MEDIA TÉCNICA", "JUNIO"),        # articulacion
        _certificado("7", "OPERARIO", "JUNIO"),             # sin regla -> sin clasificar
        _certificado("8", "TECNÓLOGO", "OCTUBRE"),          # fuera del periodo
        _certificado("9", "TÉCNICO", "JUNIO", estado=""),   # estado vacio -> no cuenta
    ]
    with session_factory() as session:
        _seed(session, "certificados", registros)
        _seed(session, "meta", [_meta(superior=100, tecnica=200, articulacion=50, complementaria=1000)])
        data = compute_indicadores_2026(session)

    metricas = _metricas_por_categoria(data)
    assert metricas["superior"]["certificados"] == 1
    assert metricas["tecnica"]["certificados"] == 4
    assert metricas["articulacion"]["certificados"] == 1
    # OPERARIO no esta en la regla: queda aparte, no se suma a "tecnica".
    assert data["sin_clasificar"]["certificados"] == 1
    assert data["sin_clasificar"]["niveles"]["certificados: operario"] == 1
    # El registro de OCTUBRE no entra al periodo Ene-Sep.
    assert data["total_certificados"] == 6
    assert any("fuera del periodo" in aviso for aviso in data["advertencias"])
    # El avance usa la meta documentada: 1/100 -> 1.0 %
    assert metricas["superior"]["avance"] == 1.0


# ---------------------------------------------------------------------------
# 3. Deduplicacion de aprendices
# ---------------------------------------------------------------------------
def test_deduplicacion_de_aprendices(session_factory):
    # La misma persona aparece dos veces (misma cedula) dentro del periodo.
    registros = [
        _certificado("1001", "TECNÓLOGO", "JUNIO", acta="36"),
        _certificado("1001", "TECNÓLOGO", "JULIO", acta="37"),
    ]
    with session_factory() as session:
        _seed(session, "certificados", registros)
        data = compute_indicadores_2026(session)

    metricas = _metricas_por_categoria(data)
    assert metricas["superior"]["certificados"] == 1
    assert data["total_certificados"] == 1


def test_certificado_sin_documento_no_se_puede_contar(session_factory):
    registros = [
        _certificado("", "TÉCNICO", "JUNIO"),
        _certificado("2002", "TÉCNICO", "JUNIO"),
    ]
    with session_factory() as session:
        _seed(session, "certificados", registros)
        data = compute_indicadores_2026(session)

    assert data["total_certificados"] == 1
    assert any("sin numero de documento" in aviso for aviso in data["advertencias"])


# ---------------------------------------------------------------------------
# 4. Personas pendientes vs incidencias de motivos
# ---------------------------------------------------------------------------
def test_personas_pendientes_vs_incidencias(session_factory):
    pendientes = [
        _pendiente("A", "TÉCNICO", "APE, No anexa T&T"),       # 1 persona, 2 incidencias
        _pendiente("B", "TÉCNICO", "APE"),                     # 1 persona, 1 incidencia
        _pendiente("C", "TÉCNICO", None),                      # 1 persona, 0 incidencias
        _pendiente("D", "TÉCNICO", "APE, Documento vencido"),  # 1 persona, 2 incidencias
    ]
    with session_factory() as session:
        _seed(session, "pendientes", pendientes)
        data = compute_indicadores_2026(session)

    # 4 personas pendientes (aunque haya 5 incidencias de motivos).
    assert data["total_pendientes"] == 4
    # 5 incidencias: "ape" x3 + "no anexa t&t" x1 + "documento vencido" x1.
    assert data["total_incidencias_causas"] == 5
    assert data["aprendices_con_causas_multiples"] == 2
    assert data["aprendices_pendientes_sin_motivo"] == 1

    motivos = {m["motivo"]: m["cantidad"] for m in data["motivos"]}
    assert motivos["ape"] == 3
    assert motivos["no anexa t&t"] == 1
    assert motivos["documento vencido"] == 1
    # Las personas y las incidencias se informan por separado: NO se fuerzan a coincidir.
    assert data["total_pendientes"] != data["total_incidencias_causas"]


# ---------------------------------------------------------------------------
# 5. Doble conteo entre categorias y totales
# ---------------------------------------------------------------------------
def test_no_doble_conteo_y_nota_de_articulacion(session_factory):
    with session_factory() as session:
        _seed(
            session,
            "meta",
            [_meta(superior=943, tecnica=1910, articulacion=1995, complementaria=83726)],
        )
        data = compute_indicadores_2026(session)

    categorias = [m["category"] for m in data["metricas"]]
    assert categorias == ["superior", "tecnica", "articulacion", "complementaria"]

    # El total anual es la suma de las metas, sin repetir "Articulacion"
    # (que ya viene incluida en el total institucional de Tecnica Laboral).
    assert data["total_meta"] == sum(m["meta"] for m in data["metricas"])
    assert data["total_meta"] == 943 + 1910 + 1995 + 83726
    # La nota de doble conteo se entrega para que quien lea sepa por que no se suma aparte.
    articulacion = _metricas_por_categoria(data)["articulacion"]
    assert articulacion["nota_doble_conteo"]


def test_meta_faltante_impide_calcular_avance(session_factory):
    # Solo hay meta de Educacion Superior: las demas categorias quedan sin avance.
    with session_factory() as session:
        _seed(session, "meta", [_meta(superior=943)])
        data = compute_indicadores_2026(session)

    metricas = _metricas_por_categoria(data)
    assert metricas["superior"]["meta"] == 943
    assert metricas["tecnica"]["meta"] is None
    assert metricas["tecnica"]["avance"] is None
    assert metricas["tecnica"]["brecha"] is None
    # Si falta cualquier meta, el total anual NO representa el total institucional.
    assert data["total_meta"] is None
    assert data["avance_global"] is None
    assert any("meta" in aviso.lower() for aviso in data["advertencias"])


# ---------------------------------------------------------------------------
# 6. Formacion complementaria (conteos agregados y filtro de periodo)
# ---------------------------------------------------------------------------
def test_complementaria_suma_por_canal_y_respeta_el_periodo(session_factory):
    complementaria = [
        {"canal": "presencial", "fecha": "2026-02-26", "cantidad": 100},
        {"canal": "virtual", "fecha": "2026-10-05", "cantidad": 999},  # fuera del periodo
        {"canal": "campesena", "fecha": None, "cantidad": 50},         # sin fecha
    ]
    with session_factory() as session:
        _seed(session, "complementaria", complementaria)
        _seed(session, "meta", [_meta(complementaria=1000)])
        data = compute_indicadores_2026(session)

    complementaria_metrica = _metricas_por_categoria(data)["complementaria"]
    # Solo se suma lo que esta dentro del periodo.
    assert complementaria_metrica["certificados"] == 100
    assert data["complementaria_canales"]["presencial"] == 100
    assert data["complementaria_canales"]["virtual"] == 0
    # La fuente no reporta personas pendientes de complementaria: queda sin calcular.
    assert complementaria_metrica["pendientes"] is None
    assert complementaria_metrica["avance"] == 10.0


# ---------------------------------------------------------------------------
# 7. Reimportar el mismo archivo no duplica registros
# ---------------------------------------------------------------------------
def _certificados_xlsx(rows: list[dict]) -> bytes:
    """Construye un .xlsx de una sola hoja llamada CERTIFICADOS."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="CERTIFICADOS", index=False)
    return buffer.getvalue()


def test_reimportar_el_mismo_archivo_no_duplica(session_factory):
    content = _certificados_xlsx(
        [_certificado("5001", "TÉCNICO"), _certificado("5002", "TÉCNOLOGO")]
    )
    with session_factory() as session:
        primero = confirm_import(stage_file("ACTAS 2026.xlsx", content, "certificados").validation_id, session)
        segundo = confirm_import(stage_file("ACTAS 2026.xlsx", content, "certificados").validation_id, session)
        total_registros = (
            session.query(ImportedRecord)
            .filter(ImportedRecord.information_type == "certificados")
            .count()
        )

    assert primero["new_records"] == 2
    assert primero["updated_records"] == 0
    # La segunda importacion ACTUALIZA, no agrega filas nuevas.
    assert segundo["new_records"] == 0
    assert segundo["updated_records"] == 2
    assert total_registros == 2


# ---------------------------------------------------------------------------
# 8. Endpoint que consume el frontend
# ---------------------------------------------------------------------------
def test_endpoint_indicadores_responde_los_campos_esperados(client: TestClient):
    with client.session_factory() as session:
        _seed(session, "certificados", [_certificado("9001", "TECNÓLOGO", "JUNIO")])
        _seed(session, "meta", [_meta(superior=100, tecnica=200, articulacion=50, complementaria=1000)])

    response = client.get("/api/indicadores")
    assert response.status_code == 200
    data = response.json()

    for clave in (
        "periodo",
        "total_meta",
        "total_certificados",
        "total_pendientes",
        "avance_global",
        "metricas",
        "motivos",
        "sin_clasificar",
        "ultimas_actas",
        "advertencias",
        "datos_suficientes",
    ):
        assert clave in data, f"Falta el campo {clave} en la respuesta del endpoint"

    assert data["periodo"] == "Enero - Septiembre 2026"
    assert data["total_certificados"] == 1
