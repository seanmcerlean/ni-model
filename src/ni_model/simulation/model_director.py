import random
from math import isfinite
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

    RATE_SECTIONS = (
        "birth_rates",
        "death_rates",
        "migration_rates",
        "internal_migration_rates",
    )

    def __init__(self, db_session: Session, config: Dict[str, Any]):
        if not isinstance(config, dict):
            raise ValueError("model configuration must be a mapping")
        self.db_session = db_session
        self.config = config
        self.jitter = config.get("rate_jitter", 0.05)
        self.seed = config.get("random_seed", 42)
        self.rng = random.Random(self.seed)
        self._validate_config()

    def _jittered_rate(self, rate: float) -> float:
        """Apply uniform random jitter of ±jitter% to rate"""
        return rate * self.rng.uniform(1 - self.jitter, 1 + self.jitter)

    def _validate_config(self) -> None:
        """Fail fast for invalid or ambiguous model configuration."""
        if (
            isinstance(self.jitter, bool)
            or not isinstance(self.jitter, (int, float))
            or not isfinite(self.jitter)
            or not 0 <= self.jitter <= 1
        ):
            raise ValueError("rate_jitter must be between 0 and 1")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("random_seed must be an integer")

        valid_filters = {
            "religious_background",
            "gender",
            "location",
            "education_level",
            "origin",
            "age_min",
            "age_max",
        }
        for section in self.RATE_SECTIONS:
            rates = self.config.get(section, [])
            if not isinstance(rates, list):
                raise ValueError(f"{section} must be a list")
            for index, item in enumerate(rates):
                label = f"{section}[{index}]"
                if not isinstance(item, dict) or "rate" not in item:
                    raise ValueError(f"{label} must contain a rate")
                rate = item["rate"]
                if (
                    isinstance(rate, bool)
                    or not isinstance(rate, (int, float))
                    or not isfinite(rate)
                ):
                    raise ValueError(f"{label}.rate must be numeric")
                if section != "migration_rates" and rate < 0:
                    raise ValueError(f"{label}.rate must be non-negative")
                year_min = item.get("year_min", 0)
                year_max = item.get("year_max", 9999)
                if not isinstance(year_min, int) or not isinstance(year_max, int):
                    raise ValueError(f"{label} year bounds must be integers")
                if year_min > year_max:
                    raise ValueError(f"{label} has year_min after year_max")
                filters = item.get("filters", {})
                if not isinstance(filters, dict):
                    raise ValueError(f"{label}.filters must be a mapping")
                unknown = set(filters) - valid_filters
                if unknown:
                    raise ValueError(
                        f"{label} has unsupported filters: {sorted(unknown)}"
                    )
                age_min = filters.get("age_min", 0)
                age_max = filters.get("age_max", 999)
                if not isinstance(age_min, int) or not isinstance(age_max, int):
                    raise ValueError(f"{label} age bounds must be integers")
                if age_min < 0 or age_min > age_max:
                    raise ValueError(f"{label} has age_min after age_max")
                # Parse now so invalid enum names fail during model loading.
                self._parse_filters(filters)
                if section == "internal_migration_rates":
                    if "destination" not in item:
                        raise ValueError(f"{label} must contain a destination")
                    try:
                        Location[item["destination"]]
                    except (KeyError, TypeError) as exc:
                        raise ValueError(f"{label} has invalid destination") from exc

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
                rng=self.rng,
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
                rng=self.rng,
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
                try:
                    parsed[key] = enum_map[key][value]
                except (KeyError, TypeError) as exc:
                    raise ValueError(f"invalid {key} value: {value!r}") from exc
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
        with open(yaml_path, "r", encoding="utf-8") as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                raise ValueError(f"invalid YAML: {exc}") from exc
        return cls(db_session, config)
