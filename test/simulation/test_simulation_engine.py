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
from src.ni_model.simulation.simulation_engine import SimulationEngine


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
def director(postgres_db_session):
    return ModelDirector.from_yaml(postgres_db_session, "models/ni_base_2024.yaml")


def test_engine_runs_sequential_pattern(
    postgres_db_session, initial_population, director
):
    """Test births → deaths → migration executed in sequence"""
    engine = SimulationEngine(postgres_db_session, director)
    initial_count = initial_population.count()

    result = engine.run_simulation_year(2024)

    assert result["year"] == 2024
    assert isinstance(result["births"], int)
    assert isinstance(result["deaths"], int)
    assert isinstance(result["migration"], int)
    assert (
        result["net_change"]
        == result["births"] - result["deaths"] + result["migration"]
    )
    assert initial_population.count() == initial_count + result["net_change"]


def test_engine_result_structure(postgres_db_session, initial_population, director):
    """Test result dict contains all expected keys"""
    engine = SimulationEngine(postgres_db_session, director)
    result = engine.run_simulation_year(2025)

    assert set(result.keys()) == {
        "year",
        "births",
        "deaths",
        "migration",
        "internal_migration",
        "net_change",
    }
    assert result["year"] == 2025


def test_engine_multiple_years(postgres_db_session, initial_population, director):
    """Test running simulation across multiple years"""
    engine = SimulationEngine(postgres_db_session, director)

    results = [engine.run_simulation_year(year) for year in range(2024, 2027)]

    assert len(results) == 3
    assert [r["year"] for r in results] == [2024, 2025, 2026]


def test_engine_commits_each_step(postgres_db_session, initial_population, director):
    """Test population count changes after simulation year"""
    engine = SimulationEngine(postgres_db_session, director)

    count_before = initial_population.count()
    result = engine.run_simulation_year(2024)
    postgres_db_session.commit()
    count_after = initial_population.count()

    assert count_after == count_before + result["net_change"]
