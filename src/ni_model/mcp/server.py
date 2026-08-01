"""FastMCP tools backed by the same services as the REST API."""

from contextlib import contextmanager
from typing import Any, Iterator, Optional
from uuid import UUID

from fastapi import HTTPException, Request
from fastmcp import FastMCP
from sqlalchemy.orm import Session

from ..api.routes.population import (
    population_location_detail,
    population_summary,
    voting_prediction,
)
from ..api.routes.simulation import (
    _get_run,
    _run_summary,
    cancel_simulation,
    run_simulation,
    simulation_models,
    simulation_person_history,
    simulation_year_people,
    simulation_year_snapshot,
    simulation_year_voting_prediction,
)
from ..api.schemas import SimulationRunRequest
from ..core.database import SessionLocal
from ..core.models import SimulationRun

mcp = FastMCP(
    "Northern Ireland Population Model",
    instructions=(
        "Explore Northern Ireland demographic baselines, run cohort simulations, "
        "and calculate polling scenarios. Model outputs are estimates; preserve "
        "their documented provenance and limitations when presenting results."
    ),
)

# Kept replaceable so integration tests and alternative deployments can bind the
# MCP interface to the same database session factory as the host application.
SessionFactory = SessionLocal


@contextmanager
def _session() -> Iterator[Session]:
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def _invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc


@mcp.tool
def list_models() -> list[dict[str, Any]]:
    """List model configurations, supported years, rules, and provenance."""
    return _json(simulation_models())


@mcp.tool
def get_population_summary() -> dict[str, Any]:
    """Return current baseline totals and broad demographic breakdowns."""
    with _session() as db:
        return _json(population_summary(db))


@mcp.tool
def get_location_details(location: str) -> dict[str, Any]:
    """Return demographic details for one LGD, by name or identifier."""
    with _session() as db:
        return _json(_invoke(population_location_detail, location, db))


@mcp.tool
def calculate_polling_scenario(
    calibration: str = "lucidtalk_winter_2025",
    include_locations: bool = True,
    unite: Optional[float] = None,
    remain: Optional[float] = None,
    undecided: Optional[float] = None,
) -> dict[str, Any]:
    """Calculate baseline voting estimates, optionally raked to percentages.

    Supply all of unite, remain, and undecided (each 0-100, summing to 100) for
    a custom polling baseline. Results remain demographic estimates, not votes.
    """
    with _session() as db:
        result = _invoke(
            voting_prediction,
            None,
            calibration,
            include_locations,
            unite,
            remain,
            undecided,
            db,
        )
        return _json(result)


@mcp.tool
def start_simulation(
    model_path: str = "models/ni_current.yaml",
    start_year: int = 2024,
    end_year: int = 2030,
    population_limit: Optional[int] = None,
    adjustments: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Queue a durable simulation using the REST API's validation and limits."""
    payload = SimulationRunRequest(
        model_path=model_path,
        start_year=start_year,
        end_year=end_year,
        population_limit=population_limit,
        adjustments=adjustments or {},
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [],
            "client": ("mcp", 0),
            "server": ("localhost", 8000),
            "scheme": "http",
            "query_string": b"",
        }
    )
    with _session() as db:
        return _json(_invoke(run_simulation, payload, request, db))


@mcp.tool
def list_simulation_runs(limit: int = 20) -> list[dict[str, Any]]:
    """List the most recent durable simulation runs (maximum 100)."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with _session() as db:
        runs = (
            db.query(SimulationRun)
            .order_by(SimulationRun.created_at.desc())
            .limit(limit)
            .all()
        )
        return _json([_run_summary(run) for run in runs])


@mcp.tool
def get_simulation_run(run_id: UUID) -> dict[str, Any]:
    """Return status, scale, settings, and completed years for a run."""
    with _session() as db:
        return _json(_invoke(_run_summary, _invoke(_get_run, db, run_id)))


@mcp.tool
def get_year_snapshot(run_id: UUID, year: int) -> dict[str, Any]:
    """Return the aggregate demographic snapshot for one simulation year."""
    with _session() as db:
        return _json(_invoke(simulation_year_snapshot, run_id, year, db))


@mcp.tool
def calculate_year_polling_scenario(
    run_id: UUID,
    year: int,
    calibration: str = "lucidtalk_winter_2025",
    unite: Optional[float] = None,
    remain: Optional[float] = None,
    undecided: Optional[float] = None,
) -> dict[str, Any]:
    """Calculate voting estimates from a completed simulation-year snapshot."""
    with _session() as db:
        result = _invoke(
            simulation_year_voting_prediction,
            run_id,
            year,
            calibration,
            unite,
            remain,
            undecided,
            db,
        )
        return _json(result)


@mcp.tool
def get_simulated_people(
    run_id: UUID,
    year: int,
    offset: int = 0,
    limit: int = 100,
    location: Optional[str] = None,
    religious_background: Optional[str] = None,
) -> dict[str, Any]:
    """Inspect a filtered, paginated page of simulated individual records."""
    if offset < 0 or not 1 <= limit <= 1000:
        raise ValueError("offset must be non-negative and limit must be 1-1000")
    with _session() as db:
        result = _invoke(
            simulation_year_people,
            run_id,
            year,
            offset,
            limit,
            location,
            religious_background,
            db,
        )
        return _json(result)


@mcp.tool
def get_person_history(run_id: UUID, person_id: UUID) -> dict[str, Any]:
    """Return one simulated resident's initial state and event history."""
    with _session() as db:
        return _json(_invoke(simulation_person_history, run_id, person_id, db))


@mcp.tool
def cancel_simulation_run(run_id: UUID) -> dict[str, Any]:
    """Cooperatively cancel a queued or running simulation."""
    with _session() as db:
        return _json(_invoke(cancel_simulation, run_id, db))
