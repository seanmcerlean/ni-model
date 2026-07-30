from typing import Any, Dict

from src.ni_model.simulation.simulation_engine import SimulationEngine


class TestSimulationEngine(SimulationEngine):
    """Test implementation of SimulationEngine for testing interface compliance"""

    def __init__(self, db_session):
        super().__init__(db_session)
        self.births_called = False
        self.deaths_called = False
        self.migration_called = False

    def simulate_births(self, year: int, parameters: Dict[str, Any]) -> int:
        self.births_called = True
        return parameters.get("birth_rate", 0)

    def simulate_deaths(self, year: int, parameters: Dict[str, Any]) -> int:
        self.deaths_called = True
        return parameters.get("death_rate", 0)

    def simulate_migration(self, year: int, parameters: Dict[str, Any]) -> int:
        self.migration_called = True
        return parameters.get("migration_rate", 0)

    def get_model_name(self) -> str:
        return "TestModel"

    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        required = ["birth_rate", "death_rate", "migration_rate"]
        return all(key in parameters for key in required)
