import random
import uuid
from abc import ABC, abstractmethod
from heapq import nlargest
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)
from .sampling import stochastic_round


class DemographicCalculator(ABC):
    """Base class for demographic calculations on population cohorts"""

    def __init__(
        self,
        db_session: Session,
        rate: float,
        query_filters: Optional[Dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
        run_id: Optional[uuid.UUID] = None,
        child_background_probabilities: Optional[
            Dict[ReligiousBackground, List[tuple[ReligiousBackground, float]]]
        ] = None,
    ):
        self.db_session = db_session
        self.rate = rate
        self.query_filters = query_filters or {}
        self.rng = rng or random.Random()
        self.run_id = run_id
        self.child_background_probabilities = child_background_probabilities or {}

    def _get_cohort(self) -> List[Person]:
        """Get population cohort matching query filters"""
        query = self.db_session.query(Person).filter(Person.run_id == self.run_id)

        filter_map = {
            "religious_background": Person.religious_background,
            "gender": Person.gender,
            "location": Person.location,
            "education_level": Person.education_level,
            "origin": Person.origin,
        }

        for key, column in filter_map.items():
            if key in self.query_filters:
                query = query.filter(column == self.query_filters[key])

        if "age_min" in self.query_filters:
            query = query.filter(Person.age >= self.query_filters["age_min"])
        if "age_max" in self.query_filters:
            query = query.filter(Person.age <= self.query_filters["age_max"])

        return query.all()

    @abstractmethod
    def calculate(self) -> int:
        """Calculate demographic change and return count"""
        pass


class BirthCalculator(DemographicCalculator):
    """Calculate and apply births to population cohort"""

    def calculate(self) -> int:
        """Calculate births based on rate for cohort"""
        cohort = self._get_cohort()
        num_births = int((self.rate / 1000.0) * len(cohort))
        potential_mothers = [
            person
            for person in cohort
            if person.gender == Gender.FEMALE and 15 <= person.age <= 49
        ]

        if num_births > 0 and potential_mothers:
            self.db_session.add_all(
                self._generate_births(num_births, potential_mothers)
            )
        elif not potential_mothers:
            num_births = 0

        return num_births

    def _generate_births(self, count: int, parents: List[Person]) -> List[Person]:
        """Generate births inheriting parent cohort characteristics"""
        if not parents:
            return []

        return [
            Person(
                run_id=self.run_id,
                age=0,
                religious_background=self._child_background(parent),
                gender=self.rng.choice([Gender.MALE, Gender.FEMALE]),
                education_level=EducationLevel.PRE_PRIMARY,
                location=parent.location,
                origin=Origin.NI,
            )
            for parent in self.rng.choices(parents, k=count)
        ]

    def _child_background(self, parent: Person) -> ReligiousBackground:
        choices = self.child_background_probabilities.get(parent.religious_background)
        if not choices:
            return parent.religious_background
        backgrounds, weights = zip(*choices)
        return self.rng.choices(backgrounds, weights=weights, k=1)[0]


class DeathCalculator(DemographicCalculator):
    """Calculate and apply deaths to population cohort"""

    def calculate(self) -> int:
        """Calculate deaths based on rate for cohort"""
        cohort = self._get_cohort()
        num_deaths = min(int((self.rate / 1000.0) * len(cohort)), len(cohort))

        if num_deaths > 0:
            for person in self.rng.sample(cohort, num_deaths):
                self.db_session.delete(person)

        return num_deaths


class AgeWeightedDeathCalculator(DeathCalculator):
    """Apply a cohort's crude death rate using age-specific relative risks."""

    def __init__(
        self, *args, age_rates: Optional[List[Dict[str, Any]]] = None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.age_rates = age_rates or []

    def _age_rate(self, age: int) -> float:
        for band in self.age_rates:
            if band["age_min"] <= age <= band["age_max"]:
                return band["rate"]
        return 0.0

    def calculate(self) -> int:
        cohort = self._get_cohort()
        num_deaths = min(int((self.rate / 1000.0) * len(cohort)), len(cohort))
        if num_deaths <= 0:
            return 0
        weighted = [(person, self._age_rate(person.age)) for person in cohort]
        eligible = [(person, weight) for person, weight in weighted if weight > 0]
        num_deaths = min(num_deaths, len(eligible))
        selected = nlargest(
            num_deaths,
            eligible,
            key=lambda item: self.rng.random() ** (1.0 / item[1]),
        )
        for person, _weight in selected:
            self.db_session.delete(person)
        return num_deaths


class MigrationCalculator(DemographicCalculator):
    """Calculate and apply migration to population cohort"""

    def calculate(self) -> int:
        """Calculate net migration based on rate for cohort"""
        cohort = self._get_cohort()
        net_migration = int((self.rate / 1000.0) * len(cohort))

        if net_migration > 0:
            self.db_session.add_all(self._generate_immigrants(net_migration, cohort))
        elif net_migration < 0:
            num_emigrants = min(abs(net_migration), len(cohort))
            for person in self.rng.sample(cohort, num_emigrants):
                self.db_session.delete(person)
            net_migration = -num_emigrants

        return net_migration

    def _generate_immigrants(self, count: int, cohort: List[Person]) -> List[Person]:
        """Generate immigrants sampling cohort characteristics per arrival."""
        immigrants = []
        for _ in range(count):
            template = self.rng.choice(cohort) if cohort else None
            immigrants.append(
                Person(
                    run_id=self.run_id,
                    age=self.rng.randint(18, 45),
                    religious_background=(
                        template.religious_background
                        if template
                        else self.rng.choice(list(ReligiousBackground))
                    ),
                    gender=self.rng.choice([Gender.MALE, Gender.FEMALE]),
                    education_level=self.rng.choice(list(EducationLevel)),
                    location=template.location if template else Location.BELFAST,
                    origin=Origin.OTHER,
                )
            )
        return immigrants


class InternalMigrationCalculator(DemographicCalculator):
    """Relocate persons within NI from source cohort to destination location"""

    def __init__(
        self,
        db_session: Session,
        rate: float,
        destination: Location,
        query_filters: Optional[Dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
        run_id: Optional[uuid.UUID] = None,
    ):
        super().__init__(db_session, rate, query_filters, rng, run_id)
        self.destination = destination

    def calculate(self) -> int:
        """Move cohort members to destination location, return count moved"""
        movers = self.select_movers()
        self.apply_movers(movers)
        return len(movers)

    def select_movers(self, excluded_ids=None, cohort=None) -> List[Person]:
        """Select movers without mutating them, enabling simultaneous flows."""
        excluded_ids = excluded_ids or set()
        full_cohort = self._get_cohort() if cohort is None else cohort
        available = [person for person in full_cohort if person.id not in excluded_ids]
        expected = (self.rate / 1000.0) * len(full_cohort)
        num_movers = min(stochastic_round(expected, self.rng.random()), len(available))
        return self.rng.sample(available, num_movers) if num_movers > 0 else []

    def apply_movers(self, movers: List[Person]) -> None:
        for person in movers:
            person.location = self.destination


class CommunityTransitionCalculator(DemographicCalculator):
    """Select people whose modelled community identification changes."""

    def __init__(
        self,
        db_session: Session,
        rate: float,
        destination: ReligiousBackground,
        query_filters: Optional[Dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
        run_id: Optional[uuid.UUID] = None,
    ):
        super().__init__(db_session, rate, query_filters, rng, run_id)
        self.destination = destination

    def calculate(self) -> int:
        transitions = self.select_people()
        self.apply_transitions(transitions)
        return len(transitions)

    def select_people(self, excluded_ids=None, cohort=None) -> List[Person]:
        """Select transitions before mutation so competing flows are simultaneous."""
        excluded_ids = excluded_ids or set()
        full_cohort = self._get_cohort() if cohort is None else cohort
        available = [person for person in full_cohort if person.id not in excluded_ids]
        probability = min(self.rate / 1000.0, 1.0)
        count = min(
            sum(self.rng.random() < probability for _ in full_cohort),
            len(available),
        )
        return self.rng.sample(available, count) if count > 0 else []

    def apply_transitions(self, people: List[Person]) -> None:
        for person in people:
            person.religious_background = self.destination
