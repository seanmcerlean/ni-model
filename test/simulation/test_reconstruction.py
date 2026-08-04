import uuid

import polars as pl

from src.ni_model.core.models import SimulationPersonEvent
from src.ni_model.simulation.columnar_worker import COLUMN_TYPES
from src.ni_model.simulation.reconstruction import PopulationReconstructor


def test_apply_events_reconstructs_birth_death_and_relocation():
    first_id = uuid.UUID(int=1)
    second_id = uuid.UUID(int=2)
    population = pl.DataFrame(
        {
            "person_id": [first_id.bytes],
            "person_number": [1],
            "birth_year": [1990],
            "religious_background": ["catholic"],
            "probable_community": ["catholic"],
            "gender": ["female"],
            "education_level": ["tertiary"],
            "location": ["derry_strabane"],
            "origin": ["ni"],
        },
        schema=COLUMN_TYPES,
    )
    second = {
        "person_id": str(second_id),
        "person_number": 2,
        "birth_year": 2025,
        "religious_background": "catholic",
        "probable_community": "catholic",
        "gender": "male",
        "education_level": "pre_primary",
        "location": "derry_strabane",
        "origin": "ni",
    }
    events = [
        SimulationPersonEvent(
            id=1,
            person_id=second_id,
            year=2025,
            event_type="birth",
            data=second,
        ),
        SimulationPersonEvent(
            id=2,
            person_id=first_id,
            year=2025,
            event_type="relocation",
            data={"from": "derry_strabane", "to": "belfast"},
        ),
        SimulationPersonEvent(
            id=3,
            person_id=first_id,
            year=2025,
            event_type="integration",
            data={"from": "catholic", "to": "none"},
        ),
        SimulationPersonEvent(
            id=4,
            person_id=second_id,
            year=2026,
            event_type="death",
            data={},
        ),
    ]

    reconstructed = PopulationReconstructor.apply_events(population, events)

    assert reconstructed.height == 1
    assert reconstructed.row(0, named=True)["person_id"] == first_id.bytes
    assert reconstructed.row(0, named=True)["location"] == "belfast"
    assert reconstructed.row(0, named=True)["religious_background"] == "none"
    assert reconstructed.row(0, named=True)["probable_community"] == "catholic"
