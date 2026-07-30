import json
from pathlib import Path
from typing import AsyncGenerator, List

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.models import Location
from ...simulation.model_director import ModelDirector
from ...simulation.orchestrator import SimulationOrchestrator
from ..queries import (
    age_band_breakdown,
    gender_breakdown,
    location_totals,
    origin_breakdown,
    religious_breakdown,
)
from ..routes.population import get_db
from ..schemas import (
    SimulationLocationSnapshot,
    SimulationModelSummary,
    SimulationRunRequest,
    SimulationRunResponse,
    SimulationYearResult,
    SimulationYearsList,
    SimulationYearSnapshot,
)

router = APIRouter(prefix="/api/simulation", tags=["simulation"])
PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODELS_DIR = PROJECT_ROOT / "models"

# In-memory store for completed simulation results, keyed by year.
# Populated by the orchestrator via store_results().
_year_snapshots: dict[int, SimulationYearSnapshot] = {}
_year_results: dict[int, SimulationYearResult] = {}


def _resolve_model_path(model_path: str) -> Path:
    """Resolve a model inside MODELS_DIR without allowing filesystem traversal."""
    requested = Path(model_path)
    candidate = (
        requested.resolve()
        if requested.is_absolute()
        else (PROJECT_ROOT / requested).resolve()
    )
    try:
        candidate.relative_to(MODELS_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="model_path must refer to a file in models/"
        ) from exc
    if candidate.suffix.lower() not in {".yaml", ".yml"} or not candidate.is_file():
        raise HTTPException(
            status_code=422, detail=f"Model file not found: {model_path}"
        )
    return candidate


def _load_director(db: Session, model_path: str) -> ModelDirector:
    path = _resolve_model_path(model_path)
    try:
        return ModelDirector.from_yaml(db, str(path))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid model configuration: {exc}"
        ) from exc


@router.get("/models", response_model=list[SimulationModelSummary])
def simulation_models():
    models = []
    for path in sorted(MODELS_DIR.glob("*.y*ml")):
        with path.open() as model_file:
            config = yaml.safe_load(model_file) or {}
        rule_groups = [
            config.get("birth_rates", []),
            config.get("death_rates", []),
            config.get("migration_rates", []),
            config.get("internal_migration_rates", []),
        ]
        years = [
            rule[key]
            for rules in rule_groups
            for rule in rules
            for key in ("year_min", "year_max")
            if rule.get(key) is not None
        ]
        models.append(
            SimulationModelSummary(
                id=path.stem,
                path=f"models/{path.name}",
                name=config.get("name", path.stem),
                description=str(config.get("description", "")).strip(),
                rate_jitter=float(config.get("rate_jitter", 0)),
                random_seed=config.get("random_seed"),
                birth_rules=len(rule_groups[0]),
                death_rules=len(rule_groups[1]),
                migration_rules=len(rule_groups[2]),
                internal_migration_rules=len(rule_groups[3]),
                year_min=min(years) if years else None,
                year_max=max(years) if years else None,
            )
        )
    return models


def store_results(
    results: List[dict], db, snapshots: dict[int, SimulationYearSnapshot]
):
    """Store simulation results and snapshots — called by orchestrator after run()"""
    _year_results.clear()
    _year_snapshots.clear()
    _year_results.update({r["year"]: SimulationYearResult(**r) for r in results})
    _year_snapshots.update(snapshots)


def _capture_snapshot(year: int, result: dict, db: Session) -> SimulationYearSnapshot:
    loc_breakdown = {loc.value: count for loc, count in location_totals(db)}
    locations = {
        location.value: SimulationLocationSnapshot(
            total=loc_breakdown.get(location.value, 0),
            religious_breakdown=religious_breakdown(db, location),
            gender_breakdown=gender_breakdown(db, location),
            origin_breakdown=origin_breakdown(db, location),
            age_bands=age_band_breakdown(db, location),
        )
        for location in Location
    }
    return SimulationYearSnapshot(
        year=year,
        total_population=sum(loc_breakdown.values()),
        religious_breakdown=religious_breakdown(db),
        gender_breakdown=gender_breakdown(db),
        location_breakdown=loc_breakdown,
        locations=locations,
        simulation_result=SimulationYearResult(**result),
    )


@router.get("/years", response_model=SimulationYearsList)
def simulation_years():
    return SimulationYearsList(years=sorted(_year_snapshots.keys()))


@router.get("/years/{year}", response_model=SimulationYearSnapshot)
def simulation_year_snapshot(year: int):
    snapshot = _year_snapshots.get(year)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot for year {year}")
    return snapshot


@router.get("/stream")
def stream_simulation(
    start_year: int = 2024,
    end_year: int = 2030,
    model_path: str = "models/ni_base_2024.yaml",
    db: Session = Depends(get_db),
):
    if not (1900 <= start_year <= 2200) or not (1900 <= end_year <= 2200):
        raise HTTPException(
            status_code=422, detail="year must be between 1900 and 2200"
        )
    if end_year < start_year:
        raise HTTPException(status_code=422, detail="end_year must be >= start_year")

    director = _load_director(db, model_path)
    orchestrator = SimulationOrchestrator(db, director)

    async def event_stream() -> AsyncGenerator[str, None]:
        for result in orchestrator._iter_years(start_year, end_year):
            snapshot = _capture_snapshot(result["year"], result, db)
            payload = snapshot.model_dump()
            yield f"data: {json.dumps(payload)}\n\n"
        yield "event: complete\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/run", response_model=SimulationRunResponse)
def run_simulation(request: SimulationRunRequest, db: Session = Depends(get_db)):
    director = _load_director(db, request.model_path)
    orchestrator = SimulationOrchestrator(db, director)

    results = []
    snapshots = {}
    for result in orchestrator._iter_years(request.start_year, request.end_year):
        results.append(result)
        snapshots[result["year"]] = _capture_snapshot(result["year"], result, db)
    orchestrator.results = results
    store_results(results, db, snapshots)

    return SimulationRunResponse(
        model_path=request.model_path,
        start_year=request.start_year,
        end_year=request.end_year,
        years_simulated=len(results),
        results=[SimulationYearResult(**r) for r in results],
    )
