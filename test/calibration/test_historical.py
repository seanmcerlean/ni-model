from src.ni_model.calibration.historical import (
    HistoricalCalibration,
    HistoricalParameters,
)


def test_calibration_keeps_holdout_separate_and_is_reproducible():
    parameters = HistoricalParameters(
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
    calibration = HistoricalCalibration(sample_size=500, seed=7)

    first = calibration.evaluate(parameters)
    second = calibration.evaluate(parameters)
    different_seed = calibration.evaluate(parameters, seed=8)

    assert first == second
    assert first["snapshots"] != different_seed["snapshots"]
    assert set(first["snapshots"]) == {2001, 2011, 2021}
    assert first["fit_score"] != first["holdout_score"]


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
