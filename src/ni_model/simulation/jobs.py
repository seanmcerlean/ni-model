"""Durable PostgreSQL-backed simulation job execution."""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from ..core.database import SessionLocal
from ..core.models import SimulationRun
from .event_store import EventStore

_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("SIMULATION_WORKERS", "1"))),
    thread_name_prefix="simulation-worker",
)


def submit_run(run_id: uuid.UUID, session_factory: sessionmaker = SessionLocal) -> None:
    _executor.submit(execute_run, run_id, session_factory)


def claim_next_run(db: Session) -> uuid.UUID | None:
    run = (
        db.query(SimulationRun)
        .filter(SimulationRun.status == "pending")
        .order_by(SimulationRun.created_at)
        .with_for_update(skip_locked=True)
        .first()
    )
    if run is None:
        db.rollback()
        return None
    run.status = "running"
    db.commit()
    return run.id


def recover_interrupted_runs(db: Session) -> int:
    """Return abandoned worker jobs to the durable queue after a restart."""
    recovered = (
        db.query(SimulationRun)
        .filter(SimulationRun.status == "running")
        .update({SimulationRun.status: "pending"}, synchronize_session=False)
    )
    cancelled = (
        db.query(SimulationRun)
        .filter(SimulationRun.status == "cancelling")
        .update(
            {
                SimulationRun.status: "cancelled",
                SimulationRun.completed_at: datetime.now(UTC),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return recovered + cancelled


def cleanup_expired_runs(db: Session) -> int:
    """Delete terminal runs and checkpoint files after the retention window."""
    retention_days = max(1, int(os.getenv("SIMULATION_RETENTION_DAYS", "30")))
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    runs = (
        db.query(SimulationRun)
        .filter(
            SimulationRun.status.in_({"complete", "cancelled", "failed"}),
            SimulationRun.completed_at < cutoff,
        )
        .all()
    )
    store = EventStore(db)
    for run in runs:
        store.delete_run(run.id)
        db.delete(run)
    db.commit()
    return len(runs)


def execute_run(
    run_id: uuid.UUID,
    session_factory: sessionmaker = SessionLocal,
    already_claimed: bool = False,
) -> None:
    db = session_factory()
    try:
        if not already_claimed:
            claimed = (
                db.query(SimulationRun)
                .filter(
                    SimulationRun.id == run_id,
                    SimulationRun.status == "pending",
                )
                .update({SimulationRun.status: "running"})
            )
            db.commit()
            if claimed == 0:
                return
        run = db.get(SimulationRun, run_id)
        if run is None:
            return
        from ..api.routes.simulation import _columnar_years, _load_director

        director = _load_director(db, run.model_path, run.id, run.adjustments)
        started = time.monotonic()
        timeout_seconds = max(1, int(os.getenv("SIMULATION_TIMEOUT_SECONDS", "1800")))
        completed = False
        for _result, _snapshot in _columnar_years(db, run, director):
            if time.monotonic() - started > timeout_seconds:
                raise TimeoutError(
                    f"simulation exceeded {timeout_seconds} second execution limit"
                )
        db.refresh(run)
        if run.status == "cancelling":
            run.status = "cancelled"
        else:
            run.status = "complete"
            completed = True
        run.completed_at = datetime.now(UTC)
        db.commit()
        if not completed:
            return
    except Exception as exc:
        db.rollback()
        run = db.get(SimulationRun, run_id)
        if run is not None:
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()
