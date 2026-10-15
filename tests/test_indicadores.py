from __future__ import annotations

from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Act, ActLearner, Learner, Requirement
from app.services.indicadores import compute_indicadores_2026, normalize_identification


def test_normalize_identification():
    assert normalize_identification(" CC_123456 ") == "123456"
    assert normalize_identification("TI_987654") == "987654"
    assert normalize_identification("100200300") == "100200300"
    assert normalize_identification("PEP-4567") == "pep4567"


def test_indicadores_base_metas_and_categories(client: TestClient):
    """Verifica las 4 categorías de formación oficiales y sus metas institucionales."""
    response = client.get("/api/indicadores")
    assert response.status_code == 200
    data = response.json()

    assert data["periodo"] == "Enero - Septiembre 2026"
    assert data["total_meta"] == 8700

    metricas_by_cat = {m["category"]: m for m in data["metricas"]}
    assert set(metricas_by_cat.keys()) == {"superior", "tecnica", "articulacion", "complementaria"}

    # Metas institucionales auditadas
    assert metricas_by_cat["superior"]["meta"] == 1250
    assert metricas_by_cat["tecnica"]["meta"] == 2100
    assert metricas_by_cat["articulacion"]["meta"] == 850
    assert metricas_by_cat["complementaria"]["meta"] == 4500


def test_indicadores_pending_discrepancy_and_multiple_causes(client: TestClient):
    """
    Verifica la discrepancia técnica auditada:
    - 638 aprendices pendientes únicos distribuidos en las 4 categorías.
    - 639 incidencias de causas en la distribución de motivos.
    - Explicación: causas múltiples por aprendiz (concurrencia de requisitos).
    """
    response = client.get("/api/indicadores")
    assert response.status_code == 200
    data = response.json()

    # 1. Total de aprendices pendientes únicos
    metricas = {m["category"]: m for m in data["metricas"]}
    sum_pendientes_por_categoria = sum(m["pendientes"] for m in data["metricas"])
    assert sum_pendientes_por_categoria == 638
    assert data["total_pendientes"] == 638
    assert metricas["superior"]["pendientes"] == 142
    assert metricas["tecnica"]["pendientes"] == 218
    assert metricas["articulacion"]["pendientes"] == 88
    assert metricas["complementaria"]["pendientes"] == 190

    # 2. Total de incidencias sumadas en la distribución de causas
    sum_incidencias_causas = sum(m["cantidad"] for m in data["motivos"])
    assert sum_incidencias_causas == 639
    assert data["total_incidencias_causas"] == 639

    # 3. Diferencia exactamente explicada por concurrencia de causas múltiples
    assert data["aprendices_con_causas_multiples"] >= 1
    assert data["total_incidencias_causas"] - data["total_pendientes"] == 1


def test_indicadores_formulas_avance_brecha_efectividad(client: TestClient):
    """Verifica las fórmulas institucionales de % Avance, Brecha y Efectividad de cierre."""
    response = client.get("/api/indicadores")
    data = response.json()

    for m in data["metricas"]:
        cert = m["certificados"]
        meta = m["meta"]
        pend = m["pendientes"]

        # Fórmulas
        expected_avance = round((cert / meta) * 100, 1)
        expected_brecha = max(0, meta - cert)
        candidatos = cert + pend
        expected_efectividad = round((cert / candidatos) * 100, 1) if candidatos else 100.0

        assert m["avance"] == expected_avance
        assert m["brecha"] == expected_brecha
        assert m["efectividad"] == expected_efectividad


def test_indicadores_period_filter_and_real_act_associations(client: TestClient):
    """
    Verifica que:
    1. Las actas dentro del período (2026-01-01 a 2026-09-30) se incluyan.
    2. Las actas fuera de período (ej. octubre 2026 o diciembre 2025) se excluyan.
    3. El número de certificados por acta se compute de sus asociaciones reales en ActLearner.
    """
    with client.session_factory() as session:
        # Crear aprendices
        l1 = Learner(identification="1001", name="Learner 1", program="ADSO", training_type="Tecnólogo")
        l2 = Learner(identification="1002", name="Learner 2", program="ADSO", training_type="Tecnólogo")
        l3 = Learner(identification="1003", name="Learner 3", program="Cocina", training_type="Técnico")
        session.add_all([l1, l2, l3])
        session.commit()

        # Acta en período: 2026-05-10
        act_valida = Act(
            number="ACTA-2026-VAL",
            act_date=date(2026, 5, 10),
            act_type="Ordinaria",
            original_file="acta_mayo.docx",
            review_status="reviewed",
        )
        # Acta fuera de período: 2026-10-15
        act_fuera = Act(
            number="ACTA-2026-OUT",
            act_date=date(2026, 10, 15),
            act_type="Ordinaria",
            original_file="acta_octubre.docx",
            review_status="reviewed",
        )
        session.add_all([act_valida, act_fuera])
        session.commit()

        # Asociar l1 y l2 al acta válida (2 aprendices asociados)
        al1 = ActLearner(act_id=act_valida.id, learner_id=l1.id)
        al2 = ActLearner(act_id=act_valida.id, learner_id=l2.id)
        # Asociar l3 al acta fuera de período
        al3 = ActLearner(act_id=act_fuera.id, learner_id=l3.id)
        session.add_all([al1, al2, al3])
        session.commit()

    response = client.get("/api/indicadores")
    assert response.status_code == 200
    data = response.json()

    ultimas_actas = data["ultimas_actas"]
    act_numbers = [a["number"] for a in ultimas_actas]
    assert "ACTA-2026-VAL" in act_numbers
    assert "ACTA-2026-OUT" not in act_numbers

    act_val_info = next(a for a in ultimas_actas if a["number"] == "ACTA-2026-VAL")
    assert act_val_info["aprendices_count"] == 2


def test_indicadores_deduplication_of_certified_learners(client: TestClient):
    """
    Verifica que si un aprendiz está asociado a 2 actas en el período,
    solo se contabiliza 1 vez como aprendiz único certificado.
    """
    with client.session_factory() as session:
        l = Learner(
            identification="CC_777888",
            name="Aprendiz Unico",
            program="ADSO",
            training_type="Tecnólogo",
        )
        session.add(l)
        session.commit()

        act1 = Act(number="ACTA-01", act_date=date(2026, 2, 15), original_file="f1.docx", review_status="reviewed")
        act2 = Act(number="ACTA-02", act_date=date(2026, 3, 20), original_file="f2.docx", review_status="reviewed")
        session.add_all([act1, act2])
        session.commit()

        # Mismo aprendiz en dos actas distintas del período
        session.add(ActLearner(act_id=act1.id, learner_id=l.id))
        session.add(ActLearner(act_id=act2.id, learner_id=l.id))
        session.commit()

    res = client.get("/api/indicadores").json()
    sup = next(m for m in res["metricas"] if m["category"] == "superior")
    # Base superior es 890, con este aprendiz único debe ser exactamente 891 (no 892)
    assert sup["certificados"] == 891


def test_indicadores_termination_date_not_used_as_certification(session_factory):
    """
    Verifica la regla de precedencia y fechas:
    La fecha de terminación del programa NO es fecha de certificación.
    Un aprendiz con termination_date en 2026 pero sin acta en período no debe sumarse como certificado.
    """
    with session_factory() as session:
        l = Learner(
            identification="999888111",
            name="Learner Terminado Sin Acta",
            program="Cocina",
            training_type="Técnico",
            certification_status="Certificado",
            termination_date=date(2026, 4, 15),
        )
        session.add(l)
        session.commit()

        data = compute_indicadores_2026(session)
        tec = next(m for m in data["metricas"] if m["category"] == "tecnica")
        # Base tecnica es 1480; no debe ser 1481 porque carece de acta verificable en período
        assert tec["certificados"] == 1480


def test_indicadores_single_category_classification_and_formulas(session_factory):
    """
    Verifica que cada aprendiz pertenezca a exactamente una categoría en el cálculo global,
    y que los numeradores y denominadores de avance y efectividad se documenten.
    """
    with session_factory() as session:
        data = compute_indicadores_2026(session)

        # Sum of categories equals totals
        sum_cert = sum(m["certificados"] for m in data["metricas"])
        assert sum_cert == data["total_certificados"]

        sum_pend = sum(m["pendientes"] for m in data["metricas"])
        assert sum_pend == data["total_pendientes"]

        sum_meta = sum(m["meta"] for m in data["metricas"])
        assert sum_meta == data["total_meta"]

        # Check formula metadata present
        assert "formula_avance_global" in data
        assert "formula_efectividad_global" in data
        assert data["formula_avance_global"]["numerador"] == data["total_certificados"]
        assert data["formula_avance_global"]["denominador"] == data["total_meta"]

        for m in data["metricas"]:
            assert m["formula_avance"]["numerador"] == m["certificados"]
            assert m["formula_avance"]["denominador"] == m["meta"]
            assert m["formula_efectividad"]["numerador"] == m["certificados"]
            assert m["formula_efectividad"]["denominador"] == m["certificados"] + m["pendientes"]

