import uuid
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.models import Location, Person

AGE_BANDS = {
    "0-17": (0, 17),
    "18-35": (18, 35),
    "36-50": (36, 50),
    "51-70": (51, 70),
    "71+": (71, 150),
}


def _population_query(db: Session, *entities, run_id: uuid.UUID = None):
    return db.query(*entities).filter(Person.run_id == run_id)


def religious_breakdown(
    db: Session, location: Location = None, run_id: uuid.UUID = None
) -> Dict[str, int]:
    query = _population_query(
        db, Person.religious_background, func.count(Person.id), run_id=run_id
    )
    if location:
        query = query.filter(Person.location == location)
    return {
        rb.value: count for rb, count in query.group_by(Person.religious_background)
    }


def gender_breakdown(
    db: Session, location: Location = None, run_id: uuid.UUID = None
) -> Dict[str, int]:
    query = _population_query(db, Person.gender, func.count(Person.id), run_id=run_id)
    if location:
        query = query.filter(Person.location == location)
    return {g.value: count for g, count in query.group_by(Person.gender)}


def origin_breakdown(
    db: Session, location: Location = None, run_id: uuid.UUID = None
) -> Dict[str, int]:
    query = _population_query(db, Person.origin, func.count(Person.id), run_id=run_id)
    if location:
        query = query.filter(Person.location == location)
    return {o.value: count for o, count in query.group_by(Person.origin)}


def age_band_breakdown(
    db: Session, location: Location = None, run_id: uuid.UUID = None
) -> Dict[str, int]:
    result = {}
    for label, (min_age, max_age) in AGE_BANDS.items():
        query = _population_query(db, func.count(Person.id), run_id=run_id).filter(
            Person.age >= min_age, Person.age <= max_age
        )
        if location:
            query = query.filter(Person.location == location)
        result[label] = query.scalar() or 0
    return result


def location_totals(db: Session, run_id: uuid.UUID = None) -> List[Dict]:
    rows = (
        _population_query(db, Person.location, func.count(Person.id), run_id=run_id)
        .group_by(Person.location)
        .all()
    )
    return [(loc, count) for loc, count in rows]
