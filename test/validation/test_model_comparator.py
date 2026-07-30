import pytest

from src.ni_model.validation.model_comparator import (
    ComparisonReport,
    ModelComparator,
    YearComparison,
)


def _snap(total, catholic, protestant, other=0, none=0):
    return {
        "total_population": total,
        "religious_breakdown": {
            "catholic": catholic,
            "protestant": protestant,
            "other": other,
            "none": none,
        },
    }


SNAP_A = _snap(1_000_000, 400_000, 450_000, 100_000, 50_000)
SNAP_B = _snap(1_050_000, 420_000, 472_500, 105_000, 52_500)  # 5% higher across board
SNAP_C = _snap(1_300_000, 600_000, 400_000, 200_000, 100_000)  # large divergence

SNAPS_A = {2001: SNAP_A, 2011: SNAP_A}
SNAPS_B = {2001: SNAP_B, 2011: SNAP_B}
SNAPS_C = {2001: SNAP_C, 2011: SNAP_C}


@pytest.fixture
def comparator():
    return ModelComparator("Model A", "Model B")


def test_compare_returns_report(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert isinstance(report, ComparisonReport)


def test_compare_years_compared(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert report.years_compared == [2001, 2011]


def test_compare_only_common_years(comparator):
    a = {2001: SNAP_A, 2010: SNAP_A}
    b = {2001: SNAP_B, 2015: SNAP_B}
    report = comparator.compare(a, b)
    assert report.years_compared == [2001]


def test_compare_no_common_years(comparator):
    report = comparator.compare({2001: SNAP_A}, {2011: SNAP_B})
    assert report.years_compared == []
    assert report.mean_rmse == 0.0
    assert report.mean_divergence == 0.0


def test_compare_identical_snapshots_zero_divergence(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_A)
    assert report.mean_divergence == 0.0
    assert report.mean_rmse == 0.0


def test_compare_5pct_difference(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert report.mean_divergence == pytest.approx(0.05, abs=0.01)


def test_compare_model_names(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert report.model_a_name == "Model A"
    assert report.model_b_name == "Model B"


def test_per_year_returns_year_comparison(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert isinstance(report.per_year[2001], YearComparison)


def test_per_year_diffs_count(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert len(report.per_year[2001].diffs) == 5  # total_pop + 4 religion keys


def test_per_year_rmse_positive_for_different(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert report.per_year[2001].rmse > 0


def test_per_year_max_divergence_key_present(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_C)
    assert report.per_year[2001].max_divergence_key in [
        "total_population",
        "catholic",
        "protestant",
        "other",
        "none",
    ]


def test_most_divergent_year(comparator):
    a = {2001: SNAP_A, 2011: SNAP_A}
    b = {2001: SNAP_B, 2011: SNAP_C}  # 2011 has larger divergence
    report = comparator.compare(a, b)
    assert comparator.most_divergent_year(report) == 2011


def test_most_divergent_year_empty(comparator):
    report = comparator.compare({}, {})
    assert comparator.most_divergent_year(report) is None


def test_most_divergent_metric(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_C)
    metric = comparator.most_divergent_metric(report)
    assert metric in ["total_population", "catholic", "protestant", "other", "none"]


def test_most_divergent_metric_empty(comparator):
    report = comparator.compare({}, {})
    assert comparator.most_divergent_metric(report) is None


def test_summary_equivalent(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_A)
    assert "equivalent" in report.summary.lower()


def test_summary_minor(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    assert "minor" in report.summary.lower()


def test_summary_significant():
    comparator = ModelComparator()
    a = {2001: _snap(1_000_000, 400_000, 450_000)}
    b = {2001: _snap(2_000_000, 900_000, 900_000)}  # ~100% diff
    report = comparator.compare(a, b)
    assert "significant" in report.summary.lower()


def test_relative_diff_signed(comparator):
    report = comparator.compare(SNAPS_A, SNAPS_B)
    total_diff = next(
        d for d in report.per_year[2001].diffs if d.key == "total_population"
    )
    assert total_diff.relative_diff > 0  # B is larger than A


def test_relative_diff_negative_when_b_smaller(comparator):
    report = comparator.compare(SNAPS_B, SNAPS_A)  # reversed
    total_diff = next(
        d for d in report.per_year[2001].diffs if d.key == "total_population"
    )
    assert total_diff.relative_diff < 0


def test_default_model_names():
    c = ModelComparator()
    assert c.model_a_name == "Model A"
    assert c.model_b_name == "Model B"
