from fastapi import APIRouter, Depends, HTTPException
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
    total = db.query(Person).count()
    age_stats = db.query(
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
        gender_breakdown=gender_breakdown(db),
    )


@router.get("/by-location", response_model=list[LocationSummary])
def population_by_location(db: Session = Depends(get_db)):
    return [
        LocationSummary(
            location=loc.value,
            total=count,
            religious_breakdown=religious_breakdown(db, loc),
        )
        for loc, count in location_totals(db)
    ]


@router.get("/location/{location_name}", response_model=LocationDetail)
def population_location_detail(location_name: str, db: Session = Depends(get_db)):
    try:
        location = Location[location_name.upper()]
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Location '{location_name}' not found"
        )

    total = db.query(Person).filter(Person.location == location).count()

    return LocationDetail(
        location=location.value,
        total=total,
        religious_breakdown=religious_breakdown(db, location),
        gender_breakdown=gender_breakdown(db, location),
        origin_breakdown=origin_breakdown(db, location),
        age_bands=age_band_breakdown(db, location),
    )


@router.get("/voting-prediction", response_model=VotingPrediction)
def voting_prediction(db: Session = Depends(get_db)):
    predictor = VotingPredictor(db)
    result = predictor.predict()
    by_location = predictor.predict_by_location()
    return VotingPrediction(**result, by_location=by_location)
