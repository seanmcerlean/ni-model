import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from src.ni_model.core.database import Base
from src.ni_model.core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)
from src.ni_model.data.repository import PersonRepository
from src.ni_model.simulation.model_director import ModelDirector
from src.ni_model.simulation.orchestrator import SimulationOrchestrator
from src.ni_model.simulation.population_manager import PopulationManager


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture
def postgres_db_session(postgres_container):
    engine = create_engine(postgres_container.get_connection_url())
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def initial_population(postgres_db_session):
    repo = PersonRepository(postgres_db_session)
    persons = [
        Person(
            age=20 + (i % 60),
            religious_background=(
                ReligiousBackground.CATHOLIC
                if i % 2 == 0
                else ReligiousBackground.PROTESTANT
            ),
            gender=Gender.MALE if i % 2 == 0 else Gender.FEMALE,
            education_level=EducationLevel.TERTIARY,
            location=Location.BELFAST_NORTH if i < 50 else Location.DERRY,
            origin=Origin.NI,
        )
        for i in range(100)
    ]
    repo.bulk_create(persons)
    return repo


@pytest.fixture
def large_population(postgres_db_session):
    """10,000 person population guarantees demographic changes at configured rates"""
    repo = PersonRepository(postgres_db_session)
    persons = [
        Person(
            age=20 + (i % 60),
            religious_background=(
                ReligiousBackground.CATHOLIC
                if i % 2 == 0
                else ReligiousBackground.PROTESTANT
            ),
            gender=Gender.MALE if i % 2 == 0 else Gender.FEMALE,
            education_level=EducationLevel.TERTIARY,
            location=Location.BELFAST_NORTH if i < 5000 else Location.DERRY,
            origin=Origin.NI,
        )
        for i in range(10_000)
    ]
    repo.bulk_create(persons)
    return repo


@pytest.fixture
def orchestrator(postgres_db_session):
    director = ModelDirector.from_yaml(postgres_db_session, "models/ni_base_2024.yaml")
    return SimulationOrchestrator(postgres_db_session, director)


def test_orchestrator_single_year(
    postgres_db_session, initial_population, orchestrator
):
    """Test running a single year simulation"""
    results = orchestrator.run(2024, 2024)

    assert len(results) == 1
    assert results[0]["year"] == 2024
    assert "births" in results[0]
    assert "deaths" in results[0]
    assert "migration" in results[0]
    assert "net_change" in results[0]


def test_orchestrator_multi_year(postgres_db_session, initial_population, orchestrator):
    """Test running a multi-year simulation"""
    results = orchestrator.run(2024, 2027)

    assert len(results) == 4
    assert [r["year"] for r in results] == [2024, 2025, 2026, 2027]


def test_orchestrator_population_changes(
    postgres_db_session, initial_population, orchestrator
):
    """Test population changes after simulation"""
    initial_count = initial_population.count()
    results = orchestrator.run(2024, 2026)

    total_net_change = sum(r["net_change"] for r in results)
    assert initial_population.count() == initial_count + total_net_change


def test_orchestrator_get_result(postgres_db_session, initial_population, orchestrator):
    """Test retrieving result for specific year"""
    orchestrator.run(2024, 2026)

    result_2025 = orchestrator.get_result(2025)

    assert result_2025 is not None
    assert result_2025["year"] == 2025


def test_orchestrator_get_result_missing_year(
    postgres_db_session, initial_population, orchestrator
):
    """Test retrieving result for year not in simulation"""
    orchestrator.run(2024, 2025)

    assert orchestrator.get_result(2030) is None


def test_orchestrator_rollback(postgres_db_session, large_population, orchestrator):
    """Test durable baseline restoration for an isolated run."""
    run = PopulationManager.create_run(
        postgres_db_session, "models/ni_base_2024.yaml", 2024, 2024
    )
    director = ModelDirector.from_yaml(
        postgres_db_session, run.model_path, run_id=run.id
    )
    run_orchestrator = SimulationOrchestrator(postgres_db_session, director)
    run_repo = PersonRepository(postgres_db_session, run_id=run.id)
    initial_count = run_repo.count()

    run_orchestrator.run(2024, 2024)
    count_after_run = run_repo.count()

    assert (
        count_after_run != initial_count
    ), f"Expected population change with {initial_count} persons"

    rolled_back = run_orchestrator.rollback_to_year(2024)

    assert rolled_back is True
    assert run_repo.count() == initial_count


def test_orchestrator_get_population_count(
    postgres_db_session, initial_population, orchestrator
):
    """Test getting current population count"""
    initial_count = initial_population.count()

    assert orchestrator.get_population_count() == initial_count


def test_orchestrator_get_demographics(
    postgres_db_session, initial_population, orchestrator
):
    """Test getting current demographics"""
    demographics = orchestrator.get_demographics()

    assert "total_population" in demographics
    assert "religious_breakdown" in demographics
    assert "gender_breakdown" in demographics
    assert demographics["total_population"] == initial_population.count()
