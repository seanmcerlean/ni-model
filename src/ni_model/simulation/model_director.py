import random
import uuid
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
    AgeWeightedDeathCalculator,
    BirthCalculator,
    CommunityTransitionCalculator,
    DeathCalculator,
    InternalMigrationCalculator,
    MigrationCalculator,
)
from .historical_configuration import configure_historical_model_from_file


class ModelDirector:
    """Orchestrates multiple demographic calculators from configuration"""

    RATE_SECTIONS = (
        "birth_rates",
        "death_rates",
        "migration_rates",
        "internal_migration_rates",
        "integration_rates",
    )

    def __init__(
        self,
        db_session: Session,
        config: Dict[str, Any],
        run_id: uuid.UUID = None,
    ):
        if not isinstance(config, dict):
            raise ValueError("model configuration must be a mapping")
        self.db_session = db_session
        self.config = config
        self.jitter = config.get("rate_jitter", 0.05)
        self.seed = config.get("random_seed", 42)
        self.rng = random.Random(self.seed)
        self.run_id = run_id
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
                if section == "integration_rates" and rate > 1000:
                    raise ValueError(f"{label}.rate must not exceed 1000")
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
                if section == "integration_rates":
                    if "destination" not in item:
                        raise ValueError(f"{label} must contain a destination")
                    try:
                        destination = ReligiousBackground[item["destination"]]
                    except (KeyError, TypeError) as exc:
                        raise ValueError(f"{label} has invalid destination") from exc
                    source_name = filters.get("religious_background")
                    if source_name is None:
                        raise ValueError(f"{label} must filter by religious_background")
                    source = ReligiousBackground[source_name]
                    if source == destination:
                        raise ValueError(f"{label} source and destination must differ")
        self._validate_mortality_age_rates()
        self._validate_child_background_rules()

    def _validate_child_background_rules(self) -> None:
        rules = self.config.get("child_background_rules", [])
        if not isinstance(rules, list):
            raise ValueError("child_background_rules must be a list")
        ranges: Dict[str, List[tuple[int, int]]] = {}
        for index, rule in enumerate(rules):
            label = f"child_background_rules[{index}]"
            if not isinstance(rule, dict):
                raise ValueError(f"{label} must be a mapping")
            try:
                source = ReligiousBackground[rule["source"]]
            except (KeyError, TypeError) as exc:
                raise ValueError(f"{label} has invalid source") from exc
            probabilities = rule.get("probabilities")
            if not isinstance(probabilities, dict) or not probabilities:
                raise ValueError(f"{label}.probabilities must be a mapping")
            try:
                parsed = {
                    ReligiousBackground[key]: value
                    for key, value in probabilities.items()
                }
            except (KeyError, TypeError) as exc:
                raise ValueError(f"{label} has invalid destination") from exc
            if (
                any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                    or value < 0
                    for value in parsed.values()
                )
                or abs(sum(parsed.values()) - 1.0) > 1e-6
            ):
                raise ValueError(f"{label}.probabilities must sum to 1")
            year_min = rule.get("year_min", 0)
            year_max = rule.get("year_max", 9999)
            if not isinstance(year_min, int) or not isinstance(year_max, int):
                raise ValueError(f"{label} year bounds must be integers")
            if year_min > year_max:
                raise ValueError(f"{label} has year_min after year_max")
            for prior_min, prior_max in ranges.setdefault(source.name, []):
                if year_min <= prior_max and year_max >= prior_min:
                    raise ValueError(f"{label} overlaps another source rule")
            ranges[source.name].append((year_min, year_max))

    def _child_background_probabilities(
        self, year: int
    ) -> Dict[ReligiousBackground, List[tuple[ReligiousBackground, float]]]:
        probabilities = {}
        for rule in self.config.get("child_background_rules", []):
            if not self._is_active(rule, year):
                continue
            probabilities[ReligiousBackground[rule["source"]]] = [
                (ReligiousBackground[destination], probability)
                for destination, probability in rule["probabilities"].items()
            ]
        return probabilities

    def _validate_mortality_age_rates(self) -> None:
        profile = self.config.get("mortality_age_rates")
        if profile is None:
            return
        if not isinstance(profile, list) or not profile:
            raise ValueError("mortality_age_rates must be a non-empty list")
        expected_min = 0
        for index, band in enumerate(profile):
            label = f"mortality_age_rates[{index}]"
            if not isinstance(band, dict):
                raise ValueError(f"{label} must be a mapping")
            age_min = band.get("age_min")
            age_max = band.get("age_max")
            rate = band.get("rate")
            if age_min != expected_min or not isinstance(age_max, int):
                raise ValueError("mortality_age_rates must be contiguous from age 0")
            if age_max < age_min:
                raise ValueError(f"{label} has age_min after age_max")
            if (
                isinstance(rate, bool)
                or not isinstance(rate, (int, float))
                or rate <= 0
            ):
                raise ValueError(f"{label}.rate must be positive")
            expected_min = age_max + 1
        if profile[-1]["age_max"] < 120:
            raise ValueError("mortality_age_rates must cover age 120")

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
                run_id=self.run_id,
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
                run_id=self.run_id,
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
        child_probabilities = self._child_background_probabilities(year)
        for calc in calcs:
            calc.child_background_probabilities = child_probabilities
        return sum(c.calculate() for c in calcs)

    def simulate_deaths(self, year: int) -> int:
        """Execute death calculators active for year and return total deaths"""
        calculator = (
            AgeWeightedDeathCalculator
            if self.config.get("mortality_age_rates")
            else DeathCalculator
        )
        calcs = self._build_calculators(
            self.config.get("death_rates", []), calculator, year
        )
        if calculator is AgeWeightedDeathCalculator:
            for calc in calcs:
                calc.age_rates = self.config["mortality_age_rates"]
        return sum(c.calculate() for c in calcs)

    def simulate_migration(self, year: int) -> int:
        """Execute migration calculators active for year and return net migration"""
        immigration, emigration = self.simulate_migration_components(year)
        return immigration - emigration

    def simulate_migration_components(self, year: int) -> tuple[int, int]:
        """Execute migration rules and return separate inflow and outflow counts."""
        calcs = self._build_calculators(
            self.config.get("migration_rates", []), MigrationCalculator, year
        )
        changes = [calculator.calculate() for calculator in calcs]
        immigration = sum(change for change in changes if change > 0)
        emigration = sum(abs(change) for change in changes if change < 0)
        return immigration, emigration

    def simulate_internal_migration(self, year: int) -> int:
        """Execute simultaneous internal flows without moving anyone twice."""
        calcs = self._build_internal_migration_calculators(
            self.config.get("internal_migration_rates", []), year
        )
        selected_ids = set()
        plans = []
        cohorts = {}
        for calculator in calcs:
            cohort_key = tuple(sorted(calculator.query_filters.items()))
            if cohort_key not in cohorts:
                cohorts[cohort_key] = calculator._get_cohort()
            cohort = cohorts[cohort_key]
            movers = calculator.select_movers(selected_ids, cohort=cohort)
            selected_ids.update(person.id for person in movers)
            plans.append((calculator, movers))
        for calculator, movers in plans:
            calculator.apply_movers(movers)
        return len(selected_ids)

    def simulate_integration(self, year: int) -> tuple[int, Dict[str, int]]:
        """Apply simultaneous community-identification transitions."""
        calculators = []
        for config in self.config.get("integration_rates", []):
            if not self._is_active(config, year):
                continue
            calculators.append(
                CommunityTransitionCalculator(
                    self.db_session,
                    rate=self._jittered_rate(config["rate"]),
                    destination=ReligiousBackground[config["destination"]],
                    query_filters=self._parse_filters(config.get("filters", {})),
                    rng=self.rng,
                    run_id=self.run_id,
                )
            )
        selected_ids = set()
        plans = []
        cohorts = {}
        for calculator in calculators:
            cohort_key = tuple(sorted(calculator.query_filters.items()))
            if cohort_key not in cohorts:
                cohorts[cohort_key] = calculator._get_cohort()
            people = calculator.select_people(selected_ids, cohort=cohorts[cohort_key])
            selected_ids.update(person.id for person in people)
            plans.append((calculator, people))
        breakdown = {}
        for calculator, people in plans:
            if not people:
                continue
            source = people[0].religious_background.value
            destination = calculator.destination.value
            key = f"{source}_to_{destination}"
            breakdown[key] = breakdown.get(key, 0) + len(people)
            calculator.apply_transitions(people)
        return len(selected_ids), breakdown

    @classmethod
    def from_yaml(
        cls,
        db_session: Session,
        yaml_path: str,
        run_id: uuid.UUID = None,
        adjustments: Dict[str, Any] = None,
    ) -> "ModelDirector":
        """Create ModelDirector from YAML configuration file"""
        with open(yaml_path, "r", encoding="utf-8") as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                raise ValueError(f"invalid YAML: {exc}") from exc
        config = configure_historical_model_from_file(config, yaml_path)
        adjustments = adjustments or {}
        section_multipliers = {
            "birth_rates": adjustments.get("birth_multiplier", 1.0),
            "death_rates": adjustments.get("death_multiplier", 1.0),
            "migration_rates": adjustments.get("migration_multiplier", 1.0),
            "internal_migration_rates": adjustments.get("relocation_multiplier", 1.0),
            "integration_rates": adjustments.get("integration_multiplier", 1.0),
        }
        community = adjustments.get("community") or {}
        section_fields = {
            "birth_rates": "birth_multiplier",
            "death_rates": "death_multiplier",
            "migration_rates": "migration_multiplier",
            "internal_migration_rates": "relocation_multiplier",
            "integration_rates": "integration_multiplier",
        }
        for section, multiplier in section_multipliers.items():
            rules = config.get(section, [])
            for rule in rules:
                rule["rate"] *= multiplier
            group_values = {
                group.upper(): values.get(section_fields[section], 1.0)
                for group, values in community.items()
            }
            if group_values:
                expanded = []
                for rule in rules:
                    existing_group = rule.get("filters", {}).get("religious_background")
                    if existing_group:
                        rule["rate"] *= group_values.get(existing_group, 1.0)
                        expanded.append(rule)
                    elif len(set(group_values.values())) == 1:
                        rule["rate"] *= next(iter(group_values.values()))
                        expanded.append(rule)
                    else:
                        for group, group_multiplier in group_values.items():
                            expanded.append(
                                {
                                    **rule,
                                    "rate": rule["rate"] * group_multiplier,
                                    "filters": {
                                        **rule.get("filters", {}),
                                        "religious_background": group,
                                    },
                                }
                            )
                config[section] = expanded
        if config.get("annual_demographic_components"):
            config["_component_target_multipliers"] = {
                "birth_rates": section_multipliers["birth_rates"],
                "death_rates": section_multipliers["death_rates"],
                "migration_rates": section_multipliers["migration_rates"],
            }
        if adjustments.get("random_seed") is not None:
            config["random_seed"] = adjustments["random_seed"]
        return cls(db_session, config, run_id=run_id)
