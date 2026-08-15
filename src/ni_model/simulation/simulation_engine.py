from contextlib import nullcontext

from sqlalchemy.orm import Session

from ..core.models import Person
from .model_director import ModelDirector


class SimulationEngine:
    """
    Executes mandatory sequential DB update pattern: births → deaths → migration
    """

    def __init__(self, db_session: Session, director: ModelDirector, recorder=None):
        self.db_session = db_session
        self.director = director
        self.recorder = recorder

    def _stage(self, name: str):
        return self.recorder.stage(name) if self.recorder else nullcontext()

    def run_simulation_year(self, year: int) -> dict:
        """Age the population, then apply demographic events without committing."""
        with self._stage("ageing"):
            (
                self.db_session.query(Person)
                .filter(Person.run_id == self.director.run_id)
                .update({Person.age: Person.age + 1}, synchronize_session=False)
            )
        with self._stage("births"):
            births = self.director.simulate_births(year)
        with self._stage("deaths"):
            deaths = self.director.simulate_deaths(year)
        with self._stage("external_migration"):
            immigration, emigration = self.director.simulate_migration_components(year)
        migration = immigration - emigration
        with self._stage("internal_relocation"):
            internal_migration = self.director.simulate_internal_migration(year)
        with self._stage("community_integration"):
            (
                community_transitions,
                transition_breakdown,
            ) = self.director.simulate_integration(year)

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
