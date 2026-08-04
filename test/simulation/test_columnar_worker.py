import uuid
from copy import deepcopy

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
            "probable_community": [
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
    same_seed = ColumnarSimulationWorker(
        population(), config(), uuid.UUID(int=99)
    ).run_year(2025)
    different_seed = ColumnarSimulationWorker(
        population(), config(), uuid.UUID(int=99), seed=44
    ).run_year(2025)

    assert result == same_seed
    assert result["births"] != different_seed["births"]
    assert result["deaths"] == 10
    assert result["immigration"] == 10
    assert result["emigration"] == 5
    assert worker.population.height == 1_000 + result["net_change"]
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


def test_columnar_worker_preserves_compact_schema_across_years():
    worker = ColumnarSimulationWorker(population(), config(), uuid.UUID(int=102))

    worker.run_year(2025)
    worker.run_year(2026)

    assert worker.population.schema == COLUMN_TYPES


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


def test_columnar_worker_weights_crude_deaths_by_age():
    people = population(1_000).with_columns(
        pl.Series("birth_year", [2005] * 500 + [1935] * 500).cast(pl.Int16)
    )
    weighted_config = {
        "random_seed": 17,
        "rate_jitter": 0.0,
        "birth_rates": [],
        "death_rates": [{"rate": 100.0, "filters": {}}],
        "mortality_age_rates": [
            {"age_min": 0, "age_max": 64, "rate": 1.0},
            {"age_min": 65, "age_max": 130, "rate": 100.0},
        ],
        "migration_rates": [],
        "internal_migration_rates": [],
    }
    worker = ColumnarSimulationWorker(people, weighted_config, uuid.uuid4())
    old_ids = set(people.tail(500)["person_id"])

    result = worker.run_year(2025)

    death_ids = {
        event.person_id for event in worker.events if event.event_type == "death"
    }
    assert result["deaths"] == 100
    assert len(death_ids & old_ids) >= 95


def test_columnar_worker_applies_competing_integration_flows_simultaneously():
    integration_config = {
        "random_seed": 3,
        "rate_jitter": 0.0,
        "birth_rates": [],
        "death_rates": [],
        "migration_rates": [],
        "internal_migration_rates": [],
        "integration_rates": [
            {
                "rate": 100.0,
                "destination": "NONE",
                "filters": {"religious_background": "CATHOLIC"},
            },
            {
                "rate": 100.0,
                "destination": "OTHER",
                "filters": {"religious_background": "CATHOLIC"},
            },
        ],
    }
    worker = ColumnarSimulationWorker(
        population(1_000), integration_config, uuid.uuid4()
    )

    result = worker.run_year(2025)

    assert 50 < result["community_transitions"] < 150
    assert (
        sum(result["community_transition_breakdown"].values())
        == result["community_transitions"]
    )
    assert {event.event_type for event in worker.events} == {"integration"}


def test_columnar_worker_assigns_child_background_from_parent_rule():
    child_config = {
        "random_seed": 7,
        "rate_jitter": 0.0,
        "birth_rates": [
            {
                "rate": 1000,
                "filters": {"religious_background": "CATHOLIC"},
            }
        ],
        "death_rates": [],
        "migration_rates": [],
        "internal_migration_rates": [],
        "integration_rates": [],
        "child_background_rules": [
            {
                "year_min": 2025,
                "source": "CATHOLIC",
                "probabilities": {"NONE": 1.0},
            }
        ],
    }
    worker = ColumnarSimulationWorker(population(100), child_config, uuid.uuid4())

    result = worker.run_year(2025)
    newborns = worker.population.filter(pl.col("birth_year") == 2025)

    assert result["births"] == 50
    assert set(newborns["religious_background"].to_list()) == {"none"}
    assert set(newborns["probable_community"].to_list()) == {"catholic"}


def test_columnar_worker_uses_explicit_immigration_profiles():
    profile_config = {
        "random_seed": 7,
        "rate_jitter": 0.0,
        "birth_rates": [],
        "death_rates": [],
        "migration_rates": [{"rate": 100.0, "filters": {}}],
        "internal_migration_rates": [],
        "immigration_profiles": [
            {
                "origin": "ROI",
                "location": "DERRY_STRABANE",
                "religious_background": "CATHOLIC",
                "weight": 1,
            }
        ],
    }
    worker = ColumnarSimulationWorker(population(1_000), profile_config, uuid.uuid4())

    result = worker.run_year(2025)
    arrivals = worker.population.tail(result["immigration"])

    assert result["immigration"] == 100
    assert set(arrivals["origin"]) == {"roi"}
    assert set(arrivals["location"]) == {"derry_strabane"}
    assert set(arrivals["religious_background"]) == {"catholic"}
    assert set(arrivals["probable_community"]) == {"catholic"}


def test_historical_component_controls_are_expected_rates_not_exact_outputs():
    controlled = {
        "birth_rates": [{"rate": 100.0, "filters": {}}],
        "death_rates": [{"rate": 50.0, "filters": {}}],
        "migration_rates": [{"rate": -20.0, "filters": {}}],
        "component_baseline_population": 1_000,
        "annual_demographic_components": {
            2025: {
                "births": 100,
                "deaths": 50,
                "population_adjustment": -20,
            }
        },
    }
    first = ColumnarSimulationWorker(
        population(), deepcopy(controlled), uuid.UUID(int=1), seed=42
    )
    second = ColumnarSimulationWorker(
        population(), deepcopy(controlled), uuid.UUID(int=2), seed=44
    )

    first_result = first.run_year(2025)
    second_result = second.run_year(2025)

    assert first_result["deaths"] == second_result["deaths"] == 50
    assert first_result["emigration"] == second_result["emigration"] == 20
    assert first_result["births"] != second_result["births"]
    first._apply_component_controls(2026)
    assert first.config["birth_rates"][0]["rate"] == 100.0
