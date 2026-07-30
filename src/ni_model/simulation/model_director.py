import random
from typing import Any, Dict, List

import yaml
from sqlalchemy.orm import Session

from ..core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    ReligiousBackground,
)
from .demographic_calculators import (
    BirthCalculator,
    DeathCalculator,
    InternalMigrationCalculator,
    MigrationCalculator,
)


class ModelDirector:
    """Orchestrates multiple demographic calculators from configuration"""

    def __init__(self, db_session: Session, config: Dict[str, Any]):
        self.db_session = db_session
        self.config = config
        self.jitter = config.get("rate_jitter", 0.05)

    def _jittered_rate(self, rate: float) -> float:
        """Apply uniform random jitter of ±jitter% to rate"""
        return rate * random.uniform(1 - self.jitter, 1 + self.jitter)

    def _is_active(self, rate_config: Dict, year: int) -> bool:
        """Return True if rate config applies to the given simulation year"""
        year_min = rate_config.get("year_min")
        year_max = rate_config.get("year_max")
        if year_min is not None and year < year_min:
            return False
        if year_max is not None and year > year_max:
            return False
        return True

    def _build_calculators(self, rate_configs: List[Dict], calculator_class, year: int):
        """Build calculator instances active for the given year"""
        calculators = []
        for config in rate_configs:
            if not self._is_active(config, year):
                continue
            filters = self._parse_filters(config.get("filters", {}))
            calc = calculator_class(
                self.db_session,
                rate=self._jittered_rate(config["rate"]),
                query_filters=filters,
            )
            calculators.append(calc)
        return calculators

    def _build_internal_migration_calculators(
        self, rate_configs: List[Dict], year: int
    ) -> List["InternalMigrationCalculator"]:
        """Build InternalMigrationCalculator instances active for the given year"""
        calculators = []
        for config in rate_configs:
            if not self._is_active(config, year):
                continue
            filters = self._parse_filters(config.get("filters", {}))
            destination = Location[config["destination"]]
            calc = InternalMigrationCalculator(
                self.db_session,
                rate=self._jittered_rate(config["rate"]),
                destination=destination,
                query_filters=filters,
            )
            calculators.append(calc)
        return calculators

    def _parse_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Parse string filter values to enum types"""
        parsed = {}
        enum_map = {
            "religious_background": ReligiousBackground,
            "gender": Gender,
            "location": Location,
            "education_level": EducationLevel,
            "origin": Origin,
        }

        for key, value in filters.items():
            if key in enum_map:
                parsed[key] = enum_map[key][value]
            else:
                parsed[key] = value

        return parsed

    def simulate_births(self, year: int) -> int:
        """Execute birth calculators active for year and return total births"""
        calcs = self._build_calculators(
            self.config.get("birth_rates", []), BirthCalculator, year
        )
        return sum(c.calculate() for c in calcs)

    def simulate_deaths(self, year: int) -> int:
        """Execute death calculators active for year and return total deaths"""
        calcs = self._build_calculators(
            self.config.get("death_rates", []), DeathCalculator, year
        )
        return sum(c.calculate() for c in calcs)

    def simulate_migration(self, year: int) -> int:
        """Execute migration calculators active for year and return net migration"""
        calcs = self._build_calculators(
            self.config.get("migration_rates", []), MigrationCalculator, year
        )
        return sum(c.calculate() for c in calcs)

    def simulate_internal_migration(self, year: int) -> int:
        """Execute internal migration calculators active for year"""
        calcs = self._build_internal_migration_calculators(
            self.config.get("internal_migration_rates", []), year
        )
        return sum(c.calculate() for c in calcs)

    @classmethod
    def from_yaml(cls, db_session: Session, yaml_path: str) -> "ModelDirector":
        """Create ModelDirector from YAML configuration file"""
        with open(yaml_path, "r") as f:
            config = yaml.safe_load(f)
        return cls(db_session, config)
