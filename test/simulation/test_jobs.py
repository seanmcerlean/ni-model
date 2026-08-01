from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

from src.ni_model.core.models import SimulationRun
from src.ni_model.simulation.jobs import (
    claim_next_run,
    cleanup_expired_runs,
    execute_run,
    recover_interrupted_runs,
)


def test_claim_next_run_uses_durable_pending_queue(postgres_db_session):
    first = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2025,
        status="pending",
        base_population_count=1,
    )
    second = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2025,
        status="pending",
        base_population_count=1,
    )
    postgres_db_session.add_all([first, second])
    postgres_db_session.commit()

    claimed = claim_next_run(postgres_db_session)

    assert claimed == first.id
    postgres_db_session.refresh(first)
    assert first.status == "running"
    assert second.status == "pending"


def test_worker_startup_recovers_interrupted_statuses(postgres_db_session):
    running = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2030,
        status="running",
        base_population_count=1,
    )
    cancelling = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2030,
        status="cancelling",
        base_population_count=1,
    )
    postgres_db_session.add_all([running, cancelling])
    postgres_db_session.commit()

    assert recover_interrupted_runs(postgres_db_session) == 2

    postgres_db_session.refresh(running)
    postgres_db_session.refresh(cancelling)
    assert running.status == "pending"
    assert cancelling.status == "cancelled"
    assert cancelling.completed_at is not None


def test_retention_cleanup_deletes_only_expired_terminal_runs(postgres_db_session):
    expired = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2025,
        status="complete",
        completed_at=datetime.now(UTC) - timedelta(days=31),
        base_population_count=1,
    )
    recent = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2025,
        status="complete",
        completed_at=datetime.now(UTC),
        base_population_count=1,
    )
    postgres_db_session.add_all([expired, recent])
    postgres_db_session.commit()

    assert cleanup_expired_runs(postgres_db_session) == 1
    assert postgres_db_session.get(SimulationRun, expired.id) is None
    assert postgres_db_session.get(SimulationRun, recent.id) is not None


def test_execution_timeout_marks_run_failed(postgres_db_session, monkeypatch):
    run = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2026,
        status="running",
        base_population_count=1,
    )
    postgres_db_session.add(run)
    postgres_db_session.commit()
    factory = sessionmaker(bind=postgres_db_session.get_bind(), autoflush=False)

    from src.ni_model.api.routes import simulation

    monkeypatch.setattr(simulation, "_load_director", lambda *args: object())
    monkeypatch.setattr(
        simulation,
        "_columnar_years",
        lambda *args: iter([({"year": 2025}, object())]),
    )
    elapsed = iter([0.0, 2.0])
    monkeypatch.setattr(
        "src.ni_model.simulation.jobs.time.monotonic", lambda: next(elapsed)
    )
    monkeypatch.setenv("SIMULATION_TIMEOUT_SECONDS", "1")

    execute_run(run.id, factory, already_claimed=True)

    postgres_db_session.expire_all()
    failed = postgres_db_session.get(SimulationRun, run.id)
    assert failed.status == "failed"
    assert "execution limit" in failed.error
