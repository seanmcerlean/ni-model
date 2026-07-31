import json
import uuid

from src.ni_model.core.models import Person, SimulationRun, SimulationSnapshot


def _parse_sse(text: str) -> list:
    events = []
    current = {}
    for line in text.splitlines():
        if line.startswith("event:"):
            current["event"] = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.removeprefix("data:").strip())
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def test_simulation_models_describes_available_configs(client):
    response = client.get("/api/simulation/models")

    assert response.status_code == 200
    models = response.json()
    assert models[0]["path"] == "models/ni_base_2024.yaml"
    assert models[0]["name"] == "NI Historical Model"
    assert models[0]["birth_rules"] == 12
    assert models[0]["birth_rate_rules"][0]["rate"] == 26.0
    assert models[0]["default_start_year"] == 1969
    assert models[0]["default_end_year"] == 2024

    current = next(model for model in models if model["id"] == "ni_current")
    assert current["baseline_year"] == 2021
    assert current["data_through"] == 2024
    assert current["projection_version"] == "NISRA/ONS 2024-based principal projection"
    assert current["year_min"] == 2022
    assert current["year_max"] == 2074
    assert current["birth_rules"] == 53
    assert current["migration_rules"] == 103
    assert current["internal_migration_rules"] == 110
    assert current["default_start_year"] == 2024
    assert current["default_end_year"] == 2035
    assert current["migration_rate_rules"][3]["flow"] == "in"

    community = next(model for model in models if model["id"] == "ni_current_community")
    assert community["birth_rules"] == current["birth_rules"] * 4
    assert community["death_rules"] == current["death_rules"] * 4
    assert community["migration_rules"] == current["migration_rules"] * 4
    assert community["default_start_year"] == 2024
    assert community["default_end_year"] == 2050
    assert "not an official projection" in community["description"]
    assert {
        rule["filters"]["religious_background"]
        for rule in community["birth_rate_rules"]
    } == {"CATHOLIC", "PROTESTANT", "OTHER", "NONE"}


def test_runs_empty_initially(client):
    response = client.get("/api/simulation/runs")

    assert response.status_code == 200
    assert response.json() == []


def test_run_creates_isolated_population_and_durable_snapshots(client, populated_db):
    baseline_count = populated_db.query(Person).filter(Person.run_id.is_(None)).count()

    response = client.post(
        "/api/simulation/run",
        json={"start_year": 2024, "end_year": 2025},
    )

    assert response.status_code == 200
    data = response.json()
    run_id = uuid.UUID(data["run_id"])
    assert data["status"] == "complete"
    assert data["years_simulated"] == 2
    assert (
        populated_db.query(Person).filter(Person.run_id.is_(None)).count()
        == baseline_count
    )
    assert populated_db.query(Person).filter(Person.run_id == run_id).count() > 0
    assert (
        populated_db.query(SimulationSnapshot)
        .filter(SimulationSnapshot.run_id == run_id)
        .count()
        == 2
    )


def test_current_model_can_be_selected_for_a_run(client):
    response = client.post(
        "/api/simulation/run",
        json={
            "model_path": "models/ni_current.yaml",
            "start_year": 2025,
            "end_year": 2025,
        },
    )

    assert response.status_code == 200
    assert response.json()["model_path"] == "models/ni_current.yaml"
    assert response.json()["status"] == "complete"


def test_community_differentiated_model_can_be_selected(client):
    response = client.post(
        "/api/simulation/run",
        json={
            "model_path": "models/ni_current_community.yaml",
            "start_year": 2025,
            "end_year": 2025,
        },
    )

    assert response.status_code == 200
    assert response.json()["model_path"] == "models/ni_current_community.yaml"


def test_run_adjustments_are_validated_and_persisted(client):
    adjustments = {
        "birth_multiplier": 1.2,
        "death_multiplier": 0.8,
        "migration_multiplier": 0.5,
        "relocation_multiplier": 1.1,
        "random_seed": 99,
    }
    created = client.post(
        "/api/simulation/run",
        json={"start_year": 2024, "end_year": 2024, "adjustments": adjustments},
    )
    assert created.status_code == 200
    summary = client.get(f"/api/simulation/runs/{created.json()['run_id']}").json()
    assert summary["adjustments"] == adjustments

    invalid = client.post(
        "/api/simulation/run",
        json={
            "start_year": 2024,
            "end_year": 2024,
            "adjustments": {"birth_multiplier": 3.1},
        },
    )
    assert invalid.status_code == 422


def test_per_community_adjustments_are_validated_and_persisted(client):
    created = client.post(
        "/api/simulation/run",
        json={
            "start_year": 2024,
            "end_year": 2024,
            "adjustments": {"community": {"catholic": {"birth_multiplier": 1.4}}},
        },
    )

    assert created.status_code == 200
    summary = client.get(f"/api/simulation/runs/{created.json()['run_id']}").json()
    catholic = summary["adjustments"]["community"]["catholic"]
    assert catholic["birth_multiplier"] == 1.4
    assert catholic["death_multiplier"] == 1.0

    invalid = client.post(
        "/api/simulation/run",
        json={"adjustments": {"community": {"catholic": {"birth_multiplier": 3.1}}}},
    )
    assert invalid.status_code == 422


def test_two_runs_are_user_isolated(client, populated_db):
    first = client.post(
        "/api/simulation/run", json={"start_year": 2024, "end_year": 2024}
    ).json()
    second = client.post(
        "/api/simulation/run",
        json={
            "start_year": 2024,
            "end_year": 2024,
            "model_path": "models/ni_zero_migration.yaml",
        },
    ).json()

    first_id = uuid.UUID(first["run_id"])
    second_id = uuid.UUID(second["run_id"])
    assert first_id != second_id
    assert populated_db.query(Person).filter(Person.run_id == first_id).count() > 0
    assert populated_db.query(Person).filter(Person.run_id == second_id).count() > 0


def test_run_summary_and_year_endpoints(client):
    created = client.post(
        "/api/simulation/run", json={"start_year": 2024, "end_year": 2025}
    ).json()
    run_id = created["run_id"]

    summary = client.get(f"/api/simulation/runs/{run_id}")
    years = client.get(f"/api/simulation/runs/{run_id}/years")
    snapshot = client.get(f"/api/simulation/runs/{run_id}/years/2024")

    assert summary.status_code == 200
    assert summary.json()["completed_years"] == [2024, 2025]
    assert years.json() == {"years": [2024, 2025]}
    assert snapshot.status_code == 200
    assert snapshot.json()["run_id"] == run_id
    assert snapshot.json()["year"] == 2024
    assert "locations" in snapshot.json()


def test_missing_run_and_snapshot_return_404(client):
    missing_id = uuid.uuid4()

    assert client.get(f"/api/simulation/runs/{missing_id}").status_code == 404

    created = client.post(
        "/api/simulation/run", json={"start_year": 2024, "end_year": 2024}
    ).json()
    response = client.get(f"/api/simulation/runs/{created['run_id']}/years/2025")
    assert response.status_code == 404


def test_stream_persists_run_and_emits_run_id(client, populated_db):
    response = client.get("/api/simulation/stream?start_year=2024&end_year=2025")

    assert response.status_code == 200
    run_id = uuid.UUID(response.headers["x-simulation-run-id"])
    events = _parse_sse(response.text)
    assert len(events) == 3
    assert events[0]["data"]["run_id"] == str(run_id)
    predictions = events[0]["data"]["voting_predictions"]
    assert set(predictions) == {"lucidtalk_winter_2025", "nilt_2024"}
    assert predictions["lucidtalk_winter_2025"]["source"]["id"] == (
        "lucidtalk_winter_2025"
    )
    assert set(predictions["lucidtalk_winter_2025"]["by_location"]) == {
        "antrim_and_newtownabbey",
        "armagh_banbridge_craigavon",
        "belfast",
        "causeway_coast_glens",
        "derry_strabane",
        "fermanagh_omagh",
        "lisburn_castlereagh",
        "mid_east_antrim",
        "mid_ulster",
        "newry_mourne_down",
        "ards_north_down",
    }
    assert events[-1]["event"] == "complete"
    run = populated_db.get(SimulationRun, run_id)
    assert run.status == "complete"
    assert len(run.snapshots) == 2


def test_run_rejects_invalid_model_and_years(client):
    invalid_model = client.post(
        "/api/simulation/run",
        json={
            "model_path": "models/nonexistent.yaml",
            "start_year": 2024,
            "end_year": 2025,
        },
    )
    reversed_years = client.post(
        "/api/simulation/run",
        json={"start_year": 2025, "end_year": 2024},
    )
    invalid_year = client.post(
        "/api/simulation/run",
        json={"start_year": 1800, "end_year": 1801},
    )

    assert invalid_model.status_code == 422
    assert reversed_years.status_code == 422
    assert invalid_year.status_code == 422


def test_stream_rejects_path_traversal_and_invalid_range(client):
    traversal = client.get(
        "/api/simulation/stream"
        "?start_year=2024&end_year=2024&model_path=../pyproject.toml"
    )
    reversed_years = client.get("/api/simulation/stream?start_year=2025&end_year=2024")
    malformed_community = client.get(
        "/api/simulation/stream?community_adjustments=not-json"
    )

    assert traversal.status_code == 422
    assert reversed_years.status_code == 422
    assert malformed_community.status_code == 422
