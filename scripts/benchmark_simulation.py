"""Benchmark a deterministic simulation against an existing PostgreSQL baseline."""

import argparse
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.api.routes.simulation import _capture_snapshot  # noqa: E402
from src.ni_model.core.models import Person  # noqa: E402
from src.ni_model.simulation.model_director import ModelDirector  # noqa: E402
from src.ni_model.simulation.orchestrator import SimulationOrchestrator  # noqa: E402
from src.ni_model.simulation.performance import PerformanceRecorder  # noqa: E402
from src.ni_model.simulation.population_manager import PopulationManager  # noqa: E402


def benchmark(args) -> dict:
    engine = create_engine(args.database_url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise ValueError("performance benchmarks require PostgreSQL")
    session = sessionmaker(bind=engine, autoflush=False)()
    recorder = PerformanceRecorder(engine)
    try:
        baseline_count = (
            session.query(func.count(Person.id))
            .filter(Person.run_id.is_(None))
            .scalar()
        )
        if baseline_count == 0:
            raise ValueError("the database has no baseline population")
        if args.expected_size is not None and baseline_count != args.expected_size:
            raise ValueError(
                f"expected {args.expected_size:,} baseline residents, "
                f"found {baseline_count:,}"
            )

        adjustments = {"random_seed": args.seed}
        with recorder:
            with recorder.stage("baseline_preparation"):
                run = PopulationManager.create_run(
                    session,
                    args.model,
                    args.start_year,
                    args.end_year,
                    adjustments,
                )
            director = ModelDirector.from_yaml(
                session, args.model, run_id=run.id, adjustments=adjustments
            )
            orchestrator = SimulationOrchestrator(session, director, recorder=recorder)
            payload_bytes = 0
            results = []
            for year in range(args.start_year, args.end_year + 1):
                result = orchestrator.engine.run_simulation_year(year)
                results.append(result)
                with recorder.stage("flush"):
                    session.flush()
                with recorder.stage("snapshot_aggregation"):
                    snapshot = _capture_snapshot(run.id, year, result, session)
                with recorder.stage("serialization"):
                    payload = snapshot.model_dump_json()
                    payload_bytes += len(payload.encode("utf-8"))
                with recorder.stage("snapshot_persistence"):
                    PopulationManager(session, run.id).create_snapshot(
                        f"year_{year}", year, snapshot.model_dump(mode="json")
                    )
                    session.commit()

        metadata = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "database": engine.dialect.name,
            "model": args.model,
            "seed": args.seed,
            "start_year": args.start_year,
            "end_year": args.end_year,
            "baseline_population": baseline_count,
            "final_population": (
                session.query(func.count(Person.id))
                .filter(Person.run_id == run.id)
                .scalar()
            ),
            "sse_payload_bytes": payload_bytes,
            "results": results,
        }
        return recorder.report(metadata)
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--model", default="models/ni_current_community.yaml")
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--expected-size", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    if args.end_year < args.start_year:
        parser.error("--end-year must not precede --start-year")

    report = benchmark(args)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
