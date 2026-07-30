import uuid
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..core.models import Person


class PersonRepository:
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def create(self, person: Person) -> Person:
        """Create a new person record"""
        self.db.add(person)
        self.db.commit()
        self.db.refresh(person)
        return person

    def get_by_id(self, person_id: uuid.UUID) -> Optional[Person]:
        """Get person by ID"""
        return self.db.query(Person).filter(Person.id == person_id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[Person]:
        """Get all persons with pagination"""
        return self.db.query(Person).offset(skip).limit(limit).all()

    def update(self, person_id: uuid.UUID, **kwargs) -> Optional[Person]:
        """Update person record"""
        person = self.get_by_id(person_id)
        if person:
            for key, value in kwargs.items():
                if hasattr(person, key):
                    setattr(person, key, value)
            self.db.commit()
            self.db.refresh(person)
        return person

    def delete(self, person_id: uuid.UUID) -> bool:
        """Delete person record"""
        person = self.get_by_id(person_id)
        if person:
            self.db.delete(person)
            self.db.commit()
            return True
        return False

    def bulk_create(self, persons: List[Person]) -> List[Person]:
        """Bulk create person records"""
        self.db.add_all(persons)
        self.db.commit()
        return persons

    def count(self) -> int:
        """Get total count of persons"""
        return self.db.query(Person).count()

    def get_by_location(self, location: str) -> List[Person]:
        """Get persons by location"""
        return self.db.query(Person).filter(Person.location == location).all()

    def get_by_age_range(self, min_age: int, max_age: int) -> List[Person]:
        """Get persons by age range"""
        return (
            self.db.query(Person)
            .filter(Person.age >= min_age, Person.age <= max_age)
            .all()
        )

    def get_demographics_summary(self) -> dict:
        """Get demographic summary statistics"""
        total = self.count()

        age_stats = self.db.query(
            func.avg(Person.age).label("avg_age"),
            func.min(Person.age).label("min_age"),
            func.max(Person.age).label("max_age"),
        ).first()

        religious_breakdown = (
            self.db.query(
                Person.religious_background, func.count(Person.id).label("count")
            )
            .group_by(Person.religious_background)
            .all()
        )

        gender_breakdown = (
            self.db.query(Person.gender, func.count(Person.id).label("count"))
            .group_by(Person.gender)
            .all()
        )

        return {
            "total_population": total,
            "age_stats": {
                "average": float(age_stats.avg_age) if age_stats.avg_age else 0,
                "minimum": age_stats.min_age,
                "maximum": age_stats.max_age,
            },
            "religious_breakdown": {
                rb.religious_background.value: rb.count for rb in religious_breakdown
            },
            "gender_breakdown": {gb.gender.value: gb.count for gb in gender_breakdown},
        }

    def close(self):
        """Close database session"""
        self.db.close()
