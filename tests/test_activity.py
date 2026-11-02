from datetime import date, datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ImportHistory, Learner, RequirementStatusHistory
from app.services.activity import build_activity_heatmap, learners_for_activity_date


def test_build_activity_heatmap_structure(db_session: Session):
    result = build_activity_heatmap(db_session, year=2026)
    assert result["year"] == 2026
    assert "days" in result
    assert len(result["days"]) == 365
    assert result["days"][0]["date"] == "2026-01-01"
    assert result["days"][-1]["date"] == "2026-12-31"


def test_activity_with_history_and_imports(db_session: Session):
    # Create test learner
    learner = Learner(
        identification="TEST-ACT-001",
        name="ACTIVIDAD APRENDIZ TEST",
        certification_status="CERTIFICADO",
    )
    db_session.add(learner)
    db_session.flush()

    # Add requirement status history event
    target_date = datetime(2026, 4, 15, 10, 30, tzinfo=timezone.utc)
    history = RequirementStatusHistory(
        learner_id=learner.id,
        requirement_type="ETAPA PRODUCTIVA",
        status="CUMPLE",
        recorded_at=target_date,
        source="Test",
    )
    db_session.add(history)

    # Add import event
    import_record = ImportHistory(
        file_name="ACTAS_TEST.xlsx",
        information_type="actas",
        imported_at=target_date,
        new_records=5,
        updated_records=2,
        status="confirmed",
    )
    db_session.add(import_record)
    db_session.commit()

    # Verify heatmap counts for 2026-04-15
    heatmap = build_activity_heatmap(db_session, year=2026)
    day_entry = next((d for d in heatmap["days"] if d["date"] == "2026-04-15"), None)
    assert day_entry is not None
    assert day_entry["count"] > 0
    assert day_entry["level"] >= 1
    assert day_entry["sources"].get("status_changes") == 1
    assert day_entry["sources"].get("imports") == 1

    # Verify learners for activity date
    day_data = learners_for_activity_date(db_session, date(2026, 4, 15))
    assert day_data["date"] == "2026-04-15"
    assert day_data["learner_count"] >= 1
    assert any(l["id"] == learner.id for l in day_data["learners"])
    assert any(i["file_name"] == "ACTAS_TEST.xlsx" for i in day_data["imports"])


def test_api_activity_endpoints(client: TestClient):
    res_heat = client.get("/api/activity/heatmap?year=2026")
    assert res_heat.status_code == 200
    data_heat = res_heat.json()
    assert data_heat["year"] == 2026
    assert len(data_heat["days"]) == 365

    res_day = client.get("/api/activity/day/2026-04-15")
    assert res_day.status_code == 200
    data_day = res_day.json()
    assert data_day["date"] == "2026-04-15"
    assert "learners" in data_day
    assert "imports" in data_day
