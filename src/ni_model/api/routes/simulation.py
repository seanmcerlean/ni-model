import asyncio
import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator, Optional
from urllib.parse import unquote, urlparse
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ...core.models import (
    SimulationCheckpoint,
    SimulationPersonEvent,
    SimulationRun,
    SimulationSnapshot,
)
from ...simulation.columnar_worker import ColumnarSimulationWorker
from ...simulation.event_store import EventStore
from ...simulation.jobs import submit_run
from ...simulation.model_director import ModelDirector
from ...simulation.population_manager import PopulationManager
from ...simulation.reconstruction import PopulationReconstructor
from ...simulation.voting_predictor import CALIBRATIONS, VotingPredictor
from ..queries import snapshot_aggregates
from ..routes.population import get_db
from ..schemas import (
    SimulationAdjustments,
    SimulationLocationSnapshot,
    SimulationModelSummary,
    SimulationPeoplePage,
    SimulationPersonHistory,
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
ACTIVE_STATUSES = {"pending", "running", "cancelling"}


def _owner_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(host.encode()).hexdigest()


def _enforce_run_limits(
    db: Session, request: Request, start_year: int, end_year: int
) -> str:
    horizon = max(1, int(os.getenv("MAX_SIMULATION_HORIZON_YEARS", "100")))
    if end_year - start_year + 1 > horizon:
        raise HTTPException(
            status_code=422,
            detail=f"simulation horizon cannot exceed {horizon} years",
        )
    owner_key = _owner_key(request)
    if db.get_bind().dialect.name == "postgresql":
        lock_key = int.from_bytes(bytes.fromhex(owner_key[:16]), signed=True)
        db.execute(select(func.pg_advisory_xact_lock(lock_key)))
    maximum = max(1, int(os.getenv("MAX_ACTIVE_RUNS_PER_USER", "2")))
    active = (
        db.query(SimulationRun)
        .filter(
            SimulationRun.owner_key == owner_key,
            SimulationRun.status.in_(ACTIVE_STATUSES),
        )
        .count()
    )
    if active >= maximum:
        raise HTTPException(
            status_code=429,
            detail=f"at most {maximum} active simulations are allowed",
        )
    return owner_key


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


def _baseline_settings(model_path: str) -> tuple[str, int]:
    path = _resolve_model_path(model_path)
    try:
        with path.open(encoding="utf-8") as model_file:
            config = yaml.safe_load(model_file) or {}
        profile = config.get("baseline_profile", "current")
        population = int(config["baseline_population"])
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid model baseline configuration: {exc}",
        ) from exc
    if profile not in {"current", "historical"} or population < 1:
        raise HTTPException(status_code=422, detail="Invalid model baseline profile")
    return profile, population


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
                baseline_profile=config.get("baseline_profile", "current"),
                baseline_population=int(config.get("baseline_population", 1_903_175)),
                data_through=config.get("data_through"),
                projection_version=config.get("projection_version"),
                default_start_year=config.get("default_start_year"),
                default_end_year=config.get("default_end_year"),
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
    aggregates = snapshot_aggregates(db, run_id=run_id)
    locations = {
        location_id: SimulationLocationSnapshot(
            total=detail.total,
            religious_breakdown=detail.religious_breakdown,
            gender_breakdown=detail.gender_breakdown,
            origin_breakdown=detail.origin_breakdown,
            age_bands=detail.age_bands,
        )
        for location_id, detail in aggregates.locations.items()
    }
    voting_rows = VotingPredictor.aggregate_population(db, run_id)
    voting_predictions = {
        calibration: _snapshot_voting_prediction(
            db, run_id, calibration, voting_rows, aggregates.total
        )
        for calibration in CALIBRATIONS
    }
    return SimulationYearSnapshot(
        run_id=run_id,
        year=year,
        total_population=aggregates.total,
        religious_breakdown=aggregates.religious_breakdown,
        gender_breakdown=aggregates.gender_breakdown,
        location_breakdown={
            key: detail.total
            for key, detail in aggregates.locations.items()
            if detail.total
        },
        locations=locations,
        voting_predictions=voting_predictions,
        simulation_result=SimulationYearResult(**result),
    )


def _snapshot_voting_prediction(
    db: Session,
    run_id: UUID,
    calibration: str,
    aggregate_rows=None,
    total_population=None,
) -> dict:
    predictor = VotingPredictor(
        db,
        run_id=run_id,
        calibration=calibration,
        aggregate_rows=aggregate_rows,
        total_population=total_population,
    )
    return {**predictor.predict(), "by_location": predictor.predict_by_location()}


def _scaled_counts(values: dict, scale: float, target: int = None) -> dict:
    """Expand representative counts while preserving the requested total."""
    target = round(sum(values.values()) * scale) if target is None else target
    raw = {key: value * scale for key, value in values.items()}
    scaled = {key: math.floor(value) for key, value in raw.items()}
    remainder = target - sum(scaled.values())
    for key in sorted(raw, key=lambda item: (raw[item] % 1, item), reverse=True)[
        :remainder
    ]:
        scaled[key] += 1
    return scaled


def _scaled_aggregates(aggregates: dict, scale: float) -> dict:
    if scale == 1.0:
        return aggregates
    total = round(aggregates["total_population"] * scale)
    location_totals = _scaled_counts(
        {key: detail["total"] for key, detail in aggregates["locations"].items()},
        scale,
        total,
    )
    locations = {}
    for key, detail in aggregates["locations"].items():
        location_total = location_totals[key]
        locations[key] = {
            "total": location_total,
            "religious_breakdown": _scaled_counts(
                detail["religious_breakdown"], scale, location_total
            ),
            "gender_breakdown": _scaled_counts(
                detail["gender_breakdown"], scale, location_total
            ),
            "origin_breakdown": _scaled_counts(
                detail["origin_breakdown"], scale, location_total
            ),
            "age_bands": _scaled_counts(detail["age_bands"], scale, location_total),
        }
    return {
        "total_population": total,
        "religious_breakdown": _scaled_counts(
            aggregates["religious_breakdown"], scale, total
        ),
        "gender_breakdown": _scaled_counts(
            aggregates["gender_breakdown"], scale, total
        ),
        "location_breakdown": location_totals,
        "locations": locations,
    }


def _scaled_result(result: dict, scale: float) -> dict:
    if scale == 1.0:
        return result
    scaled = {
        key: round(value * scale) if key != "year" else value
        for key, value in result.items()
    }
    scaled["migration"] = scaled["immigration"] - scaled["emigration"]
    scaled["net_change"] = scaled["births"] - scaled["deaths"] + scaled["migration"]
    return scaled


def _scaled_voting_rows(rows, scale: float):
    if scale == 1.0:
        return rows
    raw_counts = [row.count * scale for row in rows]
    counts = [math.floor(count) for count in raw_counts]
    remainder = round(sum(row.count for row in rows) * scale) - sum(counts)
    ranked_indexes = sorted(
        range(len(rows)),
        key=lambda index: (raw_counts[index] % 1, -index),
        reverse=True,
    )
    for index in ranked_indexes[:remainder]:
        counts[index] += 1
    return [
        SimpleNamespace(
            location=row.location,
            religious_background=row.religious_background,
            age=row.age,
            count=counts[index],
        )
        for index, row in enumerate(rows)
    ]


def _capture_columnar_snapshot(
    worker: ColumnarSimulationWorker,
    run_id: UUID,
    year: int,
    result: dict,
    db: Session,
    voting_rows=None,
    population_scale: float = 1.0,
) -> SimulationYearSnapshot:
    aggregates = _scaled_aggregates(worker.demographic_summary(year), population_scale)
    voting_rows = worker.voting_rows(year) if voting_rows is None else voting_rows
    voting_rows = _scaled_voting_rows(voting_rows, population_scale)
    voting_predictions = {
        calibration: _snapshot_voting_prediction(
            db,
            run_id,
            calibration,
            voting_rows,
            aggregates["total_population"],
        )
        for calibration in CALIBRATIONS
    }
    return SimulationYearSnapshot(
        run_id=run_id,
        year=year,
        sample_population=worker.population.height,
        population_scale=population_scale,
        **aggregates,
        voting_predictions=voting_predictions,
        simulation_result=SimulationYearResult(
            **_scaled_result(result, population_scale)
        ),
    )


def _stored_columnar_snapshot(snapshot: SimulationYearSnapshot, voting_rows) -> dict:
    data = snapshot.model_dump(mode="json")
    data["_polling_inputs"] = [
        [row.location.value, row.religious_background.value, row.age, row.count]
        for row in voting_rows
    ]
    return data


def _columnar_years(
    db: Session,
    run: SimulationRun,
    director: ModelDirector,
):
    event_store = EventStore(db)
    checkpoint = (
        db.query(SimulationCheckpoint)
        .filter(SimulationCheckpoint.run_id == run.id)
        .order_by(SimulationCheckpoint.year.desc())
        .first()
    )
    if checkpoint:
        worker = ColumnarSimulationWorker(
            event_store.load(checkpoint),
            director.config,
            run.id,
            seed=director.seed,
        )
        first_year = checkpoint.year + 1
        db.query(SimulationPersonEvent).filter(
            SimulationPersonEvent.run_id == run.id,
            SimulationPersonEvent.year > checkpoint.year,
        ).delete(synchronize_session=False)
        db.query(SimulationSnapshot).filter(
            SimulationSnapshot.run_id == run.id,
            SimulationSnapshot.year > checkpoint.year,
        ).delete(synchronize_session=False)
        db.commit()
    else:
        worker = ColumnarSimulationWorker.load_baseline(
            db,
            director.config,
            run.id,
            run.start_year,
            seed=director.seed,
            population_limit=run.base_population_count,
            baseline_profile=run.baseline_profile,
        )
        first_year = run.start_year
    checkpoint_interval = max(1, int(os.getenv("CHECKPOINT_INTERVAL", "5")))
    for year in range(first_year, run.end_year + 1):
        db.refresh(run)
        if run.status == "cancelling":
            return
        result = worker.run_year(year)
        voting_rows = worker.voting_rows(year)
        snapshot = _capture_columnar_snapshot(
            worker,
            run.id,
            year,
            result,
            db,
            voting_rows=voting_rows,
            population_scale=run.population_scale,
        )
        event_store.append(run.id, worker.events)
        worker.events.clear()
        PopulationManager(db, run.id).create_snapshot(
            f"year_{year}",
            year,
            _stored_columnar_snapshot(
                snapshot, _scaled_voting_rows(voting_rows, run.population_scale)
            ),
        )
        if (
            year == run.end_year
            or (year - run.start_year + 1) % checkpoint_interval == 0
        ):
            event_store.checkpoint(run.id, year, worker.population)
        db.commit()
        yield result, snapshot


def _get_run(db: Session, run_id: UUID) -> SimulationRun:
    run = db.get(SimulationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    db.refresh(run)
    return run


def _submit_if_embedded(run_id: UUID, db: Session) -> None:
    enabled = os.getenv("EMBEDDED_SIMULATION_WORKER", "true").lower()
    if enabled in {"1", "true", "yes"}:
        submit_run(run_id, sessionmaker(bind=db.get_bind(), autoflush=False))


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
        represented_population_count=run.represented_population_count,
        population_scale=run.population_scale,
        baseline_profile=run.baseline_profile,
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


@router.get("/runs/{run_id}/years/{year}/checkpoint")
def simulation_year_checkpoint(run_id: UUID, year: int, db: Session = Depends(get_db)):
    """Download an exact, durable full-population Parquet checkpoint."""
    _get_run(db, run_id)
    checkpoint = (
        db.query(SimulationCheckpoint)
        .filter(
            SimulationCheckpoint.run_id == run_id,
            SimulationCheckpoint.year == year,
        )
        .one_or_none()
    )
    if not checkpoint:
        raise HTTPException(
            status_code=404,
            detail=f"No full-population checkpoint for year {year}",
        )
    parsed = urlparse(checkpoint.storage_uri)
    if parsed.scheme != "file":
        raise HTTPException(
            status_code=501,
            detail="This checkpoint storage backend cannot be downloaded directly",
        )
    path = Path(unquote(parsed.path))
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Checkpoint file is unavailable")
    return FileResponse(
        path,
        media_type="application/vnd.apache.parquet",
        filename=f"ni-model-{run_id}-{year}.parquet",
        headers={
            "X-Checkpoint-SHA256": checkpoint.checksum,
            "X-Population-Count": str(checkpoint.population_count),
        },
    )


@router.get("/runs/{run_id}/years/{year}/people", response_model=SimulationPeoplePage)
def simulation_year_people(
    run_id: UUID,
    year: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    location: Optional[str] = None,
    religious_background: Optional[str] = None,
    db: Session = Depends(get_db),
):
    run = _get_run(db, run_id)
    try:
        total, people = PopulationReconstructor(db).page(
            run,
            year,
            offset,
            limit,
            location=location,
            religious_background=religious_background,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SimulationPeoplePage(
        run_id=run_id,
        year=year,
        total=total,
        offset=offset,
        limit=limit,
        people=people,
    )


@router.get(
    "/runs/{run_id}/people/{person_id}/history",
    response_model=SimulationPersonHistory,
)
def simulation_person_history(
    run_id: UUID, person_id: UUID, db: Session = Depends(get_db)
):
    run = _get_run(db, run_id)
    try:
        return SimulationPersonHistory(
            **PopulationReconstructor(db).history(run, person_id)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stream")
def stream_simulation(
    request: Request,
    start_year: int = 2024,
    end_year: int = 2030,
    model_path: str = "models/ni_current.yaml",
    birth_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    death_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    migration_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    relocation_multiplier: float = Query(1.0, ge=0.0, le=3.0),
    random_seed: Optional[int] = None,
    community_adjustments: Optional[str] = None,
    population_limit: Optional[int] = Query(None, ge=1, le=1_903_175),
    db: Session = Depends(get_db),
):
    if not (1900 <= start_year <= 2200) or not (1900 <= end_year <= 2200):
        raise HTTPException(
            status_code=422, detail="year must be between 1900 and 2200"
        )
    if end_year < start_year:
        raise HTTPException(status_code=422, detail="end_year must be >= start_year")
    owner_key = _enforce_run_limits(db, request, start_year, end_year)

    baseline_profile, represented_population = _baseline_settings(model_path)
    try:
        community = json.loads(community_adjustments) if community_adjustments else {}
        adjustments = SimulationAdjustments(
            birth_multiplier=birth_multiplier,
            death_multiplier=death_multiplier,
            migration_multiplier=migration_multiplier,
            relocation_multiplier=relocation_multiplier,
            random_seed=random_seed,
            community=community if community_adjustments else None,
        ).model_dump(exclude_none=True)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid community adjustments: {exc}"
        ) from exc
    try:
        run = PopulationManager.create_run(
            db,
            model_path,
            start_year,
            end_year,
            adjustments,
            clone_population=False,
            owner_key=owner_key,
            population_limit=population_limit,
            baseline_profile=baseline_profile,
            represented_population_count=represented_population,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    worker_sessions = sessionmaker(bind=db.get_bind(), autoflush=False)
    _submit_if_embedded(run.id, db)

    async def event_stream() -> AsyncGenerator[str, None]:
        emitted_years = set()
        yield f"event: started\ndata: {json.dumps({'run_id': str(run.id)})}\n\n"
        while True:
            if await request.is_disconnected():
                return
            poll_db = worker_sessions()
            try:
                current = poll_db.get(SimulationRun, run.id)
                snapshots = (
                    poll_db.query(SimulationSnapshot)
                    .filter(
                        SimulationSnapshot.run_id == run.id,
                        ~SimulationSnapshot.year.in_(emitted_years),
                    )
                    .order_by(SimulationSnapshot.year)
                    .all()
                )
                status = current.status
                error = current.error
                payloads = [snapshot.data for snapshot in snapshots]
            finally:
                poll_db.close()
            for payload in payloads:
                emitted_years.add(payload["year"])
                snapshot = SimulationYearSnapshot.model_validate(payload)
                yield f"data: {snapshot.model_dump_json()}\n\n"
            if status in {"complete", "cancelled", "failed"}:
                event_name = "error" if status == "failed" else status
                data = {"run_id": str(run.id)}
                if error:
                    data["error"] = error
                yield f"event: {event_name}\ndata: {json.dumps(data)}\n\n"
                return
            await asyncio.sleep(0.05)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Simulation-Run-ID": str(run.id)},
    )


@router.post("/run", response_model=SimulationRunResponse)
def run_simulation(
    payload: SimulationRunRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    baseline_profile, represented_population = _baseline_settings(payload.model_path)
    owner_key = _enforce_run_limits(db, request, payload.start_year, payload.end_year)
    try:
        run = PopulationManager.create_run(
            db,
            payload.model_path,
            payload.start_year,
            payload.end_year,
            payload.adjustments.model_dump(exclude_none=True),
            clone_population=False,
            owner_key=owner_key,
            population_limit=payload.population_limit,
            baseline_profile=baseline_profile,
            represented_population_count=represented_population,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _load_director(
        db,
        payload.model_path,
        run.id,
        payload.adjustments.model_dump(exclude_none=True),
    )
    _submit_if_embedded(run.id, db)
    return SimulationRunResponse(
        run_id=run.id,
        status=run.status,
        model_path=payload.model_path,
        start_year=payload.start_year,
        end_year=payload.end_year,
        years_simulated=0,
        results=[],
    )


@router.post("/runs/{run_id}/cancel", response_model=SimulationRunSummary)
def cancel_simulation(run_id: UUID, db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    if run.status == "pending":
        run.status = "cancelled"
        run.completed_at = datetime.now(UTC)
    elif run.status == "running":
        run.status = "cancelling"
    db.commit()
    db.refresh(run)
    return _run_summary(run)


@router.delete("/runs/{run_id}", status_code=204)
def delete_simulation(run_id: UUID, db: Session = Depends(get_db)):
    run = _get_run(db, run_id)
    if run.status in {"running", "cancelling"}:
        raise HTTPException(
            status_code=409, detail="cancel the running simulation first"
        )
    EventStore(db).delete_run(run.id)
    db.delete(run)
    db.commit()
