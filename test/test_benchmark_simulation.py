import pytest

from scripts.benchmark_simulation import core_year_p95, enforce_budget


def report(seconds: float) -> dict:
    return {
        "stages": {
            stage: {"wall_p95_seconds": seconds / 4}
            for stage in (
                "births",
                "deaths",
                "external_migration",
                "internal_relocation",
            )
        }
    }


def test_core_year_p95_sums_component_percentiles():
    assert core_year_p95(report(0.2)) == pytest.approx(0.2)


def test_budget_gate_rejects_regression_and_unknown_size():
    enforce_budget(report(0.2), 25_000)
    with pytest.raises(RuntimeError, match="exceeds"):
        enforce_budget(report(0.3), 25_000)
    with pytest.raises(ValueError, match="no performance budget"):
        enforce_budget(report(0.2), 10_000)
