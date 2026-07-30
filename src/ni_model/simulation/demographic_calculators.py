import random
from abc import ABC, abstractmethod
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


class DemographicCalculator(ABC):
    """Base class for demographic calculations on population cohorts"""

    def __init__(
        self,
        db_session: Session,
        rate: float,
        query_filters: Optional[Dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
    ):
        self.db_session = db_session
        self.rate = rate
        self.query_filters = query_filters or {}
        self.rng = rng or random.Random()

    def _get_cohort(self) -> List[Person]:
        """Get population cohort matching query filters"""
        query = self.db_session.query(Person)

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
                age=0,
                religious_background=parent.religious_background,
                gender=self.rng.choice([Gender.MALE, Gender.FEMALE]),
                education_level=EducationLevel.PRE_PRIMARY,
                location=parent.location,
                origin=Origin.NI,
            )
            for parent in self.rng.choices(parents, k=count)
        ]


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
        """Generate immigrants matching cohort characteristics"""
        template = self.rng.choice(cohort) if cohort else None

        return [
            Person(
                age=self.rng.randint(18, 45),
                religious_background=(
                    template.religious_background
                    if template
                    else self.rng.choice(list(ReligiousBackground))
                ),
                gender=self.rng.choice([Gender.MALE, Gender.FEMALE]),
                education_level=self.rng.choice(list(EducationLevel)),
                location=template.location if template else Location.BELFAST_NORTH,
                origin=Origin.OTHER,
            )
            for _ in range(count)
        ]


class InternalMigrationCalculator(DemographicCalculator):
    """Relocate persons within NI from source cohort to destination location"""

    def __init__(
        self,
        db_session: Session,
        rate: float,
        destination: Location,
        query_filters: Optional[Dict[str, Any]] = None,
        rng: Optional[random.Random] = None,
    ):
        super().__init__(db_session, rate, query_filters, rng)
        self.destination = destination

    def calculate(self) -> int:
        """Move cohort members to destination location, return count moved"""
        cohort = self._get_cohort()
        num_movers = int((self.rate / 1000.0) * len(cohort))

        if num_movers > 0:
            for person in self.rng.sample(cohort, min(num_movers, len(cohort))):
                person.location = self.destination

        return num_movers
