import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class MetricError:
    key: str
    actual: float
    predicted: float
    absolute_error: float
    relative_error: float  # as fraction, e.g. 0.05 = 5%


@dataclass
class ValidationResult:
    year: int
    total_population_error: MetricError
    religious_breakdown_errors: List[MetricError]
    rmse: float
    mean_absolute_relative_error: float  # MARE across all metrics
    within_threshold: bool  # True if MARE <= threshold
    notes: str = ""

    @property
    def accuracy_score(self) -> float:
        """1.0 - MARE, clamped to [0, 1]"""
        return max(0.0, min(1.0, 1.0 - self.mean_absolute_relative_error))


class HistoricalValidator:
    """Compares simulation snapshots against historical census benchmarks."""

    DEFAULT_THRESHOLD = 0.10  # 10% MARE considered acceptable

    def __init__(
        self,
        benchmarks: Dict[int, Dict[str, Any]],
        threshold: float = DEFAULT_THRESHOLD,
    ):
        self.benchmarks = benchmarks
        self.threshold = threshold

    @classmethod
    def from_yaml(
        cls, path: str, threshold: float = DEFAULT_THRESHOLD
    ) -> "HistoricalValidator":
        with open(path) as f:
            data = yaml.safe_load(f)
        benchmarks = {int(year): vals for year, vals in data["benchmarks"].items()}
        return cls(benchmarks, threshold)

    def available_years(self) -> List[int]:
        return sorted(self.benchmarks.keys())

    def validate(
        self, year: int, snapshot: Dict[str, Any]
    ) -> Optional[ValidationResult]:
        """Validate a simulation snapshot against the benchmark for the given year.

        snapshot must contain:
          - total_population: int
          - religious_breakdown: Dict[str, int]  (keys: catholic, protestant,
            other, none)
        """
        benchmark = self.benchmarks.get(year)
        if benchmark is None:
            return None

        pop_error = self._metric_error(
            "total_population",
            benchmark["total_population"],
            snapshot["total_population"],
        )

        rb_errors = []
        b_rb = benchmark.get("religious_breakdown", {})
        s_rb = snapshot.get("religious_breakdown", {})
        for key in b_rb:
            rb_errors.append(self._metric_error(key, b_rb[key], s_rb.get(key, 0)))

        all_errors = [pop_error] + rb_errors
        rmse = self._rmse([e.absolute_error for e in all_errors])
        mare = sum(e.relative_error for e in all_errors) / len(all_errors)

        return ValidationResult(
            year=year,
            total_population_error=pop_error,
            religious_breakdown_errors=rb_errors,
            rmse=round(rmse, 2),
            mean_absolute_relative_error=round(mare, 4),
            within_threshold=mare <= self.threshold,
        )

    def validate_all(
        self, snapshots: Dict[int, Dict[str, Any]]
    ) -> Dict[int, ValidationResult]:
        """Validate all snapshots that have a matching benchmark year."""
        return {
            year: result
            for year, snap in snapshots.items()
            if (result := self.validate(year, snap)) is not None
        }

    def summary(self, results: Dict[int, ValidationResult]) -> Dict[str, Any]:
        """Aggregate summary across all validation results."""
        if not results:
            return {
                "years_validated": 0,
                "mean_accuracy": 0.0,
                "all_within_threshold": False,
            }
        scores = [r.accuracy_score for r in results.values()]
        return {
            "years_validated": len(results),
            "mean_accuracy": round(sum(scores) / len(scores), 4),
            "all_within_threshold": all(r.within_threshold for r in results.values()),
            "per_year": {
                year: {
                    "accuracy_score": r.accuracy_score,
                    "mare": r.mean_absolute_relative_error,
                    "within_threshold": r.within_threshold,
                }
                for year, r in sorted(results.items())
            },
        }

    @staticmethod
    def _metric_error(key: str, actual: float, predicted: float) -> MetricError:
        abs_err = abs(predicted - actual)
        rel_err = abs_err / actual if actual != 0 else 0.0
        return MetricError(
            key=key,
            actual=actual,
            predicted=predicted,
            absolute_error=abs_err,
            relative_error=rel_err,
        )

    @staticmethod
    def _rmse(errors: List[float]) -> float:
        if not errors:
            return 0.0
        return math.sqrt(sum(e**2 for e in errors) / len(errors))
