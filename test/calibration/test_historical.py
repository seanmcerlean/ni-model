import copy

from src.ni_model.calibration.historical import (
    HistoricalCalibration,
    HistoricalParameters,
)

PARAMETERS = HistoricalParameters(
    baseline_catholic=0.34,
    baseline_none=0.015,
    baseline_other=0.006,
    early_catholic_birth=1.05,
    early_protestant_birth=0.8,
    protestant_mortality=1.05,
    catholic_mortality=0.95,
    protestant_migration=1.0,
    catholic_migration=1.0,
    other_migration=1.0,
    none_migration=1.0,
    protestant_adult_none=2.0,
    catholic_adult_none=1.0,
    protestant_child_none_1981=0.10,
    catholic_child_none_1981=0.04,
)


def test_calibration_keeps_holdout_separate_and_is_reproducible():
    calibration = HistoricalCalibration(sample_size=500, seed=7)

    first = calibration.evaluate(PARAMETERS)
    second = calibration.evaluate(PARAMETERS)
    different_seed = calibration.evaluate(PARAMETERS, seed=8)

    assert first == second
    assert first["snapshots"] != different_seed["snapshots"]
    assert set(first["snapshots"]) == {2001, 2011, 2021}
    assert first["fit_score"] != first["holdout_score"]


def test_benchmarks_score_outputs_but_cannot_change_simulation_trajectory():
    calibration = HistoricalCalibration(sample_size=500, seed=7)
    original = calibration.evaluate(PARAMETERS)
    altered_benchmarks = copy.deepcopy(calibration.benchmarks)
    altered_benchmarks[2001]["total_population"] *= 2
    altered_benchmarks[2001]["religious_breakdown"]["catholic"] = 0
    calibration.benchmarks = altered_benchmarks

    rescored = calibration.evaluate(PARAMETERS)

    assert rescored["snapshots"] == original["snapshots"]
    assert rescored["fit_score"] != original["fit_score"]


def test_search_never_selects_on_holdout_score(monkeypatch):
    calibration = HistoricalCalibration(sample_size=10, seed=7)
    results = iter(
        [
            {
                "fit_score": 0.2,
                "holdout_score": 0.01,
                "checkpoint_errors": {
                    2001: {"within_tolerance": False},
                    2011: {"within_tolerance": False},
                },
            },
            {
                "fit_score": 0.1,
                "holdout_score": 0.9,
                "checkpoint_errors": {
                    2001: {"within_tolerance": False},
                    2011: {"within_tolerance": False},
                },
            },
        ]
    )
    monkeypatch.setattr(
        calibration,
        "evaluate_ensemble",
        lambda _parameters, _replicates: next(results),
    )

    result = calibration.search(2)

    assert result["fit_score"] == 0.1
    assert result["holdout_score"] == 0.9
    assert result["selection"] == "lowest_mean_fit_error_no_candidate_in_tolerance"


def test_accepted_search_selects_central_parameters_not_best_holdout(monkeypatch):
    calibration = HistoricalCalibration(sample_size=10, seed=7)
    central = {
        name: center
        for name, (center, _span) in {
            "baseline_catholic": (0.325, 0.025),
            "baseline_none": (0.015, 0.010),
            "baseline_other": (0.007, 0.005),
            "early_catholic_birth": (1.20, 0.25),
            "early_protestant_birth": (0.875, 0.175),
            "protestant_mortality": (1.125, 0.175),
            "catholic_mortality": (0.95, 0.15),
            "protestant_migration": (1.075, 0.275),
            "catholic_migration": (0.95, 0.25),
            "other_migration": (2.25, 1.75),
            "none_migration": (1.75, 1.25),
            "protestant_adult_none": (3.25, 2.75),
            "catholic_adult_none": (2.125, 1.875),
            "protestant_child_none_1981": (0.09, 0.05),
            "catholic_child_none_1981": (0.035, 0.025),
        }.items()
    }
    edge = {**central, "baseline_catholic": 0.35}
    results = iter(
        [
            {
                "parameters": edge,
                "fit_score": 0.01,
                "holdout_score": 0.001,
                "checkpoint_errors": {
                    2001: {"within_tolerance": True},
                    2011: {"within_tolerance": True},
                },
            },
            {
                "parameters": central,
                "fit_score": 0.02,
                "holdout_score": 0.9,
                "checkpoint_errors": {
                    2001: {"within_tolerance": True},
                    2011: {"within_tolerance": True},
                },
            },
        ]
    )
    monkeypatch.setattr(
        calibration,
        "evaluate_ensemble",
        lambda _parameters, _replicates: next(results),
    )

    result = calibration.search(2)

    assert result["parameters"] == central
    assert result["holdout_score"] == 0.9
    assert result["selection"] == "central_parameter_set_within_fit_tolerance"
