from datetime import datetime

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
from src.ni_model.simulation.population_manager import PopulationManager


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for testing"""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture
def postgres_db_session(postgres_container):
    """Create PostgreSQL database session"""
    engine = create_engine(postgres_container.get_connection_url())
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def population_manager(postgres_db_session):
    """Create PopulationManager with PostgreSQL database"""
    return PopulationManager(postgres_db_session)


@pytest.fixture
def sample_persons():
    """Create sample persons for testing"""
    return [
        Person(
            age=25,
            religious_background=ReligiousBackground.CATHOLIC,
            gender=Gender.MALE,
            education_level=EducationLevel.TERTIARY,
            location=Location.BELFAST_NORTH,
            origin=Origin.NI,
        ),
        Person(
            age=35,
            religious_background=ReligiousBackground.PROTESTANT,
            gender=Gender.FEMALE,
            education_level=EducationLevel.SECONDARY,
            location=Location.DERRY,
            origin=Origin.NI,
        ),
        Person(
            age=45,
            religious_background=ReligiousBackground.CATHOLIC,
            gender=Gender.MALE,
            education_level=EducationLevel.PRIMARY,
            location=Location.BELFAST_NORTH,
            origin=Origin.NI,
        ),
    ]


def test_initialize_population(population_manager, sample_persons):
    """Test population initialization"""
    count = population_manager.initialize_population(sample_persons)

    assert count == 3
    assert population_manager.get_population_count() == 3


def test_clear_population(population_manager, sample_persons):
    """Test population clearing"""
    # Initialize population first
    population_manager.initialize_population(sample_persons)
    assert population_manager.get_population_count() == 3

    # Clear population
    cleared_count = population_manager.clear_population()

    assert cleared_count == 3
    assert population_manager.get_population_count() == 0


def test_create_snapshot(population_manager, sample_persons):
    """Test snapshot creation"""
    # Initialize population
    population_manager.initialize_population(sample_persons)

    # Create snapshot
    snapshot = population_manager.create_snapshot("test_snapshot", 2024)

    assert snapshot.snapshot_id == "test_snapshot"
    assert snapshot.year == 2024
    assert snapshot.population_count == 3
    assert isinstance(snapshot.timestamp, datetime)
    assert isinstance(snapshot.demographics, dict)
    assert snapshot.savepoint_name == "sp_test_snapshot"


def test_get_snapshot(population_manager, sample_persons):
    """Test snapshot retrieval"""
    population_manager.initialize_population(sample_persons)

    # Create snapshot
    original_snapshot = population_manager.create_snapshot("test_snapshot", 2024)

    # Retrieve snapshot
    retrieved_snapshot = population_manager.get_snapshot("test_snapshot")

    assert retrieved_snapshot is not None
    assert retrieved_snapshot.snapshot_id == original_snapshot.snapshot_id
    assert retrieved_snapshot.year == original_snapshot.year
    assert retrieved_snapshot.population_count == original_snapshot.population_count


def test_get_nonexistent_snapshot(population_manager):
    """Test retrieving non-existent snapshot"""
    snapshot = population_manager.get_snapshot("nonexistent")
    assert snapshot is None


def test_list_snapshots(population_manager, sample_persons):
    """Test listing snapshots"""
    population_manager.initialize_population(sample_persons)

    # Create multiple snapshots
    population_manager.create_snapshot("snapshot1", 2024)
    population_manager.create_snapshot("snapshot2", 2025)

    snapshots = population_manager.list_snapshots()

    assert len(snapshots) == 2
    snapshot_ids = [s.snapshot_id for s in snapshots]
    assert "snapshot1" in snapshot_ids
    assert "snapshot2" in snapshot_ids


def test_delete_snapshot(population_manager, sample_persons):
    """Test snapshot deletion"""
    population_manager.initialize_population(sample_persons)

    # Create snapshot
    population_manager.create_snapshot("test_snapshot", 2024)
    assert population_manager.get_snapshot("test_snapshot") is not None

    # Delete snapshot
    deleted = population_manager.delete_snapshot("test_snapshot")

    assert deleted is True
    assert population_manager.get_snapshot("test_snapshot") is None


def test_delete_nonexistent_snapshot(population_manager):
    """Test deleting non-existent snapshot"""
    deleted = population_manager.delete_snapshot("nonexistent")
    assert deleted is False


def test_restore_snapshot(population_manager, sample_persons):
    """Test snapshot restoration"""
    # Initialize population
    population_manager.initialize_population(sample_persons)
    original_count = population_manager.get_population_count()

    # Create snapshot
    population_manager.create_snapshot("test_snapshot", 2024)

    # Modify population (clear it)
    population_manager.clear_population()
    assert population_manager.get_population_count() == 0

    # Restore snapshot
    restored = population_manager.restore_snapshot("test_snapshot")

    assert restored is True
    assert population_manager.get_population_count() == original_count


def test_restore_nonexistent_snapshot(population_manager):
    """Test restoring non-existent snapshot"""
    restored = population_manager.restore_snapshot("nonexistent")
    assert restored is False


def test_get_demographics_summary(population_manager, sample_persons):
    """Test demographics summary"""
    population_manager.initialize_population(sample_persons)

    summary = population_manager.get_demographics_summary()

    assert summary["total_population"] == 3
    assert "age_stats" in summary
    assert "religious_breakdown" in summary
    assert "gender_breakdown" in summary


def test_multiple_snapshot_rollback_cycles(population_manager, sample_persons):
    """Test multiple snapshot and rollback cycles maintain data integrity"""
    # Initialize with sample population
    population_manager.initialize_population(sample_persons)
    original_count = population_manager.get_population_count()

    # Create first snapshot
    population_manager.create_snapshot("snapshot1", 2024)

    # Modify population
    population_manager.clear_population()

    # Restore first snapshot
    population_manager.restore_snapshot("snapshot1")
    assert population_manager.get_population_count() == original_count

    # Create another snapshot after restore
    population_manager.create_snapshot("snapshot2", 2025)

    # Clear again
    population_manager.clear_population()

    # Restore second snapshot
    population_manager.restore_snapshot("snapshot2")
    assert population_manager.get_population_count() == original_count


def test_snapshot_demographics_consistency(population_manager, sample_persons):
    """Test that snapshot demographics match actual population"""
    population_manager.initialize_population(sample_persons)

    # Get current demographics
    current_demographics = population_manager.get_demographics_summary()

    # Create snapshot
    snapshot = population_manager.create_snapshot("test_snapshot", 2024)

    # Compare demographics
    assert (
        snapshot.demographics["total_population"]
        == current_demographics["total_population"]
    )
    assert (
        snapshot.demographics["religious_breakdown"]
        == current_demographics["religious_breakdown"]
    )
    assert (
        snapshot.demographics["gender_breakdown"]
        == current_demographics["gender_breakdown"]
    )
