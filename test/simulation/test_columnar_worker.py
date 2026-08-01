import uuid

import polars as pl

from src.ni_model.simulation.columnar_worker import (
    COLUMN_TYPES,
    ColumnarSimulationWorker,
)


def population(size=1_000):
    return pl.DataFrame(
        {
            "person_id": [uuid.UUID(int=index + 1).bytes for index in range(size)],
            "person_number": range(1, size + 1),
            "birth_year": [1975 + index % 30 for index in range(size)],
            "religious_background": [
                "catholic" if index % 2 else "protestant" for index in range(size)
            ],
            "gender": ["female" if index % 2 else "male" for index in range(size)],
            "education_level": ["secondary"] * size,
            "location": [
                "derry_strabane" if index < size // 2 else "belfast"
                for index in range(size)
            ],
            "origin": ["ni"] * size,
        },
        schema=COLUMN_TYPES,
    )


def config():
    return {
        "random_seed": 42,
        "rate_jitter": 0.0,
        "birth_rates": [{"rate": 20.0, "filters": {}}],
        "death_rates": [{"rate": 10.0, "filters": {}}],
        "migration_rates": [
            {"rate": 10.0, "filters": {}},
            {"rate": -5.0, "filters": {}},
        ],
        "internal_migration_rates": [
            {
                "rate": 100.0,
                "filters": {"location": "DERRY_STRABANE"},
                "destination": "BELFAST",
            }
        ],
    }


def test_columnar_worker_runs_full_individual_population_without_age_updates():
    worker = ColumnarSimulationWorker(population(), config(), uuid.UUID(int=99))
    original_birth_years = dict(
        worker.population.select("person_id", "birth_year").iter_rows()
    )

    result = worker.run_year(2025)

    assert result["births"] == 20
    assert result["deaths"] == 10
    assert result["immigration"] == 10
    assert result["emigration"] == 5
    assert worker.population.height == 1_015
    survivors = worker.population.filter(
        pl.col("person_id").is_in(list(original_birth_years))
    )
    assert all(
        original_birth_years[person_id] == birth_year
        for person_id, birth_year in survivors.select(
            "person_id", "birth_year"
        ).iter_rows()
    )
    assert {event.event_type for event in worker.events} == {
        "arrival",
        "birth",
        "death",
        "departure",
        "relocation",
    }


def test_columnar_worker_is_deterministic_for_seed_run_and_year():
    run_id = uuid.UUID(int=101)
    first = ColumnarSimulationWorker(population(), config(), run_id)
    second = ColumnarSimulationWorker(population(), config(), run_id)

    assert first.run_year(2025) == second.run_year(2025)
    assert first.checkpoint_digest() == second.checkpoint_digest()
    assert first.events == second.events


def test_columnar_worker_applies_community_and_age_filters():
    filtered_config = {
        "random_seed": 7,
        "rate_jitter": 0.0,
        "birth_rates": [],
        "death_rates": [
            {
                "rate": 1000.0,
                "filters": {
                    "religious_background": "CATHOLIC",
                    "age_min": 35,
                },
            }
        ],
        "migration_rates": [],
        "internal_migration_rates": [],
    }
    worker = ColumnarSimulationWorker(population(100), filtered_config, uuid.uuid4())

    result = worker.run_year(2025)

    assert result["deaths"] > 0
    remaining = worker.population.with_columns(
        (2025 - pl.col("birth_year")).alias("age")
    )
    assert remaining.filter(
        (pl.col("religious_background") == "catholic") & (pl.col("age") >= 35)
    ).is_empty()
