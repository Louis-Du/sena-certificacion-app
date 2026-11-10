"""Pruebas del rediseño de "Resolver conflicto" para requisitos y evidencias.

Cubren las reglas de detección, los grupos del modal, las decisiones
explícitas, la auditoría y la reapertura por cambio de huella. La UI se prueba
aparte con el contrato estático de ``test_conflict_banner_ui.py``; aquí se usa
la API real para comprobar que el backend aplica lo que la UI envía.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from app.models import Learner, RequirementStatusHistory
from app.services.requirement_conflicts import (
    conflict_fingerprint,
    requirement_for_cause,
)
from app.services.requirements import evidence_status

DOCUMENTO = "NÚMERO DE DOCUMENTO"
NOMBRE = "NOMBRE"
FICHA = "FICHA"
NIVEL = "NIVEL"
ESTADO = "ESTADO"
MOTIVO = "MOTIVO DE NO CERTIFICACION"
DOCUMENTO_IDENTIDAD = "Copia del Documento de Identidad vigente"
SABER_TYT = "Evidencia de la presentación de las pruebas Saber T y T. ( SOLO TGO)"
CARNET = "Comprobante de Destrucción de Carnet."
CONFLICT_SOURCE = "conflict:requirement"


def _workbook(
    certificados: list[dict] | None = None,
    pendientes: list[dict] | None = None,
) -> bytes:
    """Genera un paquete ACTAS mínimo con las dos hojas del cruce."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(certificados or []).to_excel(
            writer, sheet_name="CERTIFICADOS", index=False
        )
        pd.DataFrame(pendientes or []).to_excel(
            writer, sheet_name="PENDIENTES", index=False
        )
    return buffer.getvalue()


def _validate(client: TestClient, content: bytes, name: str = "ACTAS_2026.xlsx") -> dict:
    response = client.post(
        "/api/files/validate",
        data={"information_type": "actas_completo"},
        files={"file": (name, content, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validation_id"]
    return body


def _preview(client: TestClient, validation_id: str) -> dict:
    response = client.get(f"/api/imports/{validation_id}/preview")
    assert response.status_code == 200, response.text
    return response.json()


def _confirm(
    client: TestClient,
    validation_id: str,
    requirement_resolutions: list[dict] | None = None,
    conflict_resolutions: list[dict] | None = None,
):
    payload = {
        "accept_missing_complementaria": True,
        "requirement_conflict_resolutions": requirement_resolutions or [],
        "conflict_resolutions": conflict_resolutions or [],
    }
    return client.post(f"/api/imports/{validation_id}/confirm", json=payload)


def _one_conflict(body: dict, requirement_type: str) -> dict:
    items = [
        item
        for item in body["requirement_conflicts"]
        if item["requirement_type"] == requirement_type
    ]
    assert len(items) == 1, body["requirement_conflicts"]
    return items[0]


def _decision(item: dict, status: str, source: str = "user", fingerprint: str | None = None) -> dict:
    return {
        "identification": item["identification"],
        "requirement_type": item["requirement_type"],
        "status": status,
        "source": source,
        "conflict_fingerprint": fingerprint or item["fingerprint"],
    }


def _learner(client: TestClient, identification: str) -> Learner:
    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification=identification).one()
        session.expunge(learner)
        return learner


def _requirement_history(
    client: TestClient, identification: str, requirement_type: str
) -> list[dict]:
    learner = _learner(client, identification)
    detail = client.get(f"/api/learners/{learner.id}").json()
    return [
        event
        for event in detail["requirement_history"]
        if event["requirement_type"] == requirement_type
        and event["source"] == CONFLICT_SOURCE
    ]


def _requirement_status(client: TestClient, identification: str, requirement_type: str) -> str | None:
    learner = _learner(client, identification)
    detail = client.get(f"/api/learners/{learner.id}").json()
    for requirement in detail["requirements"]:
        if requirement["requirement_type"] == requirement_type:
            return requirement["status"]
    return None


def _pendiente(
    identification: str,
    *,
    nivel: str = "Tecnólogo",
    nombre: str = "Aprendiz de prueba",
    ficha: str = "3001",
    **evidence: str,
) -> dict:
    row = {
        DOCUMENTO: identification,
        NOMBRE: nombre,
        FICHA: ficha,
        NIVEL: nivel,
        ESTADO: "Pendiente Documento",
    }
    row.update(evidence)
    return row


def test_evidence_status_blank_is_missing_information_not_pending():
    assert evidence_status(None) == "Sin información"
    assert evidence_status("") == "Sin información"
    assert evidence_status("   ") == "Sin información"
    assert evidence_status("X") == "Cumplido"
    assert evidence_status("N.A.") == "No aplica"
    assert evidence_status("Pendiente") == "Pendiente"


def test_requirement_for_cause_does_not_invent_requirement():
    assert requirement_for_cause("No anexa T&T") == "saber_tyt"
    assert requirement_for_cause("Documento vencido") == "documento_identidad"
    assert requirement_for_cause("Destrucción del carnet") == "carnet"
    assert requirement_for_cause("No ha remitido documentos") is None
    assert requirement_for_cause("") is None


def test_fingerprint_is_stable_and_changes_with_the_contrast():
    first = conflict_fingerprint(
        "saber_tyt", "X", "Cumplido", "No anexa T&T", "Tecnólogo"
    )
    same = conflict_fingerprint(
        "saber_tyt", "x", "Cumplido", " no anexa T&T ", "Tecnólogo"
    )
    other_nivel = conflict_fingerprint(
        "saber_tyt", "X", "Cumplido", "No anexa T&T", "Técnico"
    )
    other_motivo = conflict_fingerprint(
        "saber_tyt", "X", "Cumplido", "No anexa T&T", "Tecnólogo"
    )[:-1] + "0"

    assert first == same
    assert first != other_nivel
    assert first != other_motivo
    assert len(first) == 20


def test_tyt_blank_non_tgo_is_auto_rule_and_does_not_block(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7001",
                nivel="Técnico",
                nombre="Aprendiz Técnico",
                **{SABER_TYT: ""},
            )
        ]
    )
    body = _validate(client, content)

    conflict = _one_conflict(body, "saber_tyt")
    assert conflict["pattern"] == "tyt_not_applicable_level"
    assert conflict["group"] == "high"
    assert conflict["suggested_status"] == "No aplica"
    assert conflict["auto_resolved"] is True
    assert conflict["evidence_status"] == "Sin información"
    assert conflict["level_applies"] is False

    summary = body["requirement_conflict_summary"]
    assert summary["total"] == 1
    assert summary["auto_resolved"] == 1
    assert summary["requires_decision"] == 0
    assert summary["groups"] == {"high": 1, "medium": 0, "review": 0}

    preview = _preview(client, body["validation_id"])
    assert preview["requirement_conflict_summary"]["unresolved"] == 0
    assert preview["requirement_conflict_summary"]["resolved_saved"] == 0

    # No envía decisiones: la regla automática no bloquea la confirmación.
    confirmed = _confirm(client, body["validation_id"])
    assert confirmed.status_code == 200, confirmed.text
    assert "1 por regla automática" in confirmed.json()["message"]

    assert _requirement_status(client, "7001", "saber_tyt") == "No aplica"
    events = _requirement_history(client, "7001", "saber_tyt")
    assert len(events) == 1
    assert events[0]["status"] == "No aplica"
    assert events[0]["decision_source"] == "rule"
    assert events[0]["conflict_fingerprint"] == conflict["fingerprint"]
    assert "Origen: Regla automática" in events[0]["note"]
    assert "Columna: «vacía» (Sin información)" in events[0]["note"]


def test_fulfilled_with_motive_requires_decision_and_records_audit(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7002",
                nombre="Aprendiz TyT",
                **{SABER_TYT: "X", MOTIVO: "No anexa T&T"},
            )
        ]
    )
    body = _validate(client, content)

    conflict = _one_conflict(body, "saber_tyt")
    assert conflict["pattern"] == "evidence_fulfilled_motivo_missing"
    assert conflict["group"] == "high"
    assert conflict["suggested_status"] == "Pendiente"
    assert conflict["auto_resolved"] is False
    assert conflict["motivo_mentions"] is True
    assert conflict["evidence_status"] == "Cumplido"

    summary = body["requirement_conflict_summary"]
    assert summary["total"] == 1
    assert summary["requires_decision"] == 1
    assert summary["groups"]["high"] == 1

    blocked = _confirm(client, body["validation_id"])
    assert blocked.status_code == 400
    assert "Faltan 1 resolucion(es) de requisito" in blocked.json()["detail"]

    preview = _preview(client, body["validation_id"])
    assert preview["requirement_conflict_summary"]["unresolved"] == 1
    assert preview["requirement_conflict_resolutions"] == {}

    confirmed = _confirm(
        client,
        body["validation_id"],
        [_decision(conflict, "Pendiente", source="user")],
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "1 con decisión manual/lote" in confirmed.json()["message"]

    assert _requirement_status(client, "7002", "saber_tyt") == "Pendiente"
    events = _requirement_history(client, "7002", "saber_tyt")
    assert events[0]["status"] == "Pendiente"
    assert events[0]["decision_source"] == "user"
    assert events[0]["conflict_fingerprint"] == conflict["fingerprint"]
    assert "Origen: Usuario" in events[0]["note"]
    assert "Columna: «X» (Cumplido)" in events[0]["note"]
    assert "Motivo: «No anexa T&T»" in events[0]["note"]
    assert "Lote: ACTAS_2026.xlsx" in events[0]["note"]


def test_na_with_motive_is_review_group_without_strong_suggestion(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7003",
                **{SABER_TYT: "N.A", MOTIVO: "No anexa T&T"},
            )
        ]
    )
    body = _validate(client, content)

    conflict = _one_conflict(body, "saber_tyt")
    assert conflict["pattern"] == "evidence_na_motivo_missing"
    assert conflict["group"] == "review"
    assert conflict["suggested_status"] is None
    assert conflict["auto_resolved"] is False
    assert conflict["evidence_status"] == "No aplica"

    summary = body["requirement_conflict_summary"]
    assert summary["groups"] == {"high": 0, "medium": 0, "review": 1}
    assert summary["requires_decision"] == 1

    assert _confirm(client, body["validation_id"]).status_code == 400
    confirmed = _confirm(
        client,
        body["validation_id"],
        [_decision(conflict, "Pendiente", source="bulk")],
    )
    assert confirmed.status_code == 200, confirmed.text

    assert _requirement_status(client, "7003", "saber_tyt") == "Pendiente"
    events = _requirement_history(client, "7003", "saber_tyt")
    assert events[0]["decision_source"] == "bulk"
    assert "Origen: Acción por lote" in events[0]["note"]


def test_blank_without_motive_mention_does_not_create_a_conflict(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7004",
                **{
                    MOTIVO: "Destrucción del carnet",
                    DOCUMENTO_IDENTIDAD: "",
                    SABER_TYT: "",
                    CARNET: "Pendiente",
                },
            )
        ]
    )
    body = _validate(client, content)

    # El carnet está Pendiente y el motivo coincide; las demás celdas vacías no
    # son una contradicción porque el motivo no las nombra.
    assert body["requirement_conflicts"] == []
    assert body["requirement_conflict_summary"]["total"] == 0

    confirmed = _confirm(client, body["validation_id"])
    assert confirmed.status_code == 200, confirmed.text

    assert _requirement_status(client, "7004", "carnet") == "Pendiente"
    assert _requirement_status(client, "7004", "documento_identidad") == "Sin información"
    assert _requirement_status(client, "7004", "saber_tyt") == "Sin información"


def test_blank_with_motive_mention_is_medium_and_audits_bulk_source(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7005",
                **{
                    MOTIVO: "Documento de identidad vencido",
                    DOCUMENTO_IDENTIDAD: "",
                },
            )
        ]
    )
    body = _validate(client, content)

    conflict = _one_conflict(body, "documento_identidad")
    assert conflict["pattern"] == "evidence_blank_motivo_missing"
    assert conflict["group"] == "medium"
    assert conflict["suggested_status"] == "Pendiente"
    assert conflict["auto_resolved"] is False
    assert conflict["evidence_status"] == "Sin información"
    assert body["requirement_conflict_summary"]["groups"]["medium"] == 1
    assert body["requirement_conflict_summary"]["requires_decision"] == 1

    assert _confirm(client, body["validation_id"]).status_code == 400
    confirmed = _confirm(
        client,
        body["validation_id"],
        [_decision(conflict, "Pendiente", source="bulk")],
    )
    assert confirmed.status_code == 200, confirmed.text

    assert _requirement_status(client, "7005", "documento_identidad") == "Pendiente"
    events = _requirement_history(client, "7005", "documento_identidad")
    assert events[0]["decision_source"] == "bulk"
    assert "Columna: «vacía» (Sin información)" in events[0]["note"]


def test_summary_counts_groups_rules_and_unresolved(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7101",
                nombre="Caso alto",
                **{SABER_TYT: "X", MOTIVO: "No anexa T&T"},
            ),
            _pendiente(
                "7102",
                nombre="Caso medio",
                **{DOCUMENTO_IDENTIDAD: "", MOTIVO: "Documento de identidad vencido"},
            ),
            _pendiente(
                "7103",
                nombre="Caso revisión",
                **{SABER_TYT: "N.A", MOTIVO: "No anexa T&T"},
            ),
            _pendiente(
                "7104",
                nombre="Caso TyT automático",
                nivel="Técnico",
                **{SABER_TYT: ""},
            ),
        ]
    )
    body = _validate(client, content)

    summary = body["requirement_conflict_summary"]
    assert summary["total"] == 4
    assert summary["auto_resolved"] == 1
    assert summary["requires_decision"] == 3
    assert summary["groups"] == {"high": 2, "medium": 1, "review": 1}
    assert summary["patterns"] == {
        "evidence_fulfilled_motivo_missing": 1,
        "evidence_blank_motivo_missing": 1,
        "evidence_na_motivo_missing": 1,
        "tyt_not_applicable_level": 1,
    }

    preview = _preview(client, body["validation_id"])
    assert preview["requirement_conflict_summary"]["unresolved"] == 3
    assert preview["requirement_conflict_summary"]["resolved_saved"] == 0

    # Los tres conflictos manuales bloquean aunque la regla automática ya tenga
    # una respuesta del backend.
    assert _confirm(client, body["validation_id"]).status_code == 400


def test_saved_decision_is_reapplied_without_asking_again(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7201",
                nombre="Aprendiz Guardado",
                **{SABER_TYT: "X", MOTIVO: "No anexa T&T"},
            )
        ]
    )
    first = _validate(client, content)
    conflict = _one_conflict(first, "saber_tyt")
    confirmed = _confirm(
        client,
        first["validation_id"],
        [_decision(conflict, "Pendiente", source="user")],
    )
    assert confirmed.status_code == 200, confirmed.text

    replay = _validate(client, content)
    replay_conflict = _one_conflict(replay, "saber_tyt")
    key = f"7201|saber_tyt"
    preview = _preview(client, replay["validation_id"])
    assert preview["requirement_conflict_resolutions"][key] == "Pendiente"
    assert preview["requirement_conflict_resolution_sources"][key] == "user"
    assert (
        preview["requirement_conflict_resolution_fingerprints"][key]
        == replay_conflict["fingerprint"]
    )
    assert preview["requirement_conflict_summary"]["resolved_saved"] == 1
    assert preview["requirement_conflict_summary"]["unresolved"] == 0

    # No se envía la decisión: el backend reaplica la guardada.
    second = _confirm(client, replay["validation_id"])
    assert second.status_code == 200, second.text
    assert "guardadas reaplicadas" in second.json()["message"]

    assert _requirement_status(client, "7201", "saber_tyt") == "Pendiente"
    events = _requirement_history(client, "7201", "saber_tyt")
    assert len(events) == 1
    assert events[0]["decision_source"] == "user"
    assert events[0]["conflict_fingerprint"] == replay_conflict["fingerprint"]


def test_explicit_decision_overrides_saved_decision(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7301",
                nombre="Aprendiz Override",
                **{SABER_TYT: "X", MOTIVO: "No anexa T&T"},
            )
        ]
    )
    first = _validate(client, content)
    conflict = _one_conflict(first, "saber_tyt")
    assert _confirm(
        client,
        first["validation_id"],
        [_decision(conflict, "Pendiente", source="user")],
    ).status_code == 200

    override = _validate(client, content)
    override_conflict = _one_conflict(override, "saber_tyt")
    preview = _preview(client, override["validation_id"])
    assert preview["requirement_conflict_resolutions"]["7301|saber_tyt"] == "Pendiente"

    confirmed = _confirm(
        client,
        override["validation_id"],
        [_decision(override_conflict, "Cumplido", source="user")],
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "1 con decisión manual/lote" in confirmed.json()["message"]

    assert _requirement_status(client, "7301", "saber_tyt") == "Cumplido"
    events = _requirement_history(client, "7301", "saber_tyt")
    assert [event["status"] for event in events[:2]] == ["Cumplido", "Pendiente"]
    assert all(event["decision_source"] == "user" for event in events[:2])


def test_changed_motive_reopens_conflict_and_rejects_stale_fingerprint(client: TestClient):
    first_content = _workbook(
        pendientes=[
            _pendiente(
                "7401",
                nombre="Aprendiz Reabierto",
                **{
                    DOCUMENTO_IDENTIDAD: "",
                    MOTIVO: "Documento de identidad vencido",
                },
            )
        ]
    )
    first = _validate(client, first_content)
    old_conflict = _one_conflict(first, "documento_identidad")
    assert _confirm(
        client,
        first["validation_id"],
        [_decision(old_conflict, "Pendiente", source="user")],
    ).status_code == 200

    # El mismo requisito sigue en conflicto, pero el motivo cambió: el hecho ya
    # no es el mismo y la decisión anterior no debe reutilizarse.
    second_content = _workbook(
        pendientes=[
            _pendiente(
                "7401",
                nombre="Aprendiz Reabierto",
                **{
                    DOCUMENTO_IDENTIDAD: "",
                    MOTIVO: "No anexa documento de identidad",
                },
            )
        ]
    )
    second = _validate(client, second_content)
    new_conflict = _one_conflict(second, "documento_identidad")
    assert new_conflict["fingerprint"] != old_conflict["fingerprint"]

    preview = _preview(client, second["validation_id"])
    assert "7401|documento_identidad" not in preview["requirement_conflict_resolutions"]
    assert preview["requirement_conflict_summary"]["resolved_saved"] == 0
    assert preview["requirement_conflict_summary"]["unresolved"] == 1
    assert _confirm(client, second["validation_id"]).status_code == 400

    stale = _confirm(
        client,
        second["validation_id"],
        [_decision(new_conflict, "Pendiente", source="user", fingerprint=old_conflict["fingerprint"])],
    )
    assert stale.status_code == 400
    assert "El conflicto cambió desde que se abrió el modal" in stale.json()["detail"]

    confirmed = _confirm(
        client,
        second["validation_id"],
        [_decision(new_conflict, "Cumplido", source="user")],
    )
    assert confirmed.status_code == 200, confirmed.text

    assert _requirement_status(client, "7401", "documento_identidad") == "Cumplido"
    events = _requirement_history(client, "7401", "documento_identidad")
    assert len(events) == 2
    assert events[0]["status"] == "Cumplido"
    assert events[0]["conflict_fingerprint"] == new_conflict["fingerprint"]
    assert events[1]["status"] == "Pendiente"
    assert events[1]["conflict_fingerprint"] == old_conflict["fingerprint"]


def test_human_decision_on_auto_rule_is_kept_on_reimport(client: TestClient):
    content = _workbook(
        pendientes=[
            _pendiente(
                "7501",
                nivel="Técnico",
                nombre="Aprendiz Regla",
                **{SABER_TYT: ""},
            )
        ]
    )
    first = _validate(client, content)
    conflict = _one_conflict(first, "saber_tyt")
    assert conflict["auto_resolved"] is True

    # Aunque la regla propone No aplica, la persona puede elegir otra cosa.
    confirmed = _confirm(
        client,
        first["validation_id"],
        [_decision(conflict, "Pendiente", source="user")],
    )
    assert confirmed.status_code == 200, confirmed.text
    assert "1 con decisión manual/lote" in confirmed.json()["message"]
    assert _requirement_status(client, "7501", "saber_tyt") == "Pendiente"

    replay = _validate(client, content)
    replay_conflict = _one_conflict(replay, "saber_tyt")
    preview = _preview(client, replay["validation_id"])
    assert preview["requirement_conflict_resolutions"]["7501|saber_tyt"] == "Pendiente"
    assert preview["requirement_conflict_resolution_sources"]["7501|saber_tyt"] == "user"

    second = _confirm(client, replay["validation_id"])
    assert second.status_code == 200, second.text
    assert _requirement_status(client, "7501", "saber_tyt") == "Pendiente"

    events = _requirement_history(client, "7501", "saber_tyt")
    assert len(events) == 1
    assert events[0]["status"] == "Pendiente"
    assert events[0]["decision_source"] == "user"
    assert events[0]["conflict_fingerprint"] == replay_conflict["fingerprint"]