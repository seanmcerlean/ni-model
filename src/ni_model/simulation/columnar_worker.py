"""Vectorised individual-level population simulation using Polars columns."""

import hashlib
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

EVENT_CODES = {
    "birth": 1,
    "death": 2,
    "arrival": 3,
    "departure": 4,
    "relocation": 5,
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

    @classmethod
    def baseline_frame(
        cls, db: Session, start_year: int, recorder=None
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
            cast(Person.gender, String).label("gender"),
            cast(Person.education_level, String).label("education_level"),
            cast(Person.location, String).label("location"),
            cast(Person.origin, String).label("origin"),
        ).filter(Person.run_id.is_(None))
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
    ) -> "ColumnarSimulationWorker":
        frame = cls.baseline_frame(db, start_year, recorder=recorder)
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
            count = int(self._rate(rule, rng) / 1000 * cohort.height)
            mothers = cohort.filter(
                (pl.col("gender") == "female")
                & ((year - pl.col("birth_year")).is_between(15, 49))
            )
            if count <= 0 or mothers.height == 0:
                continue
            parents = mothers[
                rng.choice(mothers.height, size=count, replace=True).tolist()
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
                    "religious_background": parents["religious_background"],
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

    def _deaths(self, year: int) -> int:
        total = 0
        for rule_index, rule in self._active_rules("death_rates", year):
            rng = self._rng(year, "death", rule_index)
            cohort = self.population.filter(
                self._filter_expression(rule.get("filters", {}), year)
            )
            count = int(self._rate(rule, rng) / 1000 * cohort.height)
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
            if cohort.height:
                templates = cohort[
                    rng.choice(cohort.height, size=change, replace=True).tolist()
                ]
                backgrounds = templates["religious_background"]
                locations = templates["location"]
            else:
                backgrounds = rng.choice(
                    ["catholic", "protestant", "other", "none"], size=change
                )
                locations = ["belfast"] * change
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
                    "origin": ["other"] * change,
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

    def _relocations(self, year: int) -> int:
        selected_numbers: set[int] = set()
        plans = []
        cohorts: dict[tuple, np.ndarray] = {}
        for rule_index, rule in self._active_rules("internal_migration_rates", year):
            rng = self._rng(year, "relocation", rule_index)
            filters = rule.get("filters", {})
            cohort_key = tuple(sorted(filters.items()))
            if cohort_key not in cohorts:
                cohort = self.population.filter(self._filter_expression(filters, year))
                cohorts[cohort_key] = cohort["person_number"].to_numpy()
            cohort_numbers = cohorts[cohort_key]
            count = int(self._rate(rule, rng) / 1000 * len(cohort_numbers))
            if selected_numbers:
                selected_array = np.fromiter(selected_numbers, dtype=np.int64)
                available = cohort_numbers[
                    ~np.isin(cohort_numbers, selected_array, assume_unique=True)
                ]
            else:
                available = cohort_numbers
            if count > 0 and len(available):
                numbers = rng.choice(
                    available, size=min(count, len(available)), replace=False
                ).tolist()
            else:
                numbers = []
            selected_numbers.update(numbers)
            plans.append((numbers, rule["destination"].lower()))
        moves = [
            (person_number, destination)
            for numbers, destination in plans
            for person_number in numbers
        ]
        if moves:
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
                .with_columns(pl.coalesce("new_location", "location").alias("location"))
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
        return len(selected_numbers)

    def run_year(self, year: int) -> dict:
        """Apply one sequential year without population-wide age updates."""
        with self._stage("births"):
            births = self._births(year)
        with self._stage("deaths"):
            deaths = self._deaths(year)
        with self._stage("external_migration"):
            immigration, emigration = self._external_migration(year)
        with self._stage("internal_relocation"):
            internal_migration = self._relocations(year)
        migration = immigration - emigration
        return {
            "year": year,
            "births": births,
            "deaths": deaths,
            "immigration": immigration,
            "emigration": emigration,
            "migration": migration,
            "internal_migration": internal_migration,
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
        gender_by_location = grouped("gender")
        origin_by_location = grouped("origin")
        age_by_location = grouped("age_band")
        locations = {}
        for location in Location:
            religious = religious_by_location[location.value]
            genders = gender_by_location[location.value]
            origins = origin_by_location[location.value]
            age_bands = age_by_location[location.value]
            locations[location.value] = {
                "total": sum(religious.values()),
                "religious_breakdown": religious,
                "gender_breakdown": genders,
                "origin_breakdown": origins,
                "age_bands": {
                    label: age_bands.get(label, 0)
                    for label in ("0-17", "18-35", "36-50", "51-70", "71+")
                },
            }
        religious = {}
        genders = {}
        for detail in locations.values():
            for key, value in detail["religious_breakdown"].items():
                religious[key] = religious.get(key, 0) + value
            for key, value in detail["gender_breakdown"].items():
                genders[key] = genders.get(key, 0) + value
        return {
            "total_population": aged.height,
            "religious_breakdown": religious,
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
            .group_by("location", "religious_background", "age")
            .len()
        )
        return [
            SimpleNamespace(
                location=Location(row["location"]),
                religious_background=ReligiousBackground(row["religious_background"]),
                age=row["age"],
                count=row["len"],
            )
            for row in rows.iter_rows(named=True)
        ]

    def checkpoint_digest(self) -> str:
        """Hash current population content for deterministic parity checks."""
        return hashlib.sha256(self.population.write_ipc(None).getvalue()).hexdigest()
