from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.models import Person
from ..data.repository import PersonRepository


class PopulationSnapshot:
    """Represents a population state snapshot"""

    def __init__(
        self,
        snapshot_id: str,
        year: int,
        population_count: int,
        demographics: Dict,
        timestamp: datetime,
        savepoint_name: str,
    ):
        self.snapshot_id = snapshot_id
        self.year = year
        self.population_count = population_count
        self.demographics = demographics
        self.timestamp = timestamp
        self.savepoint_name = savepoint_name


class PopulationManager:
    """Manages population with PostgreSQL snapshots"""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.repository = PersonRepository(db_session)
        self.snapshots: Dict[str, PopulationSnapshot] = {}

    def initialize_population(self, persons: List[Person]) -> int:
        """Initialize population with given persons"""
        self.clear_population()
        self.repository.bulk_create(persons)
        return len(persons)

    def clear_population(self) -> int:
        """Clear all persons from population (without committing)"""
        count = self.repository.count()
        self.db_session.execute(text("DELETE FROM persons"))
        # Don't commit here to preserve savepoints
        return count

    def create_snapshot(self, snapshot_id: str, year: int) -> PopulationSnapshot:
        """Create snapshot using PostgreSQL savepoints"""
        population_count = self.repository.count()
        demographics = self.repository.get_demographics_summary()
        timestamp = datetime.now()
        savepoint_name = f"sp_{snapshot_id}"

        # Create PostgreSQL savepoint
        self.db_session.execute(text(f"SAVEPOINT {savepoint_name}"))

        snapshot = PopulationSnapshot(
            snapshot_id=snapshot_id,
            year=year,
            population_count=population_count,
            demographics=demographics,
            timestamp=timestamp,
            savepoint_name=savepoint_name,
        )

        self.snapshots[snapshot_id] = snapshot
        return snapshot

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore to snapshot using PostgreSQL rollback"""
        if snapshot_id not in self.snapshots:
            return False

        snapshot = self.snapshots[snapshot_id]

        try:
            # PostgreSQL: rollback to savepoint
            self.db_session.execute(
                text(f"ROLLBACK TO SAVEPOINT {snapshot.savepoint_name}")
            )
            return True
        except Exception:
            return False

    def get_snapshot(self, snapshot_id: str) -> Optional[PopulationSnapshot]:
        """Get snapshot by ID"""
        return self.snapshots.get(snapshot_id)

    def list_snapshots(self) -> List[PopulationSnapshot]:
        """List all available snapshots"""
        return list(self.snapshots.values())

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot"""
        if snapshot_id not in self.snapshots:
            return False

        snapshot = self.snapshots[snapshot_id]

        try:
            # PostgreSQL: release savepoint
            self.db_session.execute(
                text(f"RELEASE SAVEPOINT {snapshot.savepoint_name}")
            )
        except Exception:
            pass  # Savepoint might already be released

        del self.snapshots[snapshot_id]
        return True

    def get_population_count(self) -> int:
        """Get current population count"""
        return self.repository.count()

    def get_demographics_summary(self) -> Dict:
        """Get current demographics summary"""
        return self.repository.get_demographics_summary()
