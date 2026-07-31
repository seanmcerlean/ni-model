from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.models import SimulationRun
from .model_director import ModelDirector
from .population_manager import PopulationManager
from .simulation_engine import SimulationEngine


class SimulationOrchestrator:
    """Coordinates multi-year simulations with snapshot and rollback support"""

    def __init__(self, db_session: Session, director: ModelDirector, recorder=None):
        self.db_session = db_session
        self.engine = SimulationEngine(db_session, director, recorder=recorder)
        self.population_manager = PopulationManager(db_session, director.run_id)
        self.results: List[Dict] = []

    def run(self, start_year: int, end_year: int) -> List[Dict]:
        """Run simulation from start_year to end_year inclusive"""
        self.results = list(self._iter_years(start_year, end_year))
        return self.results

    def _iter_years(self, start_year: int, end_year: int):
        """Yield result dict per year, flushing after each"""
        for year in range(start_year, end_year + 1):
            result = self.engine.run_simulation_year(year)
            self.db_session.flush()
            yield result

    def rollback_to_year(self, year: int) -> bool:
        """Restore the durable baseline; callers can deterministically replay."""
        run_id = self.engine.director.run_id
        run = self.db_session.get(SimulationRun, run_id) if run_id else None
        if not run or year != run.start_year:
            return False
        self.population_manager.reset_to_baseline()
        return True

    def get_result(self, year: int) -> Optional[Dict]:
        """Get simulation result for a specific year"""
        return next((r for r in self.results if r["year"] == year), None)

    def get_population_count(self) -> int:
        """Get current population count"""
        return self.population_manager.get_population_count()

    def get_demographics(self) -> Dict:
        """Get current population demographics"""
        return self.population_manager.get_demographics_summary()
