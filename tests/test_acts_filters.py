"""Filtros de actas disponibles en el backend: `search` y `review_status`."""
import pytest


@pytest.fixture
def acts_client(client):
    rows = [
        ("ACT-001", "2026-09-01", "Titulada", "pending", "acta_titulada.pdf"),
        ("ACT-002", "2026-09-08", "Titulada", "reviewed", "acta_2.docx"),
        ("ACT-003", "2026-09-15", "Complementaria", "reviewed", "complementaria.pdf"),
        ("ACT-004", "2026-09-22", "Complementaria", "rejected", "acta_4.pdf"),
    ]
    for number, act_date, act_type, status, original_file in rows:
        response = client.post(
            "/api/acts",
            json={"number": number, "act_date": act_date, "act_type": act_type,
                  "review_status": status, "original_file": original_file},
        )
        assert response.status_code == 201
    return client


def numbers(client, **params) -> list[str]:
    response = client.get("/api/acts", params=params)
    assert response.status_code == 200
    return [item["number"] for item in response.json()["items"]]


@pytest.mark.parametrize(
    ("status", "expected"),
    [("pending", ["ACT-001"]), ("reviewed", ["ACT-003", "ACT-002"]), ("rejected", ["ACT-004"])],
)
def test_review_status_filter_returns_only_matching_acts(acts_client, status, expected):
    assert sorted(numbers(acts_client, review_status=status)) == sorted(expected)


def test_empty_review_status_means_no_filter(acts_client):
    assert len(numbers(acts_client, review_status="")) == 4
    assert len(numbers(acts_client)) == 4


def test_search_and_review_status_combine_with_and(acts_client):
    assert numbers(acts_client, search="Complementaria", review_status="reviewed") == ["ACT-003"]
    assert numbers(acts_client, search="Titulada", review_status="rejected") == []


def test_search_matches_number_type_and_original_file(acts_client):
    assert numbers(acts_client, search="ACT-002") == ["ACT-002"]
    assert sorted(numbers(acts_client, search="complementaria")) == ["ACT-003", "ACT-004"]
    assert numbers(acts_client, search="acta_titulada") == ["ACT-001"]


def test_unknown_review_status_is_rejected_with_400(acts_client):
    response = acts_client.get("/api/acts", params={"review_status": "inventado"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Estado de revisión no válido."


def test_acts_are_ordered_by_most_recent_date_first(acts_client):
    assert numbers(acts_client) == ["ACT-004", "ACT-003", "ACT-002", "ACT-001"]


def test_number_filter_matches_partial_number(acts_client):
    assert numbers(acts_client, number="002") == ["ACT-002"]


def test_date_range_filter_is_inclusive(acts_client):
    assert numbers(acts_client, date_from="2026-09-08", date_to="2026-09-15") == [
        "ACT-003",
        "ACT-002",
    ]
    assert numbers(acts_client, date_from="2026-09-20") == ["ACT-004"]
    assert numbers(acts_client, date_to="2026-09-01") == ["ACT-001"]


def test_inverted_date_range_is_rejected_with_400(acts_client):
    response = acts_client.get(
        "/api/acts", params={"date_from": "2026-09-20", "date_to": "2026-09-01"}
    )
    assert response.status_code == 400
    assert "posterior" in response.json()["detail"]
