import csv
from pathlib import Path

import pytest
import yaml

from scripts.build_current_model import _controlled_counts

DATA_PATH = Path("data/ni_population_projection_2024_2074.csv")
MODEL_PATH = Path("models/ni_current.yaml")
COMMUNITY_MIGRATION_PATH = Path("data/ni_internal_migration_lgd_2021_by_religion.csv")


def _rows():
    with DATA_PATH.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def test_disclosure_affected_subgroups_are_controlled_to_total_flow():
    controlled = _controlled_counts(
        {"catholic": 5, "protestant": 3, "other": 1, "none": 1}, 12
    )

    assert controlled == {"catholic": 6, "protestant": 4, "other": 1, "none": 1}
    assert sum(controlled.values()) == 12


def test_current_series_covers_observations_and_principal_projection():
    rows = _rows()

    assert len(rows) == 53
    assert int(rows[0]["year"]) == 2022
    assert int(rows[-1]["year"]) == 2074
    assert int(rows[2]["population_end"]) == 1_927_855
    assert int(rows[3]["population_start"]) == 1_927_855


def test_projected_components_reconcile_to_population():
    for row in _rows()[3:]:
        start = int(row["population_start"])
        births = int(row["births"])
        deaths = int(row["deaths"])
        migration = int(row["net_migration"])
        adjustment = int(row["reconciliation_adjustment"])
        end = int(row["population_end"])

        assert end == start + births - deaths + migration + adjustment
        assert migration == int(row["immigration"]) - int(row["emigration"])


def test_current_model_rates_are_derived_from_checked_in_series():
    rows = _rows()
    model = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))

    assert model["baseline_year"] == 2021
    assert model["data_through"] == 2024
    assert model["rate_jitter"] == 0
    with COMMUNITY_MIGRATION_PATH.open(encoding="utf-8", newline="") as source:
        community_flows = list(csv.DictReader(source))
    assert len(model["internal_migration_rates"]) == len(community_flows)
    assert len(model["birth_rates"]) == len(rows)
    assert len(model["death_rates"]) == len(rows)
    assert len(model["migration_rates"]) == 3 + 2 * 50

    first = rows[0]
    expected_birth_rate = int(first["births"]) * 1000 / int(first["population_start"])
    assert model["birth_rates"][0]["rate"] == pytest.approx(
        expected_birth_rate, abs=0.000001
    )

    projected = rows[3]
    before_migration = (
        int(projected["population_start"])
        + int(projected["births"])
        - int(projected["deaths"])
    )
    expected_inflow_rate = int(projected["immigration"]) * 1000 / before_migration
    assert model["migration_rates"][3]["rate"] == pytest.approx(
        expected_inflow_rate, abs=0.000001
    )
    assert model["migration_rates"][3]["flow"] == "in"
    assert model["migration_rates"][4]["flow"] == "out"


def test_internal_flows_cover_every_ordered_lgd_pair():
    with Path("data/ni_internal_migration_lgd_2021.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 11 * 10
    assert sum(int(row["count"]) for row in rows) == 38_074
    assert all(row["source"] != row["destination"] for row in rows)
    assert all(float(row["rate_per_1000"]) > 0 for row in rows)


def test_internal_flows_use_observed_religion_specific_mover_composition():
    with COMMUNITY_MIGRATION_PATH.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert sum(int(row["count"]) for row in rows) == 38_074
    assert len({(row["source"], row["destination"]) for row in rows}) == 110
    assert {row["religious_background"] for row in rows} == {
        "catholic",
        "protestant",
        "other",
        "none",
    }
    assert all(int(row["count"]) > 0 for row in rows)
    assert all(float(row["rate_per_1000"]) > 0 for row in rows)


def test_observed_mover_composition_does_not_create_western_protestant_inflows():
    western_lgds = {
        "derry_strabane",
        "fermanagh_omagh",
        "mid_ulster",
        "newry_mourne_down",
    }
    net_protestant = {location: 0 for location in western_lgds}
    with COMMUNITY_MIGRATION_PATH.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["religious_background"] != "protestant":
                continue
            count = int(row["count"])
            if row["destination"] in western_lgds:
                net_protestant[row["destination"]] += count
            if row["source"] in western_lgds:
                net_protestant[row["source"]] -= count

    assert all(change < 0 for change in net_protestant.values())


def test_current_model_filters_each_internal_flow_by_background():
    model = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))
    rules = model["internal_migration_rates"]

    assert all("religious_background" in rule["filters"] for rule in rules)
    assert all(
        rule["evidence"] == "census_2021_origin_destination_by_religion"
        for rule in rules
    )


def test_lgd_population_source_matches_census_total_and_codes():
    with Path("data/ni_census_2021_lgd_population.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 11
    assert sum(int(row["count"]) for row in rows) == 1_903_175
    assert {row["code"] for row in rows} == {
        f"N090000{index:02d}" for index in range(1, 12)
    }
