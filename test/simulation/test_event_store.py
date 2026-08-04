import uuid

import polars as pl
import pytest

from src.ni_model.core.models import (
    SimulationCheckpoint,
    SimulationPersonEvent,
    SimulationRun,
)
from src.ni_model.simulation.columnar_worker import COLUMN_TYPES, PopulationEvent
from src.ni_model.simulation.event_store import EventStore


def test_event_store_appends_events_and_round_trips_checkpoint(
    postgres_db_session, tmp_path
):
    run = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2025,
        base_population_count=1,
    )
    postgres_db_session.add(run)
    postgres_db_session.flush()
    person_id = uuid.uuid4()
    population = pl.DataFrame(
        {
            "person_id": [person_id.bytes],
            "person_number": [1],
            "birth_year": [1990],
            "religious_background": ["catholic"],
            "probable_community": ["catholic"],
            "gender": ["female"],
            "education_level": ["tertiary"],
            "location": ["belfast"],
            "origin": ["ni"],
        },
        schema=COLUMN_TYPES,
    )
    store = EventStore(postgres_db_session, tmp_path)

    assert (
        store.append(
            run.id,
            [PopulationEvent(person_id.bytes, 2025, "relocation", {"to": "belfast"})],
        )
        == 1
    )
    checkpoint = store.checkpoint(run.id, 2025, population)
    postgres_db_session.commit()

    assert postgres_db_session.query(SimulationPersonEvent).count() == 1
    assert postgres_db_session.query(SimulationCheckpoint).count() == 1
    assert checkpoint.byte_size > 0
    assert len(checkpoint.checksum) == 64
    assert EventStore.load(checkpoint).equals(population)

    store.delete_run(run.id)

    assert not tmp_path.joinpath(str(run.id), "2025.parquet").exists()


def test_checkpoint_storage_limit_is_enforced(
    postgres_db_session, tmp_path, monkeypatch
):
    run = SimulationRun(
        model_path="models/ni_current.yaml",
        start_year=2025,
        end_year=2025,
        base_population_count=1,
    )
    postgres_db_session.add(run)
    postgres_db_session.flush()
    population = pl.DataFrame(
        {
            "person_id": [uuid.uuid4().bytes],
            "person_number": [1],
            "birth_year": [1990],
            "religious_background": ["catholic"],
            "probable_community": ["catholic"],
            "gender": ["female"],
            "education_level": ["tertiary"],
            "location": ["belfast"],
            "origin": ["ni"],
        },
        schema=COLUMN_TYPES,
    )
    monkeypatch.setenv("MAX_CHECKPOINT_BYTES_PER_RUN", "1")

    with pytest.raises(RuntimeError, match="storage limit"):
        EventStore(postgres_db_session, tmp_path).checkpoint(run.id, 2025, population)

    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.parquet"))
