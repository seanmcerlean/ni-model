import math

import pytest

from src.ni_model.validation.historical_validator import (
    HistoricalValidator,
    ValidationResult,
)

BENCHMARKS = {
    2001: {
        "total_population": 1_000_000,
        "religious_breakdown": {
            "catholic": 400_000,
            "protestant": 450_000,
            "other": 100_000,
            "none": 50_000,
        },
    },
    2011: {
        "total_population": 1_100_000,
        "religious_breakdown": {
            "catholic": 450_000,
            "protestant": 440_000,
            "other": 130_000,
            "none": 80_000,
        },
    },
}

PERFECT_SNAPSHOT = {
    "total_population": 1_000_000,
    "religious_breakdown": {
        "catholic": 400_000,
        "protestant": 450_000,
        "other": 100_000,
        "none": 50_000,
    },
}

CLOSE_SNAPSHOT = {
    "total_population": 1_050_000,   # 5% over
    "religious_breakdown": {
        "catholic": 420_000,         # 5% over
        "protestant": 472_500,       # 5% over
        "other": 105_000,            # 5% over
        "none": 52_500,              # 5% over
    },
}

FAR_SNAPSHOT = {
    "total_population": 1_300_000,   # 30% over
    "religious_breakdown": {
        "catholic": 600_000,         # 50% over
        "protestant": 400_000,       # 11% under
        "other": 200_000,            # 100% over
        "none": 100_000,             # 100% over
    },
}


@pytest.fixture
def validator():
    return HistoricalValidator(BENCHMARKS)


def test_available_years(validator):
    assert validator.available_years() == [2001, 2011]


def test_validate_returns_none_for_unknown_year(validator):
    assert validator.validate(1999, PERFECT_SNAPSHOT) is None


def test_validate_perfect_match_zero_errors(validator):
    result = validator.validate(2001, PERFECT_SNAPSHOT)
    assert result.total_population_error.absolute_error == 0
    assert result.total_population_error.relative_error == 0.0
    assert result.rmse == 0.0
    assert result.mean_absolute_relative_error == 0.0


def test_validate_perfect_match_accuracy_one(validator):
    result = validator.validate(2001, PERFECT_SNAPSHOT)
    assert result.accuracy_score == 1.0


def test_validate_perfect_match_within_threshold(validator):
    result = validator.validate(2001, PERFECT_SNAPSHOT)
    assert result.within_threshold is True


def test_validate_close_snapshot_within_threshold(validator):
    result = validator.validate(2001, CLOSE_SNAPSHOT)
    assert result.within_threshold is True
    assert result.mean_absolute_relative_error == pytest.approx(0.05, abs=0.01)


def test_validate_far_snapshot_outside_threshold(validator):
    result = validator.validate(2001, FAR_SNAPSHOT)
    assert result.within_threshold is False
    assert result.mean_absolute_relative_error > 0.10


def test_validate_returns_validation_result(validator):
    result = validator.validate(2001, PERFECT_SNAPSHOT)
    assert isinstance(result, ValidationResult)
    assert result.year == 2001


def test_validate_religious_breakdown_errors_count(validator):
    result = validator.validate(2001, PERFECT_SNAPSHOT)
    assert len(result.religious_breakdown_errors) == 4


def test_validate_rmse_positive_for_imperfect(validator):
    result = validator.validate(2001, CLOSE_SNAPSHOT)
    assert result.rmse > 0


def test_validate_rmse_formula(validator):
    result = validator.validate(2001, CLOSE_SNAPSHOT)
    errors = [result.total_population_error.absolute_error] + [
        e.absolute_error for e in result.religious_breakdown_errors
    ]
    expected = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
    assert result.rmse == pytest.approx(expected, rel=0.01)


def test_accuracy_score_clamped_to_zero(validator):
    result = validator.validate(2001, FAR_SNAPSHOT)
    assert result.accuracy_score >= 0.0


def test_validate_all_returns_matching_years(validator):
    snapshots = {
        2001: PERFECT_SNAPSHOT,
        2011: CLOSE_SNAPSHOT,
        2025: PERFECT_SNAPSHOT,  # no benchmark — should be excluded
    }
    results = validator.validate_all(snapshots)
    assert set(results.keys()) == {2001, 2011}


def test_validate_all_empty_snapshots(validator):
    assert validator.validate_all({}) == {}


def test_summary_empty(validator):
    s = validator.summary({})
    assert s["years_validated"] == 0
    assert s["mean_accuracy"] == 0.0
    assert s["all_within_threshold"] is False


def test_summary_all_perfect(validator):
    results = validator.validate_all({2001: PERFECT_SNAPSHOT, 2011: {
        "total_population": 1_100_000,
        "religious_breakdown": {"catholic": 450_000, "protestant": 440_000,
                                "other": 130_000, "none": 80_000},
    }})
    s = validator.summary(results)
    assert s["years_validated"] == 2
    assert s["mean_accuracy"] == pytest.approx(1.0)
    assert s["all_within_threshold"] is True


def test_summary_per_year_keys(validator):
    results = validator.validate_all({2001: PERFECT_SNAPSHOT})
    s = validator.summary(results)
    assert 2001 in s["per_year"]
    assert "accuracy_score" in s["per_year"][2001]
    assert "mare" in s["per_year"][2001]
    assert "within_threshold" in s["per_year"][2001]


def test_custom_threshold_strict(validator):
    strict = HistoricalValidator(BENCHMARKS, threshold=0.01)
    result = strict.validate(2001, CLOSE_SNAPSHOT)
    assert result.within_threshold is False


def test_custom_threshold_lenient():
    lenient = HistoricalValidator(BENCHMARKS, threshold=0.99)
    result = lenient.validate(2001, FAR_SNAPSHOT)
    assert result.within_threshold is True


def test_from_yaml_loads_benchmarks():
    validator = HistoricalValidator.from_yaml("data/historical_benchmarks.yaml")
    assert 2021 in validator.available_years()
    assert 1971 in validator.available_years()
    assert len(validator.available_years()) == 6


def test_from_yaml_benchmark_values():
    validator = HistoricalValidator.from_yaml("data/historical_benchmarks.yaml")
    b = validator.benchmarks[2021]
    assert b["total_population"] == 1_903_175
    assert b["religious_breakdown"]["catholic"] == 864_249


def test_missing_religious_key_treated_as_zero(validator):
    snap = {"total_population": 1_000_000, "religious_breakdown": {"catholic": 400_000}}
    result = validator.validate(2001, snap)
    protestant_err = next(
        e for e in result.religious_breakdown_errors if e.key == "protestant"
    )
    assert protestant_err.predicted == 0
    assert protestant_err.absolute_error == 450_000
