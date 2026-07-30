from sqlalchemy.orm import Session

from ..core.models import Person
from .model_director import ModelDirector


class SimulationEngine:
    """
    Executes mandatory sequential DB update pattern: births → deaths → migration
    """

    def __init__(self, db_session: Session, director: ModelDirector):
        self.db_session = db_session
        self.director = director

    def run_simulation_year(self, year: int) -> dict:
        """Age the population, then apply demographic events without committing."""
        self.db_session.query(Person).update(
            {Person.age: Person.age + 1}, synchronize_session=False
        )
        births = self.director.simulate_births(year)
        deaths = self.director.simulate_deaths(year)
        migration = self.director.simulate_migration(year)
        internal_migration = self.director.simulate_internal_migration(year)

        return {
            "year": year,
            "births": births,
            "deaths": deaths,
            "migration": migration,
            "internal_migration": internal_migration,
            "net_change": births - deaths + migration,
        }
