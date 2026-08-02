"""Build the causal historical model from auditable calibration inputs."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

MODERN_CHILD_BACKGROUND_RULES = [
    {
        "year_min": 2011,
        "year_max": 9999,
        "source": "CATHOLIC",
        "probabilities": {
            "CATHOLIC": 0.87869,
            "PROTESTANT": 0.03076,
            "OTHER": 0.00182,
            "NONE": 0.08873,
        },
    },
    {
        "year_min": 2011,
        "year_max": 9999,
        "source": "PROTESTANT",
        "probabilities": {
            "CATHOLIC": 0.05421,
            "PROTESTANT": 0.75799,
            "OTHER": 0.00309,
            "NONE": 0.18471,
        },
    },
    {
        "year_min": 2011,
        "year_max": 9999,
        "source": "OTHER",
        "probabilities": {
            "CATHOLIC": 0.07504,
            "PROTESTANT": 0.06600,
            "OTHER": 0.64523,
            "NONE": 0.21373,
        },
    },
    {
        "year_min": 2011,
        "year_max": 9999,
        "source": "NONE",
        "probabilities": {
            "CATHOLIC": 0.08447,
            "PROTESTANT": 0.07440,
            "OTHER": 0.00481,
            "NONE": 0.83632,
        },
    },
]


def configure_historical_model(
    base_config: dict[str, Any],
    parameters: dict[str, float],
    components: dict[str, Any],
) -> dict[str, Any]:
    """Apply causal parameters and annual controls without checkpoint outputs."""
    config = copy.deepcopy(base_config)
    config["integration_rates"] = [
        _adult_none_rule("PROTESTANT", parameters["protestant_adult_none"]),
        _adult_none_rule("CATHOLIC", parameters["catholic_adult_none"]),
    ]
    for rule in config["birth_rates"]:
        background = rule.get("filters", {}).get("religious_background")
        if rule.get("year_min", 0) < 1995:
            if background == "CATHOLIC":
                rule["rate"] *= parameters["early_catholic_birth"]
            elif background == "PROTESTANT":
                rule["rate"] *= parameters["early_protestant_birth"]
    config["death_rates"] = _split_rules(
        config["death_rates"],
        {
            "CATHOLIC": parameters["catholic_mortality"],
            "PROTESTANT": parameters["protestant_mortality"],
            "OTHER": 1.0,
            "NONE": 1.0,
        },
    )
    config["migration_rates"] = _split_rules(
        config["migration_rates"],
        {
            "CATHOLIC": parameters["catholic_migration"],
            "PROTESTANT": parameters["protestant_migration"],
            "OTHER": parameters["other_migration"],
            "NONE": parameters["none_migration"],
        },
    )
    config["child_background_rules"] = _historical_child_rules(parameters)
    config["annual_demographic_components"] = components["annual"]
    config["component_baseline_population"] = components["baseline_population"]
    return config


def configure_historical_model_from_file(
    config: dict[str, Any], model_path: str | Path
) -> dict[str, Any]:
    calibration = config.get("historical_calibration")
    if not calibration:
        return config
    model_directory = Path(model_path).parent
    component_path = model_directory / calibration["component_file"]
    with component_path.resolve().open(encoding="utf-8") as source:
        components = yaml.safe_load(source)
    parameters = calibration.get("parameters")
    if parameters is None:
        parameter_path = model_directory / calibration["parameter_file"]
        with parameter_path.resolve().open(encoding="utf-8") as source:
            parameters = yaml.safe_load(source)["parameters"]
    return configure_historical_model(config, parameters, components)


def _adult_none_rule(source: str, rate: float) -> dict[str, Any]:
    return {
        "rate": rate,
        "year_min": 2001,
        "destination": "NONE",
        "filters": {
            "religious_background": source,
            "age_min": 18,
            "age_max": 44,
        },
        "evidence": "calibrated_response_category_transition",
    }


def _historical_child_rules(parameters: dict[str, float]) -> list[dict[str, Any]]:
    protestant = parameters["protestant_child_none_1981"]
    catholic = parameters["catholic_child_none_1981"]
    return [
        _child_none_rule(1969, 1980, "PROTESTANT", protestant * 0.5),
        _child_none_rule(1969, 1980, "CATHOLIC", catholic * 0.5),
        _child_none_rule(1981, 2000, "PROTESTANT", protestant),
        _child_none_rule(1981, 2000, "CATHOLIC", catholic),
        _child_none_rule(2001, 2010, "PROTESTANT", min(protestant * 1.5, 0.185)),
        _child_none_rule(2001, 2010, "CATHOLIC", min(catholic * 1.5, 0.089)),
        *copy.deepcopy(MODERN_CHILD_BACKGROUND_RULES),
    ]


def _child_none_rule(
    year_min: int, year_max: int, source: str, none: float
) -> dict[str, Any]:
    return {
        "year_min": year_min,
        "year_max": year_max,
        "source": source,
        "probabilities": {source: 1 - none, "NONE": none},
    }


def _split_rules(
    rules: list[dict[str, Any]], multipliers: dict[str, float]
) -> list[dict[str, Any]]:
    expanded = []
    for rule in rules:
        existing = rule.get("filters", {}).get("religious_background")
        if existing:
            adjusted = copy.deepcopy(rule)
            adjusted["rate"] *= multipliers[existing]
            expanded.append(adjusted)
            continue
        for background, multiplier in multipliers.items():
            adjusted = copy.deepcopy(rule)
            adjusted["rate"] *= multiplier
            adjusted["filters"] = {
                **adjusted.get("filters", {}),
                "religious_background": background,
            }
            expanded.append(adjusted)
    return expanded
