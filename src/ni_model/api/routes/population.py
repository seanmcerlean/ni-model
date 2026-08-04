import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...core.database import SessionLocal
from ...core.models import Location, Person
from ...simulation.voting_predictor import VotingPredictor
from ..queries import (
    age_band_breakdown,
    gender_breakdown,
    location_totals,
    origin_breakdown,
    probable_community_breakdown,
    religious_breakdown,
)
from ..schemas import (
    LocationDetail,
    LocationSummary,
    PopulationSummary,
    VotingPrediction,
)

router = APIRouter(prefix="/api/population", tags=["population"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/summary", response_model=PopulationSummary)
def population_summary(db: Session = Depends(get_db)):
    baseline = db.query(Person).filter(
        Person.run_id.is_(None), Person.baseline_profile == "current"
    )
    total = baseline.count()
    age_stats = baseline.with_entities(
        func.avg(Person.age),
        func.min(Person.age),
        func.max(Person.age),
    ).first()

    return PopulationSummary(
        total_population=total,
        age_stats={
            "average": float(age_stats[0]) if age_stats[0] else 0.0,
            "minimum": age_stats[1] or 0,
            "maximum": age_stats[2] or 0,
        },
        religious_breakdown=religious_breakdown(db),
        probable_community_breakdown=probable_community_breakdown(db),
        gender_breakdown=gender_breakdown(db),
    )


@router.get("/by-location", response_model=list[LocationSummary])
def population_by_location(db: Session = Depends(get_db)):
    return [
        LocationSummary(
            location=loc.value,
            total=count,
            religious_breakdown=religious_breakdown(db, loc),
            probable_community_breakdown=probable_community_breakdown(db, loc),
        )
        for loc, count in location_totals(db)
    ]


@router.get("/location/{location_name}", response_model=LocationDetail)
def population_location_detail(location_name: str, db: Session = Depends(get_db)):
    try:
        location = Location[location_name.upper()]
    except KeyError:
        location = next(
            (item for item in Location if item.value == location_name.lower()), None
        )
    if location is None:
        raise HTTPException(
            status_code=404, detail=f"Location '{location_name}' not found"
        )

    total = (
        db.query(Person)
        .filter(
            Person.run_id.is_(None),
            Person.baseline_profile == "current",
            Person.location == location,
        )
        .count()
    )

    return LocationDetail(
        location=location.value,
        total=total,
        religious_breakdown=religious_breakdown(db, location),
        probable_community_breakdown=probable_community_breakdown(db, location),
        gender_breakdown=gender_breakdown(db, location),
        origin_breakdown=origin_breakdown(db, location),
        age_bands=age_band_breakdown(db, location),
    )


@router.get("/voting-prediction", response_model=VotingPrediction)
def voting_prediction(
    run_id: Optional[UUID] = None,
    calibration: str = "lucidtalk_winter_2025",
    include_locations: bool = True,
    community_basis: str = "reported",
    custom_unite: Optional[float] = Query(None, ge=0, le=100),
    custom_remain: Optional[float] = Query(None, ge=0, le=100),
    custom_undecided: Optional[float] = Query(None, ge=0, le=100),
    db: Session = Depends(get_db),
):
    try:
        custom_values = (custom_unite, custom_remain, custom_undecided)
        custom_baseline = None
        if any(value is not None for value in custom_values):
            if any(value is None for value in custom_values):
                raise ValueError("all custom baseline values are required")
            if not math.isclose(sum(custom_values), 100.0, abs_tol=0.01):
                raise ValueError("custom baseline values must sum to 100")
            custom_baseline = tuple(value / 100 for value in custom_values)
        predictor = VotingPredictor(
            db,
            run_id=run_id,
            calibration=calibration,
            custom_baseline=custom_baseline,
            custom_reference_rows=VotingPredictor.aggregate_population(db),
            community_basis=community_basis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = predictor.predict()
    by_location = predictor.predict_by_location() if include_locations else {}
    return VotingPrediction(**result, by_location=by_location)
