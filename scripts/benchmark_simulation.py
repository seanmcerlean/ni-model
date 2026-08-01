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

from src.ni_model.api.routes.simulation import (  # noqa: E402
    _capture_columnar_snapshot,
    _capture_snapshot,
    _stored_columnar_snapshot,
)
from src.ni_model.core.models import Person  # noqa: E402
from src.ni_model.simulation.columnar_worker import (  # noqa: E402
    ColumnarSimulationWorker,
)
from src.ni_model.simulation.event_store import EventStore  # noqa: E402
from src.ni_model.simulation.model_director import ModelDirector  # noqa: E402
from src.ni_model.simulation.orchestrator import SimulationOrchestrator  # noqa: E402
from src.ni_model.simulation.performance import PerformanceRecorder  # noqa: E402
from src.ni_model.simulation.population_manager import PopulationManager  # noqa: E402

CORE_STAGES = ("births", "deaths", "external_migration", "internal_relocation")
PERFORMANCE_BUDGETS = {25_000: 0.250, 250_000: 0.750, 1_903_175: 3.0}


def core_year_p95(report: dict) -> float:
    return sum(
        report["stages"][stage]["wall_p95_seconds"]
        for stage in CORE_STAGES
        if stage in report["stages"]
    )


def enforce_budget(report: dict, expected_size: int) -> None:
    budget = PERFORMANCE_BUDGETS.get(expected_size)
    if budget is None:
        raise ValueError("no performance budget is defined for this population size")
    measured = core_year_p95(report)
    if measured > budget:
        raise RuntimeError(
            f"core year p95 {measured:.3f}s exceeds {budget:.3f}s budget"
        )


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
                    clone_population=args.engine == "orm",
                    status="benchmarking",
                )
            director = ModelDirector.from_yaml(
                session, args.model, run_id=run.id, adjustments=adjustments
            )
            payload_bytes = 0
            results = []
            if args.engine == "orm":
                orchestrator = SimulationOrchestrator(
                    session, director, recorder=recorder
                )
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
                final_population = (
                    session.query(func.count(Person.id))
                    .filter(Person.run_id == run.id)
                    .scalar()
                )
            else:
                worker = ColumnarSimulationWorker.load_baseline(
                    session,
                    director.config,
                    run.id,
                    args.start_year,
                    seed=args.seed,
                    recorder=recorder,
                )
                event_store = EventStore(session, checkpoint_root=args.checkpoint_dir)
                for year in range(args.start_year, args.end_year + 1):
                    result = worker.run_year(year)
                    results.append(result)
                    with recorder.stage("snapshot_aggregation"):
                        voting_rows = worker.voting_rows(year)
                        snapshot = _capture_columnar_snapshot(
                            worker,
                            run.id,
                            year,
                            result,
                            session,
                            voting_rows=voting_rows,
                        )
                    with recorder.stage("serialization"):
                        payload = snapshot.model_dump_json()
                        payload_bytes += len(payload.encode("utf-8"))
                    with recorder.stage("event_persistence"):
                        event_store.append(run.id, worker.events)
                        worker.events.clear()
                    with recorder.stage("snapshot_persistence"):
                        PopulationManager(session, run.id).create_snapshot(
                            f"year_{year}",
                            year,
                            _stored_columnar_snapshot(snapshot, voting_rows),
                        )
                        session.commit()
                with recorder.stage("checkpoint_persistence"):
                    event_store.checkpoint(run.id, args.end_year, worker.population)
                    session.commit()
                final_population = worker.population.height

        metadata = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "database": engine.dialect.name,
            "engine": args.engine,
            "model": args.model,
            "seed": args.seed,
            "start_year": args.start_year,
            "end_year": args.end_year,
            "baseline_population": baseline_count,
            "final_population": final_population,
            "sse_payload_bytes": payload_bytes,
            "results": results,
        }
        report = recorder.report(metadata)
        metadata["core_year_p95_seconds"] = core_year_p95(report)
        return report
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--model", default="models/ni_current_community.yaml")
    parser.add_argument("--engine", choices=("columnar", "orm"), default="columnar")
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--expected-size", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--enforce-budget", action="store_true")
    parser.add_argument(
        "--checkpoint-dir", type=Path, default=Path("/tmp/ni-model-checkpoints")
    )
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
    if args.enforce_budget:
        if args.expected_size is None:
            parser.error("--enforce-budget requires --expected-size")
        enforce_budget(report, args.expected_size)


if __name__ == "__main__":
    main()
