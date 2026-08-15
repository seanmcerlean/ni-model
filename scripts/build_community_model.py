"""Build a community-differentiated sensitivity model from ni_current.yaml.

The official NISRA projection supplies NI-wide components only. This variant
splits each component across community-background cohorts using documented,
conservative relative multipliers. Multipliers are normalized against Census
2021 shares so the starting-year weighted rate equals the official NI-wide
rate. They are scenario assumptions, not observed component estimates.
"""

import csv
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "models" / "ni_current.yaml"
TARGET_PATH = ROOT / "models" / "ni_current_community.yaml"
ARRIVAL_PROFILE_PATH = ROOT / "data" / "ni_external_arrivals_lgd_2021_by_religion.csv"

# ODMG20 reports current religion, while the model field represents the Census
# "religion or religion brought up in" measure. The allocations below are the
# published national differences between MS-B21 and MS-B23, normalized over
# their 361,496 total. The 16-person discrepancy from the MS-B21 pool is Census
# disclosure-control noise.
CURRENT_NONE_TO_BACKGROUND = {
    "CATHOLIC": 64_602 / 361_496,
    "PROTESTANT": 116_544 / 361_496,
    "OTHER": 2_990 / 361_496,
    "NONE": 177_360 / 361_496,
}

SHARES = {
    "CATHOLIC": 869_753 / 1_903_172,
    "PROTESTANT": 827_545 / 1_903_172,
    "OTHER": 28_514 / 1_903_172,
    "NONE": 177_360 / 1_903_172,
}

# Conservative directions calibrated to the 2011-2021 Census change: Catholic
# +6%, Protestant -6%, Other +72%, None +75%. Census change cannot identify
# births, deaths, migration and background switching separately.
MULTIPLIERS = {
    "birth_rates": {
        "CATHOLIC": 1.08,
        "PROTESTANT": 0.90,
        "OTHER": 1.05,
        "NONE": 1.10,
    },
    "death_rates": {
        "CATHOLIC": 0.92,
        "PROTESTANT": 1.12,
        "OTHER": 0.80,
        "NONE": 0.72,
    },
    "migration_in": {
        "CATHOLIC": 0.75,
        "PROTESTANT": 0.60,
        "OTHER": 2.40,
        "NONE": 1.80,
    },
    "migration_out": {
        "CATHOLIC": 1.00,
        "PROTESTANT": 1.00,
        "OTHER": 1.00,
        "NONE": 1.00,
    },
}


def _split_rule(rule, multipliers):
    denominator = sum(SHARES[group] * value for group, value in multipliers.items())
    return [
        {
            **deepcopy(rule),
            "rate": round(rule["rate"] * multipliers[group] / denominator, 6),
            "filters": {**rule.get("filters", {}), "religious_background": group},
            "evidence": "estimated_community_differential",
            "source_evidence": rule.get("evidence"),
        }
        for group in SHARES
    ]


def _arrival_profiles(rows):
    profiles = []
    for row in rows:
        profile = {
            "origin": row["origin"].upper(),
            "location": row["destination"].upper(),
        }
        background = row["religious_background"].upper()
        if background != "NONE":
            profiles.append(
                {
                    **profile,
                    "religious_background": background,
                    "weight": int(row["count"]),
                }
            )
            continue
        profiles.extend(
            {
                **profile,
                "religious_background": destination,
                "weight": int(row["count"]) * proportion,
            }
            for destination, proportion in CURRENT_NONE_TO_BACKGROUND.items()
        )
    return profiles


def build_model(source):
    model = deepcopy(source)
    model.update(
        {
            "name": "NI Current – community-differentiated estimate",
            "description": (
                "NISRA 2024 principal totals split by community background using "
                "conservative estimated differentials calibrated to Census "
                "2011–2021 change. External arrivals follow the Census 2021 joint "
                "origin, destination-LGD and current-religion profile; emigration "
                "rates are evidence-neutral because no equivalent departure "
                "breakdown is published. Current-religion arrivals are converted "
                "to the community-background measure using the national Census "
                "2021 relationship. Annual component rates are "
                "normalized to the official starting total. Estimated two-way "
                "community-identification transitions are included. Census-derived "
                "internal routes are balanced toward NISRA's 2022-based LGD population "
                "trajectory without targeting community shares. This sensitivity "
                "scenario is not an official projection."
            ),
            "projection_version": (
                "Estimated community differential over NISRA/ONS 2024 principal"
            ),
            "default_start_year": 2021,
            "default_end_year": 2075,
        }
    )
    for section in ("birth_rates", "death_rates"):
        model[section] = [
            split
            for rule in source[section]
            for split in _split_rule(rule, MULTIPLIERS[section])
        ]
    model["migration_rates"] = []
    for rule in source["migration_rates"]:
        if rule["rate"] >= 0:
            model["migration_rates"].append(
                {
                    **deepcopy(rule),
                    "evidence": "census_2021_arrival_profile_scaled_to_annual_total",
                    "source_evidence": rule.get("evidence"),
                }
            )
        else:
            model["migration_rates"].extend(
                _split_rule(rule, MULTIPLIERS["migration_out"])
            )
    if ARRIVAL_PROFILE_PATH.exists():
        with ARRIVAL_PROFILE_PATH.open(encoding="utf-8", newline="") as source_file:
            model["immigration_profiles"] = _arrival_profiles(
                csv.DictReader(source_file)
            )
    return model


def main():
    with SOURCE_PATH.open(encoding="utf-8") as source_file:
        source = yaml.safe_load(source_file)
    with TARGET_PATH.open("w", encoding="utf-8") as target_file:
        yaml.safe_dump(
            build_model(source),
            target_file,
            sort_keys=False,
            allow_unicode=True,
            width=88,
        )


if __name__ == "__main__":
    main()
