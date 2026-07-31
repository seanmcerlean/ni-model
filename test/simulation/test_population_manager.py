from datetime import datetime

import pytest

from src.ni_model.core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
    SimulationSnapshot,
)
from src.ni_model.simulation.population_manager import PopulationManager


def _sample_persons():
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


@pytest.fixture
def run_and_manager(postgres_db_session):
    postgres_db_session.add_all(_sample_persons())
    postgres_db_session.commit()
    run = PopulationManager.create_run(
        postgres_db_session,
        "models/ni_base_2024.yaml",
        2024,
        2030,
    )
    return run, PopulationManager(postgres_db_session, run.id)


def test_create_run_clones_immutable_baseline(postgres_db_session, run_and_manager):
    run, manager = run_and_manager

    assert run.base_population_count == 3
    assert manager.get_population_count() == 3
    assert (
        postgres_db_session.query(Person).filter(Person.run_id.is_(None)).count() == 3
    )


def test_clear_and_reset_affect_only_run(postgres_db_session, run_and_manager):
    _, manager = run_and_manager

    assert manager.clear_population() == 3
    assert manager.get_population_count() == 0
    assert (
        postgres_db_session.query(Person).filter(Person.run_id.is_(None)).count() == 3
    )
    assert manager.reset_to_baseline() == 3


def test_snapshot_is_durable_and_retrievable(postgres_db_session, run_and_manager):
    run, manager = run_and_manager
    data = {"year": 2024, "total_population": 3}

    snapshot = manager.create_snapshot("year_2024", 2024, data)
    postgres_db_session.commit()
    reloaded = PopulationManager(postgres_db_session, run.id).get_snapshot(2024)

    assert snapshot.snapshot_id == "year_2024"
    assert snapshot.population_count == 3
    assert isinstance(snapshot.timestamp, datetime)
    assert reloaded is not None
    assert reloaded.demographics == data
    assert (
        postgres_db_session.query(SimulationSnapshot)
        .filter(SimulationSnapshot.run_id == run.id)
        .count()
        == 1
    )


def test_snapshot_upsert_list_and_delete(run_and_manager):
    _, manager = run_and_manager
    manager.create_snapshot("year_2024", 2024, {"total_population": 3})
    manager.create_snapshot("year_2024", 2024, {"total_population": 4})
    manager.create_snapshot("year_2025", 2025, {"total_population": 5})

    snapshots = manager.list_snapshots()

    assert [snapshot.year for snapshot in snapshots] == [2024, 2025]
    assert snapshots[0].population_count == 4
    assert manager.delete_snapshot("year_2024") is True
    assert manager.get_snapshot(2024) is None
    assert manager.delete_snapshot("invalid") is False


def test_manager_requires_run_for_baseline_restore(postgres_db_session):
    with pytest.raises(ValueError, match="run_id"):
        PopulationManager(postgres_db_session).reset_to_baseline()


def test_demographics_are_run_scoped(run_and_manager):
    _, manager = run_and_manager

    summary = manager.get_demographics_summary()

    assert summary["total_population"] == 3
    assert summary["religious_breakdown"] == {
        "catholic": 2,
        "protestant": 1,
    }
