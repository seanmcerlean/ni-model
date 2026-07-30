import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class MetricDiff:
    key: str
    model_a: float
    model_b: float
    absolute_diff: float
    relative_diff: float  # (b - a) / a, signed


@dataclass
class YearComparison:
    year: int
    diffs: List[MetricDiff]
    rmse: float  # root mean square of absolute diffs across metrics
    max_divergence_key: str
    max_divergence: float  # largest absolute relative diff


@dataclass
class ComparisonReport:
    model_a_name: str
    model_b_name: str
    years_compared: List[int]
    per_year: Dict[int, YearComparison]
    mean_rmse: float
    mean_divergence: float
    summary: str


class ModelComparator:
    """Compares two sets of simulation snapshots across demographic metrics."""

    SNAPSHOT_KEYS = [
        "total_population",
        "catholic",
        "protestant",
        "other",
        "none",
    ]

    def __init__(self, model_a_name: str = "Model A", model_b_name: str = "Model B"):
        self.model_a_name = model_a_name
        self.model_b_name = model_b_name

    def compare(
        self,
        snapshots_a: Dict[int, Dict[str, Any]],
        snapshots_b: Dict[int, Dict[str, Any]],
    ) -> ComparisonReport:
        """Compare two snapshot dicts keyed by year.
        Only years present in both are compared."""
        common_years = sorted(set(snapshots_a) & set(snapshots_b))
        per_year = {
            year: self._compare_year(year, snapshots_a[year], snapshots_b[year])
            for year in common_years
        }

        mean_rmse = (
            sum(c.rmse for c in per_year.values()) / len(per_year)
            if per_year else 0.0
        )
        mean_div = (
            sum(c.max_divergence for c in per_year.values()) / len(per_year)
            if per_year else 0.0
        )

        return ComparisonReport(
            model_a_name=self.model_a_name,
            model_b_name=self.model_b_name,
            years_compared=common_years,
            per_year=per_year,
            mean_rmse=round(mean_rmse, 2),
            mean_divergence=round(mean_div, 4),
            summary=self._summary_text(mean_div),
        )

    def most_divergent_year(self, report: ComparisonReport) -> Optional[int]:
        """Return the year with the highest max_divergence, or None if no years."""
        if not report.per_year:
            return None
        return max(report.per_year, key=lambda y: report.per_year[y].max_divergence)

    def most_divergent_metric(self, report: ComparisonReport) -> Optional[str]:
        """Return the metric key with the highest mean absolute
        relative diff across years."""
        if not report.per_year:
            return None
        totals: Dict[str, float] = {}
        for yc in report.per_year.values():
            for d in yc.diffs:
                totals[d.key] = totals.get(d.key, 0.0) + abs(d.relative_diff)
        return max(totals, key=lambda k: totals[k])

    def _compare_year(
        self, year: int, snap_a: Dict[str, Any], snap_b: Dict[str, Any]
    ) -> YearComparison:
        diffs = []
        for key in self.SNAPSHOT_KEYS:
            val_a = self._extract(snap_a, key)
            val_b = self._extract(snap_b, key)
            abs_diff = abs(val_b - val_a)
            rel_diff = (val_b - val_a) / val_a if val_a != 0 else 0.0
            diffs.append(MetricDiff(
                key=key,
                model_a=val_a,
                model_b=val_b,
                absolute_diff=abs_diff,
                relative_diff=round(rel_diff, 4),
            ))

        rmse = math.sqrt(sum(d.absolute_diff ** 2 for d in diffs) / len(diffs))
        max_diff = max(diffs, key=lambda d: abs(d.relative_diff))

        return YearComparison(
            year=year,
            diffs=diffs,
            rmse=round(rmse, 2),
            max_divergence_key=max_diff.key,
            max_divergence=round(abs(max_diff.relative_diff), 4),
        )

    @staticmethod
    def _extract(snapshot: Dict[str, Any], key: str) -> float:
        if key == "total_population":
            return float(snapshot.get("total_population", 0))
        return float(snapshot.get("religious_breakdown", {}).get(key, 0))

    @staticmethod
    def _summary_text(mean_divergence: float) -> str:
        if mean_divergence < 0.02:
            return "Models are essentially equivalent (<2% mean divergence)"
        if mean_divergence < 0.10:
            return "Models show minor differences (2–10% mean divergence)"
        if mean_divergence < 0.25:
            return "Models show moderate differences (10–25% mean divergence)"
        return "Models show significant differences (>25% mean divergence)"
