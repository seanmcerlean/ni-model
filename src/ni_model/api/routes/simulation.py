import json
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncGenerator, Optional
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.models import Location, SimulationRun, SimulationSnapshot
from ...simulation.model_director import ModelDirector
from ...simulation.orchestrator import SimulationOrchestrator
from ...simulation.population_manager import PopulationManager
from ...simulation.voting_predictor import CALIBRATIONS, VotingPredictor
from ..queries import (
    age_band_breakdown,
    gender_breakdown,
    location_totals,
    origin_breakdown,
    religious_breakdown,
)
from ..routes.population import get_db
from ..schemas import (
    SimulationAdjustments,
    SimulationLocationSnapshot,
    SimulationModelSummary,
    SimulationRunRequest,
    SimulationRunResponse,
    SimulationRunSummary,
    SimulationYearResult,
    SimulationYearsList,
    SimulationYearSnapshot,
)

router = APIRouter(prefix="/api/simulation", tags=["simulation"])
PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODELS_DIR = PROJECT_ROOT / "models"


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


def _load_director(
    db: Session, model_path: str, run_id: UUID = None, adjustments: dict = None
) -> ModelDirector:
    path = _resolve_model_path(model_path)
    try:
        return ModelDirector.from_yaml(
            db, str(path), run_id=run_id, adjustments=adjustments
        )
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
                baseline_year=config.get("baseline_year"),
                data_through=config.get("data_through"),
                projection_version=config.get("projection_version"),
                birth_rules=len(rule_groups[0]),
                death_rules=len(rule_groups[1]),
                migration_rules=len(rule_groups[2]),
                internal_migration_rules=len(rule_groups[3]),
                birth_rate_rules=rule_groups[0],
                death_rate_rules=rule_groups[1],
                migration_rate_rules=rule_groups[2],
                internal_migration_rate_rules=rule_groups[3],
                year_min=min(years) if years else None,
                year_max=max(years) if years else None,
            )
        )
    return models


def _capture_snapshot(
    run_id: UUID, year: int, result: dict, db: Session
) -> SimulationYearSnapshot:
    loc_breakdown = {
        loc.value: count for loc, count in location_totals(db, run_id=run_id)
    }
    locations = {
        location.value: SimulationLocationSnapshot(
            total=loc_breakdown.get(location.value, 0),
            religious_breakdown=religious_breakdown(db, location, run_id),
            gender_breakdown=gender_breakdown(db, location, run_id),
            origin_breakdown=origin_breakdown(db, location, run_id),
            age_bands=age_band_breakdown(db, location, run_id),
        )
        for location in Location
    }
    voting_predictions = {
        calibration: {
            **VotingPredictor(
                db, run_id=run_id, calibration=calibration
            ).predict(),
            "by_location": {},
        }
        for calibration in CALIBRATIONS
    }
    return SimulationYearSnapshot(
        run_id=run_id,
        year=year,
        total_population=sum(loc_breakdown.values()),
        religious_breakdown=religious_breakdown(db, run_id=run_id),
        gender_breakdown=gender_breakdown(db, run_id=run_id),
        location_breakdown=loc_breakdown,
        locations=locations,
        voting_predictions=voting_predictions,
        simulation_result=SimulationYearResult(**result),
    )


def _get_run(db: Session, run_id: UUID) -> SimulationRun:
    run = db.get(SimulationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@router.get("/runs", response_model=list[SimulationRunSummary])
def simulation_runs(db: Session = Depends(get_db)):
    runs = db.query(SimulationRun).order_by(SimulationRun.created_at.desc()).all()
    return [_run_summary(run) for run in runs]


def _run_summary(run: SimulationRun) -> SimulationRunSummary:
    return SimulationRunSummary(
        run_id=run.id,
        model_path=run.model_path,
        start_year=run.start_year,
        end_year=run.end_year,
        status=run.status,
        base_population_count=run.base_population_count,
        completed_years=[snapshot.year for snapshot in run.snapshots],
        error=run.error,
        adjustments=run.adjustments or {},
    )


@router.get("/runs/{run_id}", response_model=SimulationRunSummary)
def simulation_run(run_id: UUID, db: Session = Depends(get_db)):
    return _run_summary(_get_run(db, run_id))


@router.get("/runs/{run_id}/years", response_model=SimulationYearsList)
def simulation_years(run_id: UUID, db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    return SimulationYearsList(years=[snapshot.year for snapshot in run.snapshots])


@router.get("/runs/{run_id}/years/{year}", response_model=SimulationYearSnapshot)
def simulation_year_snapshot(run_id: UUID, year: int, db: Session = Depends(get_db)):
    _get_run(db, run_id)
    snapshot = (
        db.query(SimulationSnapshot)
        .filter(
            SimulationSnapshot.run_id == run_id,
            SimulationSnapshot.year == year,
        )
        .one_or_none()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot for year {year}")
    return SimulationYearSnapshot.model_validate(snapshot.data)


@router.get("/stream")
def stream_simulation(
    start_year: int = 2024,
    end_year: int = 2030,
    model_path: str = "models/ni_base_2024.yaml",
    birth_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    death_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    migration_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    relocation_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    random_seed: Optional[int] = None,
    db: Session = Depends(get_db),
):
    if not (1900 <= start_year <= 2200) or not (1900 <= end_year <= 2200):
        raise HTTPException(
            status_code=422, detail="year must be between 1900 and 2200"
        )
    if end_year < start_year:
        raise HTTPException(status_code=422, detail="end_year must be >= start_year")

    _resolve_model_path(model_path)
    adjustments = SimulationAdjustments(
        birth_multiplier=birth_multiplier,
        death_multiplier=death_multiplier,
        migration_multiplier=migration_multiplier,
        relocation_multiplier=relocation_multiplier,
        random_seed=random_seed,
    ).model_dump()
    run = PopulationManager.create_run(
        db, model_path, start_year, end_year, adjustments
    )
    director = _load_director(db, model_path, run.id, adjustments)
    orchestrator = SimulationOrchestrator(db, director)

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            run.status = "running"
            db.commit()
            for result in orchestrator._iter_years(start_year, end_year):
                snapshot = _capture_snapshot(run.id, result["year"], result, db)
                PopulationManager(db, run.id).create_snapshot(
                    f"year_{result['year']}",
                    result["year"],
                    snapshot.model_dump(mode="json"),
                )
                db.commit()
                yield f"data: {snapshot.model_dump_json()}\n\n"
            run.status = "complete"
            run.completed_at = datetime.now(UTC)
            db.commit()
            yield f"event: complete\ndata: {json.dumps({'run_id': str(run.id)})}\n\n"
        except Exception as exc:
            db.rollback()
            run.status = "failed"
            run.error = str(exc)
            db.commit()
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Simulation-Run-ID": str(run.id)},
    )


@router.post("/run", response_model=SimulationRunResponse)
def run_simulation(request: SimulationRunRequest, db: Session = Depends(get_db)):
    _resolve_model_path(request.model_path)
    run = PopulationManager.create_run(
        db,
        request.model_path,
        request.start_year,
        request.end_year,
        request.adjustments.model_dump(),
    )
    director = _load_director(
        db, request.model_path, run.id, request.adjustments.model_dump()
    )
    orchestrator = SimulationOrchestrator(db, director)

    results = []
    try:
        run.status = "running"
        for result in orchestrator._iter_years(request.start_year, request.end_year):
            results.append(result)
            snapshot = _capture_snapshot(run.id, result["year"], result, db)
            PopulationManager(db, run.id).create_snapshot(
                f"year_{result['year']}",
                result["year"],
                snapshot.model_dump(mode="json"),
            )
            db.commit()
        run.status = "complete"
        run.completed_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.error = str(exc)
        db.commit()
        raise
    orchestrator.results = results

    return SimulationRunResponse(
        run_id=run.id,
        status=run.status,
        model_path=request.model_path,
        start_year=request.start_year,
        end_year=request.end_year,
        years_simulated=len(results),
        results=[SimulationYearResult(**r) for r in results],
    )
