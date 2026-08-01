import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.models import Person, SimulationRun, SimulationSnapshot
from ..data.repository import PersonRepository


@dataclass
class PopulationSnapshot:
    """Metadata for a durable aggregate population snapshot."""

    snapshot_id: str
    year: int
    population_count: int
    demographics: Dict
    timestamp: datetime


class PopulationManager:
    """Manage an immutable baseline and isolated, durable run populations."""

    def __init__(self, db_session: Session, run_id: Optional[uuid.UUID] = None):
        self.db_session = db_session
        self.run_id = run_id
        self.repository = PersonRepository(db_session, run_id=run_id)

    @classmethod
    def create_run(
        cls,
        db_session: Session,
        model_path: str,
        start_year: int,
        end_year: int,
        adjustments: Optional[Dict] = None,
        clone_population: bool = True,
        owner_key: Optional[str] = None,
        status: str = "pending",
        population_limit: Optional[int] = None,
        baseline_profile: str = "current",
        represented_population_count: Optional[int] = None,
    ) -> SimulationRun:
        """Create a durable run and clone the immutable baseline into it."""
        available_count = (
            db_session.query(Person)
            .filter(
                Person.run_id.is_(None),
                Person.baseline_profile == baseline_profile,
            )
            .count()
        )
        if available_count == 0:
            raise ValueError(f"baseline profile '{baseline_profile}' is not seeded")
        baseline_count = (
            available_count
            if population_limit is None
            else min(available_count, population_limit)
        )
        run = SimulationRun(
            model_path=model_path,
            start_year=start_year,
            end_year=end_year,
            status=status,
            base_population_count=baseline_count,
            represented_population_count=(
                represented_population_count or available_count
            ),
            population_scale=(represented_population_count or available_count)
            / baseline_count,
            baseline_profile=baseline_profile,
            adjustments=adjustments or {},
            owner_key=owner_key,
        )
        db_session.add(run)
        db_session.flush()
        if clone_population:
            cls(db_session, run.id).reset_to_baseline()
        db_session.commit()
        return run

    def initialize_population(self, persons: List[Person]) -> int:
        """Replace this scope's population with the supplied people."""
        self.clear_population()
        self.repository.bulk_create(persons)
        return len(persons)

    def clear_population(self) -> int:
        """Delete only the current run population, preserving other users."""
        query = self.db_session.query(Person).filter(Person.run_id == self.run_id)
        count = query.count()
        query.delete(synchronize_session=False)
        return count

    def reset_to_baseline(self) -> int:
        """Restore this run from immutable baseline rows (`run_id IS NULL`)."""
        if self.run_id is None:
            raise ValueError("a run_id is required to restore the baseline")
        self.clear_population()
        run = self.db_session.get(SimulationRun, self.run_id)
        baseline = (
            self.db_session.query(Person)
            .filter(
                Person.run_id.is_(None),
                Person.baseline_profile == run.baseline_profile,
            )
            .order_by(Person.person_number, Person.id)
            .limit(run.base_population_count)
            .yield_per(10_000)
        )
        mappings = []
        for person in baseline:
            mappings.append(
                {
                    "id": uuid.uuid4(),
                    "run_id": self.run_id,
                    "baseline_profile": run.baseline_profile,
                    "age": person.age,
                    "birth_year": person.birth_year,
                    "religious_background": person.religious_background,
                    "gender": person.gender,
                    "education_level": person.education_level,
                    "location": person.location,
                    "origin": person.origin,
                }
            )
            if len(mappings) == 10_000:
                self.db_session.bulk_insert_mappings(Person, mappings)
                mappings = []
        if mappings:
            self.db_session.bulk_insert_mappings(Person, mappings)
        return self.repository.count()

    def create_snapshot(
        self,
        snapshot_id: str,
        year: int,
        data: Optional[Dict] = None,
    ) -> PopulationSnapshot:
        """Persist a durable aggregate snapshot for the current run."""
        demographics = data or self.repository.get_demographics_summary()
        timestamp = datetime.now(UTC)
        snapshot = PopulationSnapshot(
            snapshot_id=snapshot_id,
            year=year,
            population_count=self.repository.count(),
            demographics=demographics,
            timestamp=timestamp,
        )
        if self.run_id is not None:
            stored = (
                self.db_session.query(SimulationSnapshot)
                .filter(
                    SimulationSnapshot.run_id == self.run_id,
                    SimulationSnapshot.year == year,
                )
                .one_or_none()
            )
            if stored:
                stored.data = demographics
                stored.created_at = timestamp
            else:
                self.db_session.add(
                    SimulationSnapshot(
                        run_id=self.run_id,
                        year=year,
                        data=demographics,
                        created_at=timestamp,
                    )
                )
            self.db_session.flush()
        return snapshot

    def get_snapshot(self, year: int) -> Optional[PopulationSnapshot]:
        """Load persisted snapshot metadata by year."""
        if self.run_id is None:
            return None
        stored = (
            self.db_session.query(SimulationSnapshot)
            .filter(
                SimulationSnapshot.run_id == self.run_id,
                SimulationSnapshot.year == year,
            )
            .one_or_none()
        )
        if not stored:
            return None
        return PopulationSnapshot(
            snapshot_id=f"year_{year}",
            year=year,
            population_count=stored.data.get("total_population", 0),
            demographics=stored.data,
            timestamp=stored.created_at,
        )

    def list_snapshots(self) -> List[PopulationSnapshot]:
        """List durable snapshots for the current run."""
        if self.run_id is None:
            return []
        years = (
            self.db_session.query(SimulationSnapshot.year)
            .filter(SimulationSnapshot.run_id == self.run_id)
            .order_by(SimulationSnapshot.year)
            .all()
        )
        return [
            snapshot
            for (year,) in years
            if (snapshot := self.get_snapshot(year)) is not None
        ]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a durable snapshot by its `year_<year>` identifier."""
        if self.run_id is None or not snapshot_id.startswith("year_"):
            return False
        try:
            year = int(snapshot_id.removeprefix("year_"))
        except ValueError:
            return False
        deleted = (
            self.db_session.query(SimulationSnapshot)
            .filter(
                SimulationSnapshot.run_id == self.run_id,
                SimulationSnapshot.year == year,
            )
            .delete(synchronize_session=False)
        )
        return bool(deleted)

    def get_population_count(self) -> int:
        return self.repository.count()

    def get_demographics_summary(self) -> Dict:
        return self.repository.get_demographics_summary()
