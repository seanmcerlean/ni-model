import pytest
import yaml

from scripts.build_community_model import MULTIPLIERS, SHARES, build_model


def _source_model():
    return {
        "name": "source",
        "description": "source",
        "projection_version": "source",
        "birth_rates": [{"rate": 10.0, "filters": {}, "year_min": 2025}],
        "death_rates": [{"rate": 8.0, "filters": {}, "year_min": 2025}],
        "migration_rates": [
            {"rate": 5.0, "filters": {}, "flow": "in", "year_min": 2025},
            {"rate": -3.0, "filters": {}, "flow": "out", "year_min": 2025},
        ],
        "internal_migration_rates": [],
    }


def test_rules_are_split_across_community_backgrounds():
    model = build_model(_source_model())

    assert len(model["birth_rates"]) == 4
    assert {
        rule["filters"]["religious_background"] for rule in model["birth_rates"]
    } == set(SHARES)
    assert all(
        rule["evidence"] == "estimated_community_differential"
        for rule in model["birth_rates"]
    )


def test_split_rates_preserve_initial_weighted_ni_rate():
    model = build_model(_source_model())

    for section, expected in (
        ("birth_rates", 10.0),
        ("death_rates", 8.0),
    ):
        weighted = sum(
            SHARES[rule["filters"]["religious_background"]] * rule["rate"]
            for rule in model[section]
        )
        assert weighted == pytest.approx(expected, abs=1e-6)


def test_differentials_have_documented_direction():
    assert (
        MULTIPLIERS["birth_rates"]["CATHOLIC"]
        > MULTIPLIERS["birth_rates"]["PROTESTANT"]
    )
    assert (
        MULTIPLIERS["death_rates"]["PROTESTANT"]
        > MULTIPLIERS["death_rates"]["CATHOLIC"]
    )
    assert (
        MULTIPLIERS["migration_in"]["OTHER"] > MULTIPLIERS["migration_in"]["CATHOLIC"]
    )


def test_checked_in_model_is_reproducible():
    with open("models/ni_current.yaml", encoding="utf-8") as source_file:
        expected = build_model(yaml.safe_load(source_file))
    with open("models/ni_current_community.yaml", encoding="utf-8") as model_file:
        assert yaml.safe_load(model_file) == expected
