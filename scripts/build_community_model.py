"""Build a community-differentiated sensitivity model from ni_current.yaml.

The official NISRA projection supplies NI-wide components only. This variant
splits each component across community-background cohorts using documented,
conservative relative multipliers. Multipliers are normalized against Census
2021 shares so the starting-year weighted rate equals the official NI-wide
rate. They are scenario assumptions, not observed component estimates.
"""

from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "models" / "ni_current.yaml"
TARGET_PATH = ROOT / "models" / "ni_current_community.yaml"

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
        "PROTESTANT": 0.85,
        "OTHER": 1.15,
        "NONE": 1.25,
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
        }
        for group in SHARES
    ]


def build_model(source):
    model = deepcopy(source)
    model.update(
        {
            "name": "NI Current – community-differentiated estimate",
            "description": (
                "NISRA 2024 principal totals split by community background using "
                "conservative estimated differentials calibrated to Census "
                "2011–2021 change. Annual component rates are normalized to the "
                "official starting total. Estimated two-way community-identification "
                "transitions are included. This sensitivity scenario is not an "
                "official projection."
            ),
            "projection_version": (
                "Estimated community differential over NISRA/ONS 2024 principal"
            ),
            "default_start_year": 2024,
            "default_end_year": 2050,
        }
    )
    for section in ("birth_rates", "death_rates"):
        model[section] = [
            split
            for rule in source[section]
            for split in _split_rule(rule, MULTIPLIERS[section])
        ]
    model["migration_rates"] = [
        split
        for rule in source["migration_rates"]
        for split in _split_rule(
            rule,
            MULTIPLIERS["migration_out" if rule["rate"] < 0 else "migration_in"],
        )
    ]
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
