from pathlib import Path

import yaml


def test_historical_components_preserve_the_population_accounting_identity():
    data = yaml.safe_load(
        Path("data/historical_demographic_components.yaml").read_text()
    )
    annual = {int(year): values for year, values in data["annual"].items()}

    for year in range(1969, 2021):
        current = annual[year]
        calculated_next = (
            current["population"]
            + current["births"]
            - current["deaths"]
            + current["population_adjustment"]
        )
        assert calculated_next == annual[year + 1]["population"]


def test_pre_2001_adjustments_are_never_labelled_as_observed_migration():
    data = yaml.safe_load(
        Path("data/historical_demographic_components.yaml").read_text()
    )

    assert all(
        values["adjustment_status"] == "estimated_residual"
        for year, values in data["annual"].items()
        if int(year) < 2001
    )
