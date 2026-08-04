"""Causal historical calibration without checkpoint reconciliation."""

from __future__ import annotations

import random
import statistics
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from ..core.models import Origin, ReligiousBackground
from ..data.population_generator import calibrated_age_bands, iter_population
from ..simulation.columnar_worker import COLUMN_TYPES, ColumnarSimulationWorker
from ..simulation.historical_configuration import configure_historical_model

CALIBRATION_YEARS = (2001, 2011, 2021)
FIT_YEARS = (2001, 2011)
HOLDOUT_YEAR = 2021
_AGE_TOTAL = 1_536_065
_HISTORICAL_AGE_BANDS = calibrated_age_bands(
    [
        (0, 14, 456_997 / _AGE_TOTAL),
        (15, 39, 512_242 / _AGE_TOTAL),
        (40, 64, 400_842 / _AGE_TOTAL),
        (65, 110, 165_984 / _AGE_TOTAL),
    ]
)
_HISTORICAL_ORIGINS = [
    (Origin.NI, 0.94),
    (Origin.ROI, 0.025),
    (Origin.GB, 0.03),
    (Origin.OTHER, 0.005),
]


@dataclass(frozen=True)
class HistoricalParameters:
    """Bounded uncertain inputs, rather than fitted output overrides."""

    baseline_catholic: float
    baseline_none: float
    baseline_other: float
    early_catholic_birth: float
    early_protestant_birth: float
    protestant_mortality: float
    catholic_mortality: float
    protestant_migration: float
    catholic_migration: float
    other_migration: float
    none_migration: float
    protestant_adult_none: float
    catholic_adult_none: float
    protestant_child_none_1981: float
    catholic_child_none_1981: float

    @classmethod
    def sample(cls, rng: random.Random) -> "HistoricalParameters":
        return cls(
            baseline_catholic=rng.uniform(0.30, 0.35),
            baseline_none=rng.uniform(0.005, 0.025),
            baseline_other=rng.uniform(0.002, 0.012),
            early_catholic_birth=rng.uniform(0.95, 1.45),
            early_protestant_birth=rng.uniform(0.70, 1.05),
            protestant_mortality=rng.uniform(0.95, 1.30),
            catholic_mortality=rng.uniform(0.80, 1.10),
            protestant_migration=rng.uniform(0.80, 1.35),
            catholic_migration=rng.uniform(0.70, 1.20),
            other_migration=rng.uniform(0.50, 4.00),
            none_migration=rng.uniform(0.50, 3.00),
            protestant_adult_none=rng.uniform(0.50, 6.00),
            catholic_adult_none=rng.uniform(0.25, 4.00),
            protestant_child_none_1981=rng.uniform(0.04, 0.14),
            catholic_child_none_1981=rng.uniform(0.01, 0.06),
        )


class HistoricalCalibration:
    """Evaluate and search causal inputs against held-out Census checkpoints."""

    def __init__(
        self,
        model_path: str | Path = "models/ni_base_2024.yaml",
        benchmark_path: str | Path = "data/historical_benchmarks.yaml",
        component_path: str | Path = "data/historical_demographic_components.yaml",
        sample_size: int = 10_000,
        seed: int = 42,
    ):
        self.model_path = Path(model_path)
        self.sample_size = sample_size
        self.seed = seed
        with self.model_path.open(encoding="utf-8") as source:
            self.base_config = yaml.safe_load(source)
        with Path(benchmark_path).open(encoding="utf-8") as source:
            raw = yaml.safe_load(source)["benchmarks"]
        self.benchmarks = {int(year): values for year, values in raw.items()}
        with Path(component_path).open(encoding="utf-8") as source:
            components = yaml.safe_load(source)
        self.component_config = components
        self.component_baseline = components["baseline_population"]

    def evaluate(
        self, parameters: HistoricalParameters, seed: int | None = None
    ) -> dict[str, Any]:
        evaluation_seed = self.seed if seed is None else seed
        config = self._configured_model(parameters)
        population = self._population(parameters, evaluation_seed)
        worker = ColumnarSimulationWorker(
            population,
            config,
            uuid.UUID(int=evaluation_seed),
            seed=evaluation_seed,
        )
        snapshots = {}
        for year in range(1969, HOLDOUT_YEAR + 1):
            worker.run_year(year)
            if year in CALIBRATION_YEARS:
                snapshots[year] = self._snapshot(worker.population)
        fit_score = self._score(snapshots, FIT_YEARS)
        holdout_score = self._score(snapshots, (HOLDOUT_YEAR,))
        return {
            "parameters": asdict(parameters),
            "fit_score": fit_score,
            "holdout_score": holdout_score,
            "snapshots": snapshots,
            "checkpoint_errors": self._checkpoint_errors(snapshots),
        }

    def evaluate_ensemble(
        self, parameters: HistoricalParameters, replicates: int = 3
    ) -> dict[str, Any]:
        """Evaluate one causal parameter set across reproducible stochastic seeds."""
        results = [
            self.evaluate(parameters, seed=self.seed + replicate)
            for replicate in range(replicates)
        ]
        snapshots = {}
        for year in CALIBRATION_YEARS:
            snapshots[year] = {
                "total_population": statistics.mean(
                    result["snapshots"][year]["total_population"] for result in results
                ),
                "shares": {
                    background: statistics.mean(
                        result["snapshots"][year]["shares"][background]
                        for result in results
                    )
                    for background in ("catholic", "protestant", "other", "none")
                },
            }
        return {
            "parameters": asdict(parameters),
            "fit_score": self._score(snapshots, FIT_YEARS),
            "fit_score_sd": statistics.pstdev(
                result["fit_score"] for result in results
            ),
            "holdout_score": self._score(snapshots, (HOLDOUT_YEAR,)),
            "holdout_score_sd": statistics.pstdev(
                result["holdout_score"] for result in results
            ),
            "snapshots": snapshots,
            "checkpoint_errors": self._checkpoint_errors(snapshots),
            "replicate_seeds": [self.seed + index for index in range(replicates)],
        }

    def search(
        self, iterations: int, workers: int = 1, replicates: int = 3
    ) -> dict[str, Any]:
        rng = random.Random(self.seed)
        candidates = [HistoricalParameters.sample(rng) for _ in range(iterations)]
        if workers <= 1:
            results = [
                self.evaluate_ensemble(candidate, replicates)
                for candidate in candidates
            ]
        else:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                results = list(
                    executor.map(
                        self._evaluate_candidate,
                        [(candidate, replicates) for candidate in candidates],
                    )
                )
        accepted = [result for result in results if self._fit_within_tolerance(result)]
        if accepted:
            selected = min(
                accepted,
                key=lambda result: self._regularization(result["parameters"]),
            )
            selected["selection"] = "central_parameter_set_within_fit_tolerance"
        else:
            selected = min(results, key=lambda result: result["fit_score"])
            selected["selection"] = "lowest_mean_fit_error_no_candidate_in_tolerance"
        selected["accepted_candidates"] = len(accepted)
        selected["searched_candidates"] = iterations
        return selected

    def _evaluate_candidate(self, task: tuple[HistoricalParameters, int]) -> dict:
        parameters, replicates = task
        return self.evaluate_ensemble(parameters, replicates)

    @staticmethod
    def _fit_within_tolerance(result: dict[str, Any]) -> bool:
        return all(
            result["checkpoint_errors"][year]["within_tolerance"] for year in FIT_YEARS
        )

    @staticmethod
    def _regularization(parameters: dict[str, float]) -> float:
        """Prefer an ordinary accepted estimate over an exact edge-case fit."""
        priors = {
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
        }
        return sum(
            ((value - priors[name][0]) / priors[name][1]) ** 2
            for name, value in parameters.items()
        )

    def _population(
        self, parameters: HistoricalParameters, seed: int | None = None
    ) -> pl.DataFrame:
        other = parameters.baseline_other
        protestant = 1 - parameters.baseline_catholic - parameters.baseline_none - other
        weights = [
            (ReligiousBackground.CATHOLIC, parameters.baseline_catholic),
            (ReligiousBackground.PROTESTANT, protestant),
            (ReligiousBackground.OTHER, other),
            (ReligiousBackground.NONE, parameters.baseline_none),
        ]
        people = list(
            iter_population(
                self.sample_size,
                seed=self.seed if seed is None else seed,
                reference_year=1969,
                religion_weights=weights,
                age_bands=_HISTORICAL_AGE_BANDS,
                origin_weights=_HISTORICAL_ORIGINS,
            )
        )
        return pl.DataFrame(
            {
                "person_id": [
                    uuid.UUID(int=index + 1).bytes for index in range(len(people))
                ],
                "person_number": range(1, len(people) + 1),
                "birth_year": [person.birth_year for person in people],
                "religious_background": [
                    person.religious_background.value for person in people
                ],
                "probable_community": [
                    person.probable_community.value for person in people
                ],
                "gender": [person.gender.value for person in people],
                "education_level": [person.education_level.value for person in people],
                "location": [person.location.value for person in people],
                "origin": [person.origin.value for person in people],
            },
            schema=COLUMN_TYPES,
        )

    def _configured_model(self, parameters: HistoricalParameters) -> dict[str, Any]:
        config = configure_historical_model(
            self.base_config, asdict(parameters), self.component_config
        )
        config["rate_jitter"] = 0
        config["_simulation_scale"] = self.sample_size / self.component_baseline
        return config

    @staticmethod
    def _snapshot(population: pl.DataFrame) -> dict[str, Any]:
        counts = dict(population["religious_background"].value_counts().iter_rows())
        total = population.height
        return {
            "total_population": total,
            "shares": {
                background: counts.get(background, 0) / total
                for background in ("catholic", "protestant", "other", "none")
            },
        }

    def _score(self, snapshots: dict[int, dict], years: tuple[int, ...]) -> float:
        errors = []
        for year in years:
            predicted = snapshots[year]
            actual = self.benchmarks[year]
            actual_total = actual["total_population"]
            baseline_total = self.base_config["baseline_population"]
            errors.append(
                abs(
                    predicted["total_population"] / self.sample_size
                    - actual_total / baseline_total
                )
                * 0.25
            )
            for background, count in actual["religious_breakdown"].items():
                errors.append(
                    abs(predicted["shares"][background] - count / actual_total)
                )
        return sum(errors) / len(errors)

    def _checkpoint_errors(self, snapshots: dict[int, dict]) -> dict[int, dict]:
        results = {}
        baseline_total = self.base_config["baseline_population"]
        for year, predicted in snapshots.items():
            actual = self.benchmarks[year]
            actual_total = actual["total_population"]
            share_errors = {
                background: round(
                    100 * (predicted["shares"][background] - count / actual_total),
                    3,
                )
                for background, count in actual["religious_breakdown"].items()
            }
            population_error = (
                predicted["total_population"] / self.sample_size
                - actual_total / baseline_total
            ) / (actual_total / baseline_total)
            results[year] = {
                "population_percent": round(population_error * 100, 3),
                "share_percentage_points": share_errors,
                "within_tolerance": abs(population_error) <= 0.05
                and all(abs(error) <= 2.5 for error in share_errors.values()),
            }
        return results
