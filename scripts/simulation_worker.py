"""Run durable simulation jobs from the PostgreSQL queue."""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.core.database import SessionLocal  # noqa: E402
from src.ni_model.simulation.jobs import (  # noqa: E402
    claim_next_run,
    cleanup_expired_runs,
    execute_run,
    recover_interrupted_runs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")

    startup_db = SessionLocal()
    try:
        recover_interrupted_runs(startup_db)
        cleanup_expired_runs(startup_db)
    finally:
        startup_db.close()

    while True:
        db = SessionLocal()
        try:
            run_id = claim_next_run(db)
        finally:
            db.close()
        if run_id is not None:
            execute_run(run_id, already_claimed=True)
        elif args.once:
            return
        else:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
