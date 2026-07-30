import json

import pytest

from src.ni_model.api.routes.simulation import (
    SimulationYearSnapshot,
    _year_snapshots,
    store_results,
)


@pytest.fixture(autouse=True)
def clear_snapshots():
    """Ensure simulation store is clean before each test"""
    _year_snapshots.clear()
    yield
    _year_snapshots.clear()


def _make_snapshot(year: int, total: int = 100) -> SimulationYearSnapshot:
    return SimulationYearSnapshot(
        year=year,
        total_population=total,
        religious_breakdown={"catholic": 50, "protestant": 30, "other": 20},
        gender_breakdown={"male": 50, "female": 50},
        location_breakdown={"belfast_north": total},
    )


def test_simulation_years_empty(client):
    response = client.get("/api/simulation/years")
    assert response.status_code == 200
    assert response.json() == {"years": []}


def test_simulation_years_after_store(client):
    _year_snapshots[2024] = _make_snapshot(2024)
    _year_snapshots[2025] = _make_snapshot(2025)

    data = client.get("/api/simulation/years").json()
    assert data["years"] == [2024, 2025]


def test_simulation_year_snapshot_found(client):
    _year_snapshots[2024] = _make_snapshot(2024, total=150)

    response = client.get("/api/simulation/years/2024")
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2024
    assert data["total_population"] == 150


def test_simulation_year_snapshot_not_found(client):
    response = client.get("/api/simulation/years/1999")
    assert response.status_code == 404


def test_simulation_year_snapshot_schema(client):
    _year_snapshots[2026] = _make_snapshot(2026)

    data = client.get("/api/simulation/years/2026").json()
    assert "religious_breakdown" in data
    assert "gender_breakdown" in data
    assert "location_breakdown" in data


def test_simulation_year_snapshot_with_result(client):
    from src.ni_model.api.schemas import SimulationYearResult

    snapshot = _make_snapshot(2024)
    snapshot.simulation_result = SimulationYearResult(
        year=2024, births=10, deaths=5, migration=2, internal_migration=8, net_change=7
    )
    _year_snapshots[2024] = snapshot

    data = client.get("/api/simulation/years/2024").json()
    assert data["simulation_result"]["births"] == 10
    assert data["simulation_result"]["net_change"] == 7


def test_store_results_populates_snapshots(client):
    results = [
        {
            "year": 2024,
            "births": 5,
            "deaths": 3,
            "migration": 1,
            "internal_migration": 4,
            "net_change": 3,
        }
    ]
    snapshots = {2024: _make_snapshot(2024, total=200)}
    store_results(results, None, snapshots)

    assert 2024 in _year_snapshots
    assert _year_snapshots[2024].total_population == 200


def test_run_simulation_invalid_model_path(client):
    response = client.post(
        "/api/simulation/run",
        json={
            "model_path": "models/nonexistent.yaml",
            "start_year": 2024,
            "end_year": 2025,
        },
    )
    assert response.status_code == 422


def test_run_simulation_end_before_start(client):
    response = client.post(
        "/api/simulation/run",
        json={
            "model_path": "models/ni_base_2024.yaml",
            "start_year": 2025,
            "end_year": 2024,
        },
    )
    assert response.status_code == 422


def test_run_simulation_year_out_of_range(client):
    response = client.post(
        "/api/simulation/run",
        json={
            "model_path": "models/ni_base_2024.yaml",
            "start_year": 1800,
            "end_year": 1801,
        },
    )
    assert response.status_code == 422


def test_run_simulation_defaults(client):
    """POST with no body uses defaults and runs against populated_db"""
    response = client.post("/api/simulation/run", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["model_path"] == "models/ni_base_2024.yaml"
    assert data["start_year"] == 2024
    assert data["end_year"] == 2030
    assert data["years_simulated"] == 7
    assert len(data["results"]) == 7


def test_run_simulation_response_schema(client):
    response = client.post(
        "/api/simulation/run",
        json={"start_year": 2024, "end_year": 2026},
    )
    assert response.status_code == 200
    data = response.json()
    expected_keys = {
        "model_path",
        "start_year",
        "end_year",
        "years_simulated",
        "results",
    }
    assert set(data.keys()) == expected_keys
    result_keys = {
        "year",
        "births",
        "deaths",
        "migration",
        "internal_migration",
        "net_change",
    }
    for r in data["results"]:
        assert set(r.keys()) == result_keys


def test_run_simulation_populates_snapshot_store(client):
    client.post("/api/simulation/run", json={"start_year": 2024, "end_year": 2025})
    response = client.get("/api/simulation/years")
    assert 2024 in response.json()["years"]
    assert 2025 in response.json()["years"]


def _parse_sse(text: str) -> list:
    """Parse SSE response body into list of (event, data) tuples"""
    events = []
    current = {}
    for line in text.splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line[len("data:") :].strip())
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def test_stream_emits_one_event_per_year(client):
    response = client.get("/api/simulation/stream?start_year=2024&end_year=2026")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    events = _parse_sse(response.text)
    # 3 year data events + 1 complete event
    assert len(events) == 4


def test_stream_year_event_schema(client):
    response = client.get("/api/simulation/stream?start_year=2024&end_year=2024")
    events = _parse_sse(response.text)
    year_event = events[0]["data"]
    assert year_event["year"] == 2024
    assert "total_population" in year_event
    assert "religious_breakdown" in year_event
    assert "gender_breakdown" in year_event
    assert "location_breakdown" in year_event
    assert "simulation_result" in year_event


def test_stream_complete_event(client):
    response = client.get("/api/simulation/stream?start_year=2024&end_year=2025")
    events = _parse_sse(response.text)
    last = events[-1]
    assert last.get("event") == "complete"


def test_stream_invalid_model_path(client):
    response = client.get(
        "/api/simulation/stream?model_path=models/missing.yaml"
        "&start_year=2024&end_year=2025"
    )
    assert response.status_code == 422


def test_stream_rejects_model_path_outside_models_directory(client):
    response = client.get(
        "/api/simulation/stream?model_path=project-goals.md"
        "&start_year=2024&end_year=2025"
    )
    assert response.status_code == 422
    assert "models/" in response.json()["detail"]


def test_stream_end_before_start(client):
    response = client.get("/api/simulation/stream?start_year=2025&end_year=2024")
    assert response.status_code == 422


def test_stream_year_out_of_range(client):
    response = client.get("/api/simulation/stream?start_year=1800&end_year=1801")
    assert response.status_code == 422
