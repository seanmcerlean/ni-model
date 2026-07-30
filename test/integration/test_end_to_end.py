"""
Integration tests: full stack end-to-end scenarios.
  - Generate realistic population
  - Run multi-year simulation with YAML model
  - Validate snapshots against historical benchmarks
  - Compare two model runs
  - Voting predictions on simulated population
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from src.ni_model.core.database import Base
from src.ni_model.data.population_generator import generate_population
from src.ni_model.data.repository import PersonRepository
from src.ni_model.simulation.model_director import ModelDirector
from src.ni_model.simulation.orchestrator import SimulationOrchestrator
from src.ni_model.simulation.voting_predictor import VotingPredictor
from src.ni_model.validation.historical_validator import HistoricalValidator
from src.ni_model.validation.model_comparator import ModelComparator


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgres:15") as pg:
        yield pg


@pytest.fixture(scope="module")
def engine(postgres_container):
    eng = create_engine(postgres_container.get_connection_url())
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db(engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def populated_db(db):
    """5,000-person realistic NI population seeded into DB."""
    repo = PersonRepository(db)
    persons = generate_population(5_000, seed=42)
    repo.bulk_create(persons)
    db.flush()
    return db


@pytest.fixture
def orchestrator(populated_db):
    director = ModelDirector.from_yaml(populated_db, "models/ni_base_2024.yaml")
    return SimulationOrchestrator(populated_db, director)


# ---------------------------------------------------------------------------
# Population generation integration
# ---------------------------------------------------------------------------


def test_generated_population_persisted(populated_db):
    repo = PersonRepository(populated_db)
    assert repo.count() == 5_000


def test_generated_population_has_all_locations(populated_db):
    from src.ni_model.core.models import Location, Person

    locations = {loc for (loc,) in populated_db.query(Person.location).distinct()}
    assert locations == set(Location)


def test_generated_population_religious_distribution(populated_db):
    from sqlalchemy import func

    from src.ni_model.core.models import Person, ReligiousBackground

    counts = dict(
        populated_db.query(Person.religious_background, func.count(Person.id))
        .group_by(Person.religious_background)
        .all()
    )
    total = sum(counts.values())
    catholic_share = counts[ReligiousBackground.CATHOLIC] / total
    assert 0.40 <= catholic_share <= 0.50


# ---------------------------------------------------------------------------
# Simulation integration
# ---------------------------------------------------------------------------


def test_simulation_runs_multiple_years(populated_db, orchestrator):
    results = orchestrator.run(2010, 2014)
    assert len(results) == 5
    assert [r["year"] for r in results] == [2010, 2011, 2012, 2013, 2014]


def test_simulation_population_changes_over_time(populated_db, orchestrator):
    repo = PersonRepository(populated_db)
    initial = repo.count()
    results = orchestrator.run(2010, 2012)
    total_net = sum(r["net_change"] for r in results)
    assert repo.count() == initial + total_net


def test_simulation_all_result_keys_present(populated_db, orchestrator):
    results = orchestrator.run(2010, 2010)
    assert set(results[0].keys()) == {
        "year",
        "births",
        "deaths",
        "immigration",
        "emigration",
        "migration",
        "internal_migration",
        "net_change",
    }


def test_simulation_births_and_deaths_non_negative(populated_db, orchestrator):
    results = orchestrator.run(2010, 2013)
    for r in results:
        assert r["births"] >= 0
        assert r["deaths"] >= 0


def test_simulation_rollback_restores_population(populated_db, orchestrator):
    repo = PersonRepository(populated_db)
    initial = repo.count()
    orchestrator.run(2010, 2010)
    orchestrator.rollback_to_year(2010)
    assert repo.count() == initial


# ---------------------------------------------------------------------------
# Validation integration
# ---------------------------------------------------------------------------


def test_validator_loads_yaml_benchmarks():
    validator = HistoricalValidator.from_yaml("data/historical_benchmarks.yaml")
    assert len(validator.available_years()) == 6


def test_validator_returns_none_for_non_benchmark_year(populated_db, orchestrator):
    validator = HistoricalValidator.from_yaml("data/historical_benchmarks.yaml")
    orchestrator.run(2025, 2025)
    repo = PersonRepository(populated_db)
    snap = {
        "total_population": repo.count(),
        "religious_breakdown": repo.get_demographics_summary()["religious_breakdown"],
    }
    result = validator.validate(2025, snap)
    assert result is None  # no benchmark for 2025


def test_validator_produces_result_for_benchmark_year(populated_db):
    validator = HistoricalValidator.from_yaml("data/historical_benchmarks.yaml")
    snap = {
        "total_population": 1_810_863,
        "religious_breakdown": {
            "catholic": 817_400,
            "protestant": 875_700,
            "other": 16_600,
            "none": 101_200,
        },
    }
    result = validator.validate(2011, snap)
    assert result is not None
    assert result.accuracy_score == pytest.approx(1.0)
    assert result.within_threshold is True


def test_validator_summary_across_multiple_years():
    validator = HistoricalValidator.from_yaml("data/historical_benchmarks.yaml")
    snapshots = {
        year: {
            "total_population": data["total_population"],
            "religious_breakdown": data["religious_breakdown"],
        }
        for year, data in validator.benchmarks.items()
    }
    results = validator.validate_all(snapshots)
    summary = validator.summary(results)
    assert summary["years_validated"] == 6
    assert summary["mean_accuracy"] == pytest.approx(1.0)
    assert summary["all_within_threshold"] is True


# ---------------------------------------------------------------------------
# Model comparison integration
# ---------------------------------------------------------------------------


def test_compare_two_model_runs(postgres_container):
    """Run same population through two different year ranges and compare."""
    engine = create_engine(postgres_container.get_connection_url())
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def run_scenario(start, end, seed):
        session = Session()
        repo = PersonRepository(session)
        repo.bulk_create(generate_population(2_000, seed=seed))
        session.flush()
        director = ModelDirector.from_yaml(session, "models/ni_base_2024.yaml")
        orch = SimulationOrchestrator(session, director)
        results = orch.run(start, end)
        snapshots = {}
        for r in results:
            demo = repo.get_demographics_summary()
            snapshots[r["year"]] = {
                "total_population": demo["total_population"],
                "religious_breakdown": demo["religious_breakdown"],
            }
        session.rollback()
        session.close()
        return snapshots

    snaps_a = run_scenario(2010, 2012, seed=1)
    snaps_b = run_scenario(2010, 2012, seed=2)

    comparator = ModelComparator("Seed-1", "Seed-2")
    report = comparator.compare(snaps_a, snaps_b)

    assert report.years_compared == [2010, 2011, 2012]
    assert report.mean_rmse >= 0
    assert report.summary != ""


# ---------------------------------------------------------------------------
# Voting prediction integration
# ---------------------------------------------------------------------------


def test_voting_prediction_on_simulated_population(populated_db, orchestrator):
    orchestrator.run(2010, 2012)
    predictor = VotingPredictor(populated_db)
    result = predictor.predict()
    assert result["total_population"] > 0
    total = result["unite_share"] + result["remain_share"] + result["undecided_share"]
    assert total == pytest.approx(1.0, abs=0.01)


def test_voting_prediction_by_location_complete(populated_db):
    from src.ni_model.core.models import Location

    predictor = VotingPredictor(populated_db)
    by_loc = predictor.predict_by_location()
    assert set(by_loc.keys()) == {loc.value for loc in Location}


def test_catholic_majority_population_favours_unite(populated_db):
    predictor = VotingPredictor(populated_db)
    result = predictor.predict()
    # Generated population is ~45% Catholic — should lean Unite
    assert result["unite_share"] > 0.35
