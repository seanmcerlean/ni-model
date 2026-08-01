import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from src.ni_model.mcp import server


class Result(BaseModel):
    value: str = "ok"


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def session(monkeypatch):
    value = FakeSession()
    monkeypatch.setattr(server, "SessionFactory", lambda: value)
    return value


def test_fastmcp_registers_complete_tool_surface():
    tools = asyncio.run(server.mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "list_models",
        "get_population_summary",
        "get_location_details",
        "calculate_polling_scenario",
        "start_simulation",
        "list_simulation_runs",
        "get_simulation_run",
        "get_year_snapshot",
        "calculate_year_polling_scenario",
        "get_simulated_people",
        "get_person_history",
        "cancel_simulation_run",
    }


def test_read_tools_delegate_to_api_services(monkeypatch, session):
    monkeypatch.setattr(server, "simulation_models", lambda: [Result()])
    monkeypatch.setattr(server, "population_summary", lambda db: Result())
    monkeypatch.setattr(
        server,
        "population_location_detail",
        lambda location, db: Result(value=location),
    )

    assert server.list_models() == [{"value": "ok"}]
    assert server.get_population_summary() == {"value": "ok"}
    assert server.get_location_details("Belfast") == {"value": "Belfast"}
    assert session.closed


def test_polling_tools_forward_custom_baselines(monkeypatch, session):
    calls = []

    def record(*args):
        calls.append(args)
        return Result()

    monkeypatch.setattr(server, "voting_prediction", record)
    monkeypatch.setattr(server, "simulation_year_voting_prediction", record)
    run_id = uuid4()

    assert server.calculate_polling_scenario(unite=40, remain=50, undecided=10)
    assert server.calculate_year_polling_scenario(
        run_id, 2030, unite=40, remain=50, undecided=10
    )
    assert calls[0][3:6] == (40, 50, 10)
    assert calls[1][0:2] == (run_id, 2030)


def test_start_simulation_validates_and_delegates(monkeypatch, session):
    captured = {}

    def run(payload, request, db):
        captured["payload"] = payload
        captured["client"] = request.client.host
        return Result()

    monkeypatch.setattr(server, "run_simulation", run)

    result = server.start_simulation(
        end_year=2025,
        population_limit=25_000,
        adjustments={"random_seed": 7},
    )

    assert result == {"value": "ok"}
    assert captured["payload"].population_limit == 25_000
    assert captured["payload"].adjustments.random_seed == 7
    assert captured["client"] == "mcp"


def test_run_and_population_inspection_tools(monkeypatch, session):
    run_id = uuid4()
    person_id = uuid4()
    fake_run = SimpleNamespace(created_at=1)
    query = SimpleNamespace(
        order_by=lambda *args: SimpleNamespace(
            limit=lambda limit: SimpleNamespace(all=lambda: [fake_run])
        )
    )
    session.query = lambda model: query
    monkeypatch.setattr(server, "_run_summary", lambda run: Result())
    monkeypatch.setattr(server, "_get_run", lambda db, identifier: fake_run)
    monkeypatch.setattr(server, "simulation_year_snapshot", lambda *args: Result())
    monkeypatch.setattr(server, "simulation_year_people", lambda *args: Result())
    monkeypatch.setattr(server, "simulation_person_history", lambda *args: Result())
    monkeypatch.setattr(server, "cancel_simulation", lambda *args: Result())

    assert server.list_simulation_runs() == [{"value": "ok"}]
    assert server.get_simulation_run(run_id) == {"value": "ok"}
    assert server.get_year_snapshot(run_id, 2025) == {"value": "ok"}
    assert server.get_simulated_people(run_id, 2025) == {"value": "ok"}
    assert server.get_person_history(run_id, person_id) == {"value": "ok"}
    assert server.cancel_simulation_run(run_id) == {"value": "ok"}


@pytest.mark.parametrize("limit", [0, 101])
def test_run_list_rejects_invalid_limits(limit):
    with pytest.raises(ValueError, match="between 1 and 100"):
        server.list_simulation_runs(limit)


@pytest.mark.parametrize("offset,limit", [(-1, 10), (0, 0), (0, 1001)])
def test_people_page_rejects_invalid_bounds(offset, limit):
    with pytest.raises(ValueError, match="offset must be"):
        server.get_simulated_people(uuid4(), 2025, offset, limit)


def test_http_errors_become_mcp_safe_value_errors():
    def fail():
        raise HTTPException(status_code=404, detail="missing")

    with pytest.raises(ValueError, match="missing"):
        server._invoke(fail)
