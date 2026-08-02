from pathlib import Path

import yaml

from src.ni_model.simulation.historical_configuration import (
    configure_historical_model_from_file,
)


def test_historical_configuration_contains_causal_inputs_not_checkpoint_targets():
    path = Path("models/ni_base_2024.yaml")
    raw_config = yaml.safe_load(path.read_text())
    config = configure_historical_model_from_file(raw_config, path)
    result_path = path.parent / raw_config["historical_calibration"]["parameter_file"]
    calibration_result = yaml.safe_load(result_path.resolve().read_text())

    assert len(config["child_background_rules"]) == 10
    assert len(config["integration_rates"]) == 2
    assert config["annual_demographic_components"][2001]["births"] == 21_460
    assert "community_calibration_targets" not in config
    assert "historical_benchmarks" not in config
    assert all("target" not in rule for rule in config["integration_rates"])
    assert raw_config["historical_calibration"]["accepted_candidates"] == (
        calibration_result["method"]["accepted_candidates"]
    )
