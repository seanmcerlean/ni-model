import uuid

from src.ni_model.api.routes.simulation import (
    _capture_columnar_snapshot,
    _capture_snapshot,
)
from src.ni_model.data.population_generator import generate_population
from src.ni_model.simulation.columnar_worker import ColumnarSimulationWorker
from src.ni_model.simulation.model_director import ModelDirector
from src.ni_model.simulation.orchestrator import SimulationOrchestrator
from src.ni_model.simulation.population_manager import PopulationManager


def _close(actual: int, expected: int, fraction: float = 0.05) -> bool:
    return abs(actual - expected) <= max(10, round(expected * fraction))


def test_vectorized_engine_has_statistical_parity_with_legacy_engine(
    postgres_db_session,
):
    baseline = generate_population(5_000, seed=42)
    for person_number, person in enumerate(baseline, start=1):
        person.id = uuid.uuid4()
        person.person_number = person_number
    postgres_db_session.add_all(baseline)
    postgres_db_session.commit()
    model = "models/ni_current_community.yaml"

    legacy_run = PopulationManager.create_run(
        postgres_db_session,
        model,
        2025,
        2025,
        clone_population=True,
        status="benchmarking",
    )
    legacy_director = ModelDirector.from_yaml(
        postgres_db_session, model, run_id=legacy_run.id
    )
    legacy_result = SimulationOrchestrator(
        postgres_db_session, legacy_director
    ).engine.run_simulation_year(2025)
    postgres_db_session.flush()
    legacy_snapshot = _capture_snapshot(
        legacy_run.id, 2025, legacy_result, postgres_db_session
    )

    columnar_run = PopulationManager.create_run(
        postgres_db_session,
        model,
        2025,
        2025,
        clone_population=False,
        status="benchmarking",
    )
    columnar_director = ModelDirector.from_yaml(
        postgres_db_session, model, run_id=columnar_run.id
    )
    worker = ColumnarSimulationWorker.load_baseline(
        postgres_db_session,
        columnar_director.config,
        columnar_run.id,
        2025,
        seed=columnar_director.seed,
    )
    columnar_result = worker.run_year(2025)
    columnar_snapshot = _capture_columnar_snapshot(
        worker, columnar_run.id, 2025, columnar_result, postgres_db_session
    )

    for component in (
        "births",
        "deaths",
        "immigration",
        "emigration",
        "internal_migration",
    ):
        assert _close(columnar_result[component], legacy_result[component])
    assert _close(
        columnar_snapshot.total_population, legacy_snapshot.total_population, 0.01
    )
    for background, expected in legacy_snapshot.religious_breakdown.items():
        assert _close(columnar_snapshot.religious_breakdown[background], expected)
    for location, expected in legacy_snapshot.location_breakdown.items():
        assert _close(columnar_snapshot.location_breakdown[location], expected)
    for calibration in legacy_snapshot.voting_predictions:
        legacy_vote = legacy_snapshot.voting_predictions[calibration]
        columnar_vote = columnar_snapshot.voting_predictions[calibration]
        assert abs(columnar_vote.unite_share - legacy_vote.unite_share) < 0.02
        assert abs(columnar_vote.remain_share - legacy_vote.remain_share) < 0.02
