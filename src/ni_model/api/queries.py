import uuid
from dataclasses import dataclass
from typing import Dict, List

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..core.models import Location, Person

AGE_BANDS = {
    "0-17": (0, 17),
    "18-35": (18, 35),
    "36-50": (36, 50),
    "51-70": (51, 70),
    "71+": (71, 150),
}


@dataclass(frozen=True)
class LocationAggregates:
    total: int
    religious_breakdown: Dict[str, int]
    gender_breakdown: Dict[str, int]
    origin_breakdown: Dict[str, int]
    age_bands: Dict[str, int]


@dataclass(frozen=True)
class PopulationAggregates:
    total: int
    religious_breakdown: Dict[str, int]
    gender_breakdown: Dict[str, int]
    locations: Dict[str, LocationAggregates]


def snapshot_aggregates(db: Session, run_id: uuid.UUID = None) -> PopulationAggregates:
    """Build all demographic snapshot fields from one grouped population scan."""
    age_band = case(
        (Person.age <= 17, "0-17"),
        (Person.age <= 35, "18-35"),
        (Person.age <= 50, "36-50"),
        (Person.age <= 70, "51-70"),
        else_="71+",
    ).label("age_band")
    rows = (
        _population_query(
            db,
            Person.location,
            Person.religious_background,
            Person.gender,
            Person.origin,
            age_band,
            func.count(Person.id).label("count"),
            run_id=run_id,
        )
        .group_by(
            Person.location,
            Person.religious_background,
            Person.gender,
            Person.origin,
            age_band,
        )
        .all()
    )

    religious: Dict[str, int] = {}
    genders: Dict[str, int] = {}
    mutable_locations = {
        location.value: {
            "total": 0,
            "religious_breakdown": {},
            "gender_breakdown": {},
            "origin_breakdown": {},
            "age_bands": {label: 0 for label in AGE_BANDS},
        }
        for location in Location
    }
    total = 0
    for row in rows:
        count = row.count
        location = mutable_locations[row.location.value]
        total += count
        religious_key = row.religious_background.value
        gender_key = row.gender.value
        origin_key = row.origin.value
        religious[religious_key] = religious.get(religious_key, 0) + count
        genders[gender_key] = genders.get(gender_key, 0) + count
        location["total"] += count
        location["religious_breakdown"][religious_key] = (
            location["religious_breakdown"].get(religious_key, 0) + count
        )
        location["gender_breakdown"][gender_key] = (
            location["gender_breakdown"].get(gender_key, 0) + count
        )
        location["origin_breakdown"][origin_key] = (
            location["origin_breakdown"].get(origin_key, 0) + count
        )
        location["age_bands"][row.age_band] += count

    return PopulationAggregates(
        total=total,
        religious_breakdown=religious,
        gender_breakdown=genders,
        locations={
            key: LocationAggregates(**values)
            for key, values in mutable_locations.items()
        },
    )


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
