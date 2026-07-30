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


def religious_breakdown(db: Session, location: Location = None) -> Dict[str, int]:
    query = db.query(Person.religious_background, func.count(Person.id))
    if location:
        query = query.filter(Person.location == location)
    return {
        rb.value: count for rb, count in query.group_by(Person.religious_background)
    }


def gender_breakdown(db: Session, location: Location = None) -> Dict[str, int]:
    query = db.query(Person.gender, func.count(Person.id))
    if location:
        query = query.filter(Person.location == location)
    return {g.value: count for g, count in query.group_by(Person.gender)}


def origin_breakdown(db: Session, location: Location = None) -> Dict[str, int]:
    query = db.query(Person.origin, func.count(Person.id))
    if location:
        query = query.filter(Person.location == location)
    return {o.value: count for o, count in query.group_by(Person.origin)}


def age_band_breakdown(db: Session, location: Location = None) -> Dict[str, int]:
    result = {}
    for label, (min_age, max_age) in AGE_BANDS.items():
        query = db.query(func.count(Person.id)).filter(
            Person.age >= min_age, Person.age <= max_age
        )
        if location:
            query = query.filter(Person.location == location)
        result[label] = query.scalar() or 0
    return result


def location_totals(db: Session) -> List[Dict]:
    rows = (
        db.query(Person.location, func.count(Person.id)).group_by(Person.location).all()
    )
    return [(loc, count) for loc, count in rows]
