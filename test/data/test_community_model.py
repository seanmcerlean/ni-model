import csv

import pytest
import yaml

from scripts.build_community_model import (
    CURRENT_NONE_TO_BACKGROUND,
    MULTIPLIERS,
    SHARES,
    build_model,
)


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
    assert len(set(MULTIPLIERS["migration_out"].values())) == 1


def test_immigration_uses_observed_joint_arrival_profiles():
    model = build_model(_source_model())

    incoming = [rule for rule in model["migration_rates"] if rule["rate"] >= 0]
    outgoing = [rule for rule in model["migration_rates"] if rule["rate"] < 0]
    assert len(incoming) == 1
    assert len(outgoing) == 4
    assert incoming[0]["evidence"] == (
        "census_2021_arrival_profile_scaled_to_annual_total"
    )
    assert len(model["immigration_profiles"]) == 230
    assert {profile["origin"] for profile in model["immigration_profiles"]} == {
        "GB",
        "ROI",
        "OTHER",
    }


def test_arrivals_bridge_current_religion_to_community_background():
    profiles = build_model(_source_model())["immigration_profiles"]
    total_weight = sum(profile["weight"] for profile in profiles)
    none_weight = sum(
        profile["weight"]
        for profile in profiles
        if profile["religious_background"] == "NONE"
    )

    assert total_weight == pytest.approx(27_257)
    assert none_weight == pytest.approx(10_510 * CURRENT_NONE_TO_BACKGROUND["NONE"])


def test_checked_in_arrival_profile_preserves_census_composition():
    with open(
        "data/ni_external_arrivals_lgd_2021_by_religion.csv",
        encoding="utf-8",
        newline="",
    ) as source:
        rows = list(csv.DictReader(source))

    assert sum(int(row["count"]) for row in rows) == 27_257
    assert {row["origin"] for row in rows} == {"gb", "roi", "other"}
    assert {row["religious_background"] for row in rows} == {
        "catholic",
        "protestant",
        "other",
        "none",
    }
    assert len({row["destination_code"] for row in rows}) == 11


def test_checked_in_model_is_reproducible():
    with open("models/ni_current.yaml", encoding="utf-8") as source_file:
        expected = build_model(yaml.safe_load(source_file))
    with open("models/ni_current_community.yaml", encoding="utf-8") as model_file:
        assert yaml.safe_load(model_file) == expected
