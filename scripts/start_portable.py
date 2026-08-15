"""Initialize the lightweight metadata store and start the Parquet API."""

import os
import sys
from pathlib import Path
from uuid import UUID

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.core import models  # noqa: E402,F401
from src.ni_model.core.database import Base, SessionLocal, engine  # noqa: E402
from src.ni_model.core.deployment import baseline_path  # noqa: E402
from src.ni_model.core.models import SimulationRun  # noqa: E402
from src.ni_model.simulation.jobs import (  # noqa: E402
    cleanup_expired_runs,
    recover_interrupted_runs,
    submit_run,
)


def recover_portable_runtime(session_factory=SessionLocal) -> list[UUID]:
    """Recover interrupted SQLite jobs and resume every durable pending run."""
    db = session_factory()
    try:
        recover_interrupted_runs(db)
        cleanup_expired_runs(db)
        pending = [
            run_id
            for (run_id,) in db.query(SimulationRun.id)
            .filter(SimulationRun.status == "pending")
            .order_by(SimulationRun.created_at)
            .all()
        ]
    finally:
        db.close()
    for run_id in pending:
        submit_run(run_id, session_factory)
    return pending


def main() -> None:
    missing = [
        profile
        for profile in ("current", "historical")
        if not baseline_path(profile).is_file()
    ]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(
            f"Missing Parquet baseline(s): {names}. Run "
            "python scripts/build_parquet_baselines.py before starting."
        )
    Base.metadata.create_all(bind=engine)
    recover_portable_runtime()
    uvicorn.run(
        "src.ni_model.api.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
