"""Reconstruct individual population state from baselines, checkpoints, and events."""

import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

import polars as pl
from sqlalchemy.orm import Session

from ..core.models import (
    Person,
    SimulationCheckpoint,
    SimulationPersonEvent,
    SimulationRun,
)
from .columnar_worker import COLUMN_TYPES, ColumnarSimulationWorker
from .event_store import EventStore


class PopulationReconstructor:
    def __init__(self, db: Session):
        self.db = db

    def reconstruct(self, run: SimulationRun, year: int) -> pl.DataFrame:
        if year < run.start_year or year > run.end_year:
            raise ValueError("year is outside the simulation run")
        checkpoint = (
            self.db.query(SimulationCheckpoint)
            .filter(
                SimulationCheckpoint.run_id == run.id,
                SimulationCheckpoint.year <= year,
            )
            .order_by(SimulationCheckpoint.year.desc())
            .first()
        )
        if checkpoint:
            population = EventStore.load(checkpoint)
            after_year = checkpoint.year
        else:
            population = ColumnarSimulationWorker.baseline_frame(
                self.db,
                run.start_year,
                population_limit=run.base_population_count,
                baseline_profile=run.baseline_profile,
            )
            after_year = run.start_year - 1
        events = (
            self.db.query(SimulationPersonEvent)
            .filter(
                SimulationPersonEvent.run_id == run.id,
                SimulationPersonEvent.year > after_year,
                SimulationPersonEvent.year <= year,
            )
            .order_by(SimulationPersonEvent.year, SimulationPersonEvent.id)
            .all()
        )
        return self.apply_events(population, events)

    @staticmethod
    def apply_events(
        population: pl.DataFrame, events: list[SimulationPersonEvent]
    ) -> pl.DataFrame:
        for event_year in sorted({event.year for event in events}):
            yearly = [event for event in events if event.year == event_year]
            removed = [
                event.person_id.bytes
                for event in yearly
                if event.event_type in {"death", "departure"}
            ]
            if removed:
                population = population.filter(~pl.col("person_id").is_in(removed))
            additions = [
                {
                    **event.data,
                    "person_id": uuid.UUID(event.data["person_id"]).bytes,
                }
                for event in yearly
                if event.event_type in {"birth", "arrival"}
            ]
            if additions:
                population = pl.concat(
                    [
                        population,
                        pl.DataFrame(additions)
                        .select(*COLUMN_TYPES)
                        .cast(COLUMN_TYPES),
                    ]
                )
            moves = [
                (event.person_id.bytes, event.data["to"])
                for event in yearly
                if event.event_type == "relocation"
            ]
            if moves:
                move_frame = pl.DataFrame(
                    moves,
                    schema={"person_id": pl.Binary, "new_location": pl.String},
                    orient="row",
                )
                population = (
                    population.join(move_frame, on="person_id", how="left")
                    .with_columns(
                        pl.coalesce("new_location", "location").alias("location")
                    )
                    .drop("new_location")
                )
            transitions = [
                (event.person_id.bytes, event.data["to"])
                for event in yearly
                if event.event_type == "integration"
            ]
            if transitions:
                transition_frame = pl.DataFrame(
                    transitions,
                    schema={"person_id": pl.Binary, "new_background": pl.String},
                    orient="row",
                )
                population = (
                    population.join(transition_frame, on="person_id", how="left")
                    .with_columns(
                        pl.coalesce("new_background", "religious_background").alias(
                            "religious_background"
                        )
                    )
                    .drop("new_background")
                )
        return population.cast(COLUMN_TYPES)

    def page(
        self,
        run: SimulationRun,
        year: int,
        offset: int,
        limit: int,
        location: str = None,
        religious_background: str = None,
    ) -> tuple[int, list[dict]]:
        checkpoint = (
            self.db.query(SimulationCheckpoint)
            .filter(
                SimulationCheckpoint.run_id == run.id,
                SimulationCheckpoint.year == year,
            )
            .one_or_none()
        )
        if checkpoint:
            parsed = urlparse(checkpoint.storage_uri)
            if parsed.scheme != "file":
                raise ValueError("only local file checkpoints are currently supported")
            lazy = pl.scan_parquet(Path(unquote(parsed.path)))
            if location:
                lazy = lazy.filter(pl.col("location") == location)
            if religious_background:
                lazy = lazy.filter(
                    pl.col("religious_background") == religious_background
                )
            total = lazy.select(pl.len()).collect().item()
            frame = lazy.slice(offset, limit).collect()
        else:
            frame = self.reconstruct(run, year)
            if location:
                frame = frame.filter(pl.col("location") == location)
            if religious_background:
                frame = frame.filter(
                    pl.col("religious_background") == religious_background
                )
            total = frame.height
            frame = frame.slice(offset, limit)
        return total, self._records(frame, year)

    @staticmethod
    def _records(frame: pl.DataFrame, year: int) -> list[dict]:
        records = (
            frame.with_columns((year - pl.col("birth_year")).alias("age"))
            .select(
                "person_id",
                "person_number",
                "birth_year",
                "age",
                "religious_background",
                "gender",
                "education_level",
                "location",
                "origin",
            )
            .to_dicts()
        )
        for record in records:
            record["person_id"] = str(uuid.UUID(bytes=record["person_id"]))
        return records

    def history(self, run: SimulationRun, person_id: uuid.UUID) -> dict:
        baseline = (
            self.db.query(Person)
            .filter(
                Person.run_id.is_(None),
                Person.baseline_profile == run.baseline_profile,
                Person.id == person_id,
            )
            .one_or_none()
        )
        events = (
            self.db.query(SimulationPersonEvent)
            .filter(
                SimulationPersonEvent.run_id == run.id,
                SimulationPersonEvent.person_id == person_id,
            )
            .order_by(SimulationPersonEvent.year, SimulationPersonEvent.id)
            .all()
        )
        initial = None
        if baseline:
            initial = {
                "person_id": str(baseline.id),
                "person_number": baseline.person_number,
                "birth_year": (
                    baseline.birth_year
                    if baseline.birth_year is not None
                    else run.start_year - baseline.age
                ),
                "religious_background": baseline.religious_background.value,
                "gender": baseline.gender.value,
                "education_level": baseline.education_level.value,
                "location": baseline.location.value,
                "origin": baseline.origin.value,
            }
        elif events and events[0].event_type in {"birth", "arrival"}:
            initial = events[0].data
        if initial is None:
            raise LookupError("person is not part of this simulation run")
        return {
            "person_id": str(person_id),
            "initial": initial,
            "events": [
                {
                    "year": event.year,
                    "event_type": event.event_type,
                    "data": event.data,
                }
                for event in events
            ],
        }
