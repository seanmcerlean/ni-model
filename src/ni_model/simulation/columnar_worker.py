"""Vectorised individual-level population simulation using Polars columns."""

import hashlib
import math
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional

import numpy as np
import polars as pl
from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session

from ..core.models import Location, Person, ReligiousBackground
from .relocation_calibration import relocation_pair_scales
from .sampling import stochastic_round

EVENT_CODES = {
    "birth": 1,
    "death": 2,
    "arrival": 3,
    "departure": 4,
    "relocation": 5,
    "integration": 6,
}

BACKGROUND_TYPE = pl.Enum(["catholic", "protestant", "other", "none"])
GENDER_TYPE = pl.Enum(["male", "female", "other"])
EDUCATION_TYPE = pl.Enum(
    ["pre_primary", "primary", "secondary", "tertiary", "postgraduate"]
)
LOCATION_TYPE = pl.Enum([location.value for location in Location])
ORIGIN_TYPE = pl.Enum(["ni", "roi", "gb", "other"])

COLUMN_TYPES = {
    "person_id": pl.Binary,
    "person_number": pl.Int64,
    "birth_year": pl.Int16,
    "religious_background": BACKGROUND_TYPE,
    "probable_community": BACKGROUND_TYPE,
    "gender": GENDER_TYPE,
    "education_level": EDUCATION_TYPE,
    "location": LOCATION_TYPE,
    "origin": ORIGIN_TYPE,
}


@dataclass(frozen=True)
class PopulationEvent:
    person_id: bytes
    year: int
    event_type: str
    data: Dict[str, Any]


@dataclass(frozen=True)
class RelocationCohort:
    rng: np.random.Generator
    person_numbers: np.ndarray
    expected: float
    source: str
    destination: str


class ColumnarSimulationWorker:
    """Evolve all residents as typed columns and retain individual events."""

    def __init__(
        self,
        population: pl.DataFrame,
        config: Dict[str, Any],
        run_id: uuid.UUID,
        seed: Optional[int] = None,
        recorder=None,
    ):
        if (
            "probable_community" not in population.columns
            and "religious_background" in population.columns
        ):
            population = population.with_columns(
                pl.when(
                    pl.col("religious_background").cast(pl.String).str.to_lowercase()
                    == "none"
                )
                .then(pl.lit("other"))
                .otherwise(
                    pl.col("religious_background").cast(pl.String).str.to_lowercase()
                )
                .alias("probable_community")
            )
        missing = set(COLUMN_TYPES) - set(population.columns)
        if missing:
            raise ValueError(f"population is missing columns: {sorted(missing)}")
        self.population = population.cast(COLUMN_TYPES)
        self.config = config
        self.run_id = run_id
        self.seed = config.get("random_seed", 42) if seed is None else seed
        self.jitter = config.get("rate_jitter", 0.0)
        self.recorder = recorder
        self.events: list[PopulationEvent] = []
        self._next_person_number = (self.population["person_number"].max() or 0) + 1
        baseline = self.config.get("component_baseline_population")
        self._component_scale = self.config.get(
            "_simulation_scale", self.population.height / baseline if baseline else 1.0
        )
        if self.config.get("annual_demographic_components"):
            for section in ("birth_rates", "death_rates", "migration_rates"):
                for rule in self.config.get(section, []):
                    rule["_component_weight"] = abs(float(rule["rate"]))
                    rule["_component_rate"] = float(rule["rate"])

    @classmethod
    def baseline_frame(
        cls,
        db: Session,
        start_year: int,
        recorder=None,
        population_limit: Optional[int] = None,
        baseline_profile: str = "current",
    ) -> pl.DataFrame:
        """Read immutable residents as columns without constructing Persons."""
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            person_id = func.decode(
                func.replace(cast(Person.id, String), "-", ""), "hex"
            ).label("person_id")
        else:
            person_id = cast(Person.id, String).label("person_id")
        query = db.query(
            person_id,
            Person.person_number,
            func.coalesce(Person.birth_year, start_year - Person.age).label(
                "birth_year"
            ),
            cast(Person.religious_background, String).label("religious_background"),
            cast(Person.probable_community, String).label("probable_community"),
            cast(Person.gender, String).label("gender"),
            cast(Person.education_level, String).label("education_level"),
            cast(Person.location, String).label("location"),
            cast(Person.origin, String).label("origin"),
        ).filter(
            Person.run_id.is_(None),
            Person.baseline_profile == baseline_profile,
        )
        query = query.order_by(Person.person_number, Person.id)
        if population_limit is not None:
            query = query.limit(population_limit)
        stage = recorder.stage("baseline_load") if recorder else nullcontext()
        with stage:
            if bind.dialect.name == "postgresql":
                statement = str(
                    query.statement.compile(
                        bind, compile_kwargs={"literal_binds": True}
                    )
                )
                uri = bind.url.render_as_string(hide_password=False).replace(
                    "postgresql+psycopg2://", "postgresql://", 1
                )
                frame = pl.read_database_uri(statement, uri, engine="adbc")
            else:
                batches = pl.read_database(
                    query.statement,
                    db.connection(),
                    iter_batches=True,
                    batch_size=10_000,
                )
                frame = pl.concat(batches, rechunk=False)
                frame = frame.with_columns(
                    pl.col("person_id").str.replace_all("-", "").str.decode("hex")
                )
        frame = frame.with_columns(
            pl.col(
                "religious_background",
                "probable_community",
                "gender",
                "education_level",
                "location",
                "origin",
            ).str.to_lowercase()
        )
        if frame["person_number"].null_count():
            frame = (
                frame.with_row_index("generated_number", offset=1)
                .with_columns(
                    pl.coalesce("person_number", "generated_number").alias(
                        "person_number"
                    )
                )
                .drop("generated_number")
            )
        return frame.cast(COLUMN_TYPES)

    @classmethod
    def load_baseline(
        cls,
        db: Session,
        config: Dict[str, Any],
        run_id: uuid.UUID,
        start_year: int,
        seed: Optional[int] = None,
        recorder=None,
        population_limit: Optional[int] = None,
        baseline_profile: str = "current",
    ) -> "ColumnarSimulationWorker":
        frame = cls.baseline_frame(
            db,
            start_year,
            recorder=recorder,
            population_limit=population_limit,
            baseline_profile=baseline_profile,
        )
        return cls(frame, config, run_id, seed=seed, recorder=recorder)

    def _stage(self, name: str):
        return self.recorder.stage(name) if self.recorder else nullcontext()

    def _rng(self, year: int, event_type: str, rule_index: int) -> np.random.Generator:
        return np.random.default_rng(
            np.random.SeedSequence(
                [self.seed, year, EVENT_CODES[event_type], rule_index]
            )
        )

    def _active_rules(self, section: str, year: int) -> Iterable[tuple[int, dict]]:
        for index, rule in enumerate(self.config.get(section, [])):
            if year < rule.get("year_min", 0) or year > rule.get("year_max", 9999):
                continue
            yield index, rule

    def _apply_component_controls(self, year: int, section: str | None = None) -> None:
        """Turn observed annual totals into stochastic, group-weighted rates."""
        sections = (
            ("birth_rates", "death_rates", "migration_rates")
            if section is None
            else (section,)
        )
        components = self.config.get("annual_demographic_components", {})
        component = components.get(year) or components.get(str(year))
        if component is None:
            for section_name in sections:
                for rule in self.config.get(section_name, []):
                    if "_component_rate" in rule:
                        rule["rate"] = rule["_component_rate"]
            return
        targets = {
            "birth_rates": component["births"] * self._component_scale,
            "death_rates": component["deaths"] * self._component_scale,
            "migration_rates": component["population_adjustment"]
            * self._component_scale,
        }
        target_multipliers = self.config.get("_component_target_multipliers", {})
        for section_name, target in targets.items():
            if section_name not in sections:
                continue
            target *= target_multipliers.get(section_name, 1.0)
            active = list(self._active_rules(section_name, year))
            weighted_population = 0.0
            cohorts = []
            for _index, rule in active:
                cohort_size = self.population.filter(
                    self._filter_expression(rule.get("filters", {}), year)
                ).height
                weight = rule.get("_component_weight", abs(float(rule["rate"])))
                weighted_population += weight * cohort_size
                cohorts.append((rule, weight, cohort_size))
            if not weighted_population:
                continue
            desired = int(round(abs(target)))
            exact = [
                desired * weight * cohort_size / weighted_population
                for _rule, weight, cohort_size in cohorts
            ]
            allocated = [math.floor(value) for value in exact]
            remainder = desired - sum(allocated)
            order = sorted(
                range(len(exact)),
                key=lambda index: exact[index] - allocated[index],
                reverse=True,
            )
            for index in order[:remainder]:
                allocated[index] += 1
            sign = -1 if target < 0 else 1
            for (rule, _weight, cohort_size), count in zip(cohorts, allocated):
                rule["rate"] = (
                    (count + 1e-9) * 1000 / cohort_size * sign if cohort_size else 0
                )

    @staticmethod
    def _filter_expression(filters: dict, year: int) -> pl.Expr:
        expression = pl.lit(True)
        for key, value in filters.items():
            if key == "age_min":
                expression &= year - pl.col("birth_year") >= value
            elif key == "age_max":
                expression &= year - pl.col("birth_year") <= value
            else:
                normalized = value.lower() if isinstance(value, str) else value
                expression &= pl.col(key) == normalized
        return expression

    def _rate(self, rule: dict, rng: np.random.Generator) -> float:
        rate = float(rule["rate"])
        return rate * rng.uniform(1 - self.jitter, 1 + self.jitter)

    @staticmethod
    def _selected_ids(
        cohort: pl.DataFrame, count: int, rng: np.random.Generator
    ) -> list[bytes]:
        if count <= 0 or cohort.height == 0:
            return []
        positions = rng.choice(
            cohort.height, size=min(count, cohort.height), replace=False
        )
        return cohort[positions.tolist()]["person_id"].to_list()

    def _new_ids(self, year: int, event_type: str, count: int) -> list[bytes]:
        namespace = uuid.uuid5(self.run_id, f"{year}:{event_type}")
        offset = sum(
            event.event_type == event_type and event.year == year
            for event in self.events
        )
        return [
            uuid.uuid5(namespace, str(offset + index)).bytes for index in range(count)
        ]

    def _append_people(self, people: pl.DataFrame) -> None:
        if people.height:
            self.population = pl.concat([self.population, people.cast(COLUMN_TYPES)])

    def _remove_people(
        self, person_ids: list[bytes], year: int, event_type: str
    ) -> int:
        if not person_ids:
            return 0
        selected = self.population.filter(pl.col("person_id").is_in(person_ids))
        for person_id in selected["person_id"]:
            self.events.append(PopulationEvent(person_id, year, event_type, {}))
        self.population = self.population.filter(~pl.col("person_id").is_in(person_ids))
        return len(person_ids)

    def _births(self, year: int) -> int:
        total = 0
        for rule_index, rule in self._active_rules("birth_rates", year):
            rng = self._rng(year, "birth", rule_index)
            cohort = self.population.filter(
                self._filter_expression(rule.get("filters", {}), year)
            )
            probability = min(self._rate(rule, rng) / 1000, 1.0)
            count = int(rng.binomial(cohort.height, probability))
            mothers = cohort.filter(
                (pl.col("gender") == "female")
                & ((year - pl.col("birth_year")).is_between(15, 49))
            )
            if count <= 0 or mothers.height == 0:
                continue
            parents = mothers[
                rng.choice(mothers.height, size=count, replace=True).tolist()
            ]
            backgrounds = self._child_backgrounds(parents, year, rng)
            probable_communities = [
                parent if background == "none" else background
                for parent, background in zip(
                    parents["probable_community"].to_list(), backgrounds
                )
            ]
            ids = self._new_ids(year, "birth", count)
            numbers = list(
                range(self._next_person_number, self._next_person_number + count)
            )
            self._next_person_number += count
            newborns = pl.DataFrame(
                {
                    "person_id": ids,
                    "person_number": numbers,
                    "birth_year": [year] * count,
                    "religious_background": backgrounds,
                    "probable_community": probable_communities,
                    "gender": rng.choice(["male", "female"], size=count),
                    "education_level": ["pre_primary"] * count,
                    "location": parents["location"],
                    "origin": ["ni"] * count,
                },
                schema=COLUMN_TYPES,
            )
            self._append_people(newborns)
            for row in newborns.iter_rows(named=True):
                self.events.append(
                    PopulationEvent(row["person_id"], year, "birth", row)
                )
            total += count
        return total

    def _child_backgrounds(
        self, parents: pl.DataFrame, year: int, rng: np.random.Generator
    ) -> list[str]:
        active = {
            rule["source"].lower(): rule["probabilities"]
            for rule in self.config.get("child_background_rules", [])
            if rule.get("year_min", 0) <= year <= rule.get("year_max", 9999)
        }
        backgrounds = []
        for source in parents["religious_background"].to_list():
            probabilities = active.get(source)
            if not probabilities:
                backgrounds.append(source)
                continue
            destinations = [key.lower() for key in probabilities]
            backgrounds.append(
                str(rng.choice(destinations, p=list(probabilities.values())))
            )
        return backgrounds

    def _deaths(self, year: int) -> int:
        total = 0
        age_rates = self.config.get("mortality_age_rates")
        for rule_index, rule in self._active_rules("death_rates", year):
            rng = self._rng(year, "death", rule_index)
            cohort = self.population.filter(
                self._filter_expression(rule.get("filters", {}), year)
            )
            count = int(self._rate(rule, rng) / 1000 * cohort.height)
            if age_rates and count > 0:
                ages = year - cohort["birth_year"].to_numpy()
                weights = np.zeros(cohort.height, dtype=np.float64)
                for band in age_rates:
                    mask = (ages >= band["age_min"]) & (ages <= band["age_max"])
                    weights[mask] = band["rate"]
                eligible = np.flatnonzero(weights > 0)
                count = min(count, len(eligible))
                probabilities = weights[eligible] / weights[eligible].sum()
                selected = rng.choice(
                    eligible, size=count, replace=False, p=probabilities
                )
                ids = cohort[selected.tolist()]["person_id"].to_list()
            else:
                ids = self._selected_ids(cohort, count, rng)
            total += self._remove_people(ids, year, "death")
        return total

    def _external_migration(self, year: int) -> tuple[int, int]:
        immigration = emigration = 0
        for rule_index, rule in self._active_rules("migration_rates", year):
            event_type = "arrival" if rule["rate"] >= 0 else "departure"
            rng = self._rng(year, event_type, rule_index)
            cohort = self.population.filter(
                self._filter_expression(rule.get("filters", {}), year)
            )
            change = int(self._rate(rule, rng) / 1000 * cohort.height)
            if change < 0:
                ids = self._selected_ids(cohort, abs(change), rng)
                emigration += self._remove_people(ids, year, "departure")
                continue
            if change == 0:
                continue
            profiles = self.config.get("immigration_profiles", [])
            if profiles:
                weights = np.array(
                    [profile["weight"] for profile in profiles], dtype=np.float64
                )
                selected_profiles = rng.choice(
                    len(profiles), size=change, replace=True, p=weights / weights.sum()
                )
                backgrounds = [
                    profiles[index]["religious_background"].lower()
                    for index in selected_profiles
                ]
                locations = [
                    profiles[index]["location"].lower() for index in selected_profiles
                ]
                probable_communities = self._initial_probable_communities(
                    backgrounds, locations, rng
                )
                origins = [
                    profiles[index]["origin"].lower() for index in selected_profiles
                ]
            elif cohort.height:
                templates = cohort[
                    rng.choice(cohort.height, size=change, replace=True).tolist()
                ]
                backgrounds = templates["religious_background"]
                probable_communities = templates["probable_community"]
                locations = templates["location"]
                origins = ["other"] * change
            else:
                backgrounds = rng.choice(
                    ["catholic", "protestant", "other", "none"], size=change
                )
                locations = ["belfast"] * change
                origins = ["other"] * change
                probable_communities = self._initial_probable_communities(
                    backgrounds, locations, rng
                )
            ids = self._new_ids(year, "arrival", change)
            numbers = list(
                range(self._next_person_number, self._next_person_number + change)
            )
            self._next_person_number += change
            arrivals = pl.DataFrame(
                {
                    "person_id": ids,
                    "person_number": numbers,
                    "birth_year": year - rng.integers(18, 46, size=change),
                    "religious_background": backgrounds,
                    "probable_community": probable_communities,
                    "gender": rng.choice(["male", "female"], size=change),
                    "education_level": rng.choice(
                        [
                            "pre_primary",
                            "primary",
                            "secondary",
                            "tertiary",
                            "postgraduate",
                        ],
                        size=change,
                    ),
                    "location": locations,
                    "origin": origins,
                },
                schema=COLUMN_TYPES,
            )
            self._append_people(arrivals)
            for row in arrivals.iter_rows(named=True):
                self.events.append(
                    PopulationEvent(row["person_id"], year, "arrival", row)
                )
            immigration += change
        return immigration, emigration

    def _relocation_cohorts(self, year: int) -> list[RelocationCohort]:
        cohorts: dict[tuple, np.ndarray] = {}
        active = []
        for rule_index, rule in self._active_rules("internal_migration_rates", year):
            rng = self._rng(year, "relocation", rule_index)
            filters = rule.get("filters", {})
            cohort_key = tuple(sorted(filters.items()))
            if cohort_key not in cohorts:
                cohort = self.population.filter(self._filter_expression(filters, year))
                cohorts[cohort_key] = cohort["person_number"].to_numpy()
            cohort_numbers = cohorts[cohort_key]
            expected = self._rate(rule, rng) / 1000 * len(cohort_numbers)
            source = str(filters.get("location", "")).lower()
            destination = rule["destination"].lower()
            active.append(
                RelocationCohort(rng, cohort_numbers, expected, source, destination)
            )
        return active

    def _relocation_scales(self, cohorts, year):
        raw_flows = {}
        for cohort in cohorts:
            if not cohort.source:
                continue
            pair = (cohort.source, cohort.destination)
            raw_flows[pair] = raw_flows.get(pair, 0.0) + cohort.expected
        current_counts = {
            str(location): count
            for location, count in self.population.group_by("location")
            .len()
            .iter_rows()
        }
        scales = relocation_pair_scales(
            current_counts,
            raw_flows,
            self.config.get("lgd_population_targets", []),
            self.config.get("lgd_relocation_calibration", {}),
            year,
        )
        return scales

    @staticmethod
    def _select_relocations(cohorts, scales):
        selected_numbers: set[int] = set()
        plans = []
        for cohort in cohorts:
            pair = (cohort.source, cohort.destination)
            expected = cohort.expected * scales.get(pair, 1.0)
            count = stochastic_round(expected, cohort.rng.random())
            if selected_numbers:
                selected_array = np.fromiter(selected_numbers, dtype=np.int64)
                available = cohort.person_numbers[
                    ~np.isin(cohort.person_numbers, selected_array, assume_unique=True)
                ]
            else:
                available = cohort.person_numbers
            if count > 0 and len(available):
                numbers = cohort.rng.choice(
                    available, size=min(count, len(available)), replace=False
                ).tolist()
            else:
                numbers = []
            selected_numbers.update(numbers)
            plans.append((numbers, cohort.destination))
        return [
            (person_number, destination)
            for numbers, destination in plans
            for person_number in numbers
        ]

    def _apply_relocations(self, moves, year):
        if not moves:
            return
        move_frame = pl.DataFrame(
            moves,
            schema={"person_number": pl.Int64, "new_location": pl.String},
            orient="row",
        )
        previous = self.population.filter(
            pl.col("person_number").is_in(move_frame["person_number"].implode())
        ).select("person_number", "person_id", "location")
        prior = {
            person_number: (person_id, location)
            for person_number, person_id, location in previous.iter_rows()
        }
        self.population = (
            self.population.join(move_frame, on="person_number", how="left")
            .with_columns(
                pl.coalesce("new_location", "location")
                .cast(LOCATION_TYPE)
                .alias("location")
            )
            .drop("new_location")
        )
        self.events.extend(
            PopulationEvent(
                prior[person_number][0],
                year,
                "relocation",
                {"from": prior[person_number][1], "to": destination},
            )
            for person_number, destination in moves
        )

    def _relocations(self, year: int) -> int:
        cohorts = self._relocation_cohorts(year)
        moves = self._select_relocations(
            cohorts, self._relocation_scales(cohorts, year)
        )
        self._apply_relocations(moves, year)
        return len(moves)

    def _integration(self, year: int) -> tuple[int, dict[str, int]]:
        """Apply competing community-identification flows simultaneously."""
        selected_numbers: set[int] = set()
        plans = []
        cohorts: dict[tuple, pl.DataFrame] = {}
        for rule_index, rule in self._active_rules("integration_rates", year):
            rng = self._rng(year, "integration", rule_index)
            filters = rule.get("filters", {})
            cohort_key = tuple(sorted(filters.items()))
            if cohort_key not in cohorts:
                cohorts[cohort_key] = self.population.filter(
                    self._filter_expression(filters, year)
                )
            cohort = cohorts[cohort_key]
            count = int(self._rate(rule, rng) / 1000 * cohort.height)
            available = cohort
            if selected_numbers:
                available = available.filter(
                    ~pl.col("person_number").is_in(list(selected_numbers))
                )
            selected = self._selected_ids(available, count, rng)
            if selected:
                numbers = available.filter(pl.col("person_id").is_in(selected))[
                    "person_number"
                ].to_list()
            else:
                numbers = []
            selected_numbers.update(numbers)
            plans.append((numbers, rule["destination"].lower()))
        changes = [
            (person_number, destination)
            for numbers, destination in plans
            for person_number in numbers
        ]
        breakdown: dict[str, int] = {}
        if changes:
            change_frame = pl.DataFrame(
                changes,
                schema={"person_number": pl.Int64, "new_background": pl.String},
                orient="row",
            )
            previous = self.population.filter(
                pl.col("person_number").is_in(change_frame["person_number"])
            ).select(
                "person_number",
                "person_id",
                "religious_background",
                "probable_community",
            )
            prior = {
                number: (person_id, background, probable)
                for number, person_id, background, probable in previous.iter_rows()
            }
            self.population = (
                self.population.join(change_frame, on="person_number", how="left")
                .with_columns(
                    pl.coalesce("new_background", "religious_background")
                    .cast(BACKGROUND_TYPE)
                    .alias("religious_background")
                )
                .with_columns(
                    pl.when(pl.col("new_background").is_not_null())
                    .then(
                        pl.when(pl.col("new_background") == "none")
                        .then(pl.col("probable_community"))
                        .otherwise(pl.col("new_background"))
                    )
                    .otherwise(pl.col("probable_community"))
                    .cast(BACKGROUND_TYPE)
                    .alias("probable_community")
                )
                .drop("new_background")
            )
            for person_number, destination in changes:
                person_id, source, _ = prior[person_number]
                key = f"{source}_to_{destination}"
                breakdown[key] = breakdown.get(key, 0) + 1
                self.events.append(
                    PopulationEvent(
                        person_id,
                        year,
                        "integration",
                        {"from": source, "to": destination},
                    )
                )
        return len(selected_numbers), breakdown

    def run_year(self, year: int) -> dict:
        """Apply one sequential year without population-wide age updates."""
        self._apply_component_controls(year, "birth_rates")
        with self._stage("births"):
            births = self._births(year)
        self._apply_component_controls(year, "death_rates")
        with self._stage("deaths"):
            deaths = self._deaths(year)
        self._apply_component_controls(year, "migration_rates")
        with self._stage("external_migration"):
            immigration, emigration = self._external_migration(year)
        with self._stage("internal_relocation"):
            internal_migration = self._relocations(year)
        with self._stage("community_integration"):
            community_transitions, transition_breakdown = self._integration(year)
        migration = immigration - emigration
        return {
            "year": year,
            "births": births,
            "deaths": deaths,
            "immigration": immigration,
            "emigration": emigration,
            "migration": migration,
            "internal_migration": internal_migration,
            "community_transitions": community_transitions,
            "community_transition_breakdown": transition_breakdown,
            "net_change": births - deaths + migration,
        }

    def demographic_summary(self, year: int) -> dict:
        """Return the aggregate-only payload inputs required by the UI."""
        aged = self.population.with_columns(
            (year - pl.col("birth_year")).alias("age")
        ).with_columns(
            pl.when(pl.col("age") <= 17)
            .then(pl.lit("0-17"))
            .when(pl.col("age") <= 35)
            .then(pl.lit("18-35"))
            .when(pl.col("age") <= 50)
            .then(pl.lit("36-50"))
            .when(pl.col("age") <= 70)
            .then(pl.lit("51-70"))
            .otherwise(pl.lit("71+"))
            .alias("age_band")
        )

        def grouped(column: str) -> dict:
            result = {location.value: {} for location in Location}
            for location, value, count in (
                aged.group_by("location", column).len().iter_rows()
            ):
                result[location][value] = count
            return result

        religious_by_location = grouped("religious_background")
        probable_by_location = grouped("probable_community")
        gender_by_location = grouped("gender")
        origin_by_location = grouped("origin")
        age_by_location = grouped("age_band")
        locations = {}
        for location in Location:
            religious = religious_by_location[location.value]
            probable = probable_by_location[location.value]
            genders = gender_by_location[location.value]
            origins = origin_by_location[location.value]
            age_bands = age_by_location[location.value]
            locations[location.value] = {
                "total": sum(religious.values()),
                "religious_breakdown": religious,
                "probable_community_breakdown": probable,
                "gender_breakdown": genders,
                "origin_breakdown": origins,
                "age_bands": {
                    label: age_bands.get(label, 0)
                    for label in ("0-17", "18-35", "36-50", "51-70", "71+")
                },
            }
        religious = {}
        probable = {}
        genders = {}
        for detail in locations.values():
            for key, value in detail["religious_breakdown"].items():
                religious[key] = religious.get(key, 0) + value
            for key, value in detail["probable_community_breakdown"].items():
                probable[key] = probable.get(key, 0) + value
            for key, value in detail["gender_breakdown"].items():
                genders[key] = genders.get(key, 0) + value
        return {
            "total_population": aged.height,
            "religious_breakdown": religious,
            "probable_community_breakdown": probable,
            "gender_breakdown": genders,
            "location_breakdown": {
                key: detail["total"]
                for key, detail in locations.items()
                if detail["total"]
            },
            "locations": locations,
        }

    def voting_rows(self, year: int):
        """Return compact shared polling inputs without person-level transfer."""
        rows = (
            self.population.with_columns((year - pl.col("birth_year")).alias("age"))
            .filter(pl.col("age") >= 18)
            .group_by("location", "religious_background", "probable_community", "age")
            .len()
        )
        return [
            SimpleNamespace(
                location=Location(row["location"]),
                religious_background=ReligiousBackground(row["religious_background"]),
                probable_community=ReligiousBackground(row["probable_community"]),
                age=row["age"],
                count=row["len"],
            )
            for row in rows.iter_rows(named=True)
        ]

    @staticmethod
    def _initial_probable_communities(backgrounds, locations, rng) -> list[str]:
        """Infer lineage for new None records while preserving all other groups."""
        from ..data.probable_community import (
            NONE_PROBABLE_CATHOLIC_BY_LOCATION,
            NONE_PROBABLE_OTHER,
        )

        result = []
        for background, location in zip(backgrounds, locations):
            value = str(background)
            if value != "none":
                result.append(value)
                continue
            if rng.random() < NONE_PROBABLE_OTHER:
                result.append("other")
                continue
            probability = NONE_PROBABLE_CATHOLIC_BY_LOCATION[Location(str(location))]
            result.append("catholic" if rng.random() < probability else "protestant")
        return result

    def checkpoint_digest(self) -> str:
        """Hash current population content for deterministic parity checks."""
        return hashlib.sha256(self.population.write_ipc(None).getvalue()).hexdigest()
