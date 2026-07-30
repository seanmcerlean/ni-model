import json
import os
from typing import AsyncGenerator, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...simulation.model_director import ModelDirector
from ...simulation.orchestrator import SimulationOrchestrator
from ..queries import gender_breakdown, location_totals, religious_breakdown
from ..routes.population import get_db
from ..schemas import (
    SimulationRunRequest,
    SimulationRunResponse,
    SimulationYearResult,
    SimulationYearsList,
    SimulationYearSnapshot,
)

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

# In-memory store for completed simulation results, keyed by year.
# Populated by the orchestrator via store_results().
_year_snapshots: dict[int, SimulationYearSnapshot] = {}
_year_results: dict[int, SimulationYearResult] = {}


def store_results(
    results: List[dict], db, snapshots: dict[int, SimulationYearSnapshot]
):
    """Store simulation results and snapshots — called by orchestrator after run()"""
    _year_results.clear()
    _year_snapshots.clear()
    _year_results.update({r["year"]: SimulationYearResult(**r) for r in results})
    _year_snapshots.update(snapshots)


def _capture_snapshot(year: int, result: dict, db: Session) -> SimulationYearSnapshot:
    loc_breakdown = {loc.value: count for loc, count in location_totals(db)}
    return SimulationYearSnapshot(
        year=year,
        total_population=sum(loc_breakdown.values()),
        religious_breakdown=religious_breakdown(db),
        gender_breakdown=gender_breakdown(db),
        location_breakdown=loc_breakdown,
        simulation_result=SimulationYearResult(**result),
    )


@router.get("/years", response_model=SimulationYearsList)
def simulation_years():
    return SimulationYearsList(years=sorted(_year_snapshots.keys()))


@router.get("/years/{year}", response_model=SimulationYearSnapshot)
def simulation_year_snapshot(year: int):
    snapshot = _year_snapshots.get(year)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot for year {year}")
    return snapshot


@router.get("/stream")
def stream_simulation(
    start_year: int = 2024,
    end_year: int = 2030,
    model_path: str = "models/ni_base_2024.yaml",
    db: Session = Depends(get_db),
):
    if not os.path.exists(model_path):
        raise HTTPException(
            status_code=422, detail=f"Model file not found: {model_path}"
        )
    if not (1900 <= start_year <= 2200) or not (1900 <= end_year <= 2200):
        raise HTTPException(
            status_code=422, detail="year must be between 1900 and 2200"
        )
    if end_year < start_year:
        raise HTTPException(status_code=422, detail="end_year must be >= start_year")

    director = ModelDirector.from_yaml(db, model_path)
    orchestrator = SimulationOrchestrator(db, director)

    async def event_stream() -> AsyncGenerator[str, None]:
        for result in orchestrator._iter_years(start_year, end_year):
            snapshot = _capture_snapshot(result["year"], result, db)
            payload = snapshot.model_dump()
            yield f"data: {json.dumps(payload)}\n\n"
        yield "event: complete\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/run", response_model=SimulationRunResponse)
def run_simulation(request: SimulationRunRequest, db: Session = Depends(get_db)):
    if not os.path.exists(request.model_path):
        raise HTTPException(
            status_code=422, detail=f"Model file not found: {request.model_path}"
        )

    director = ModelDirector.from_yaml(db, request.model_path)
    orchestrator = SimulationOrchestrator(db, director)

    results = orchestrator.run(request.start_year, request.end_year)
    snapshots = {r["year"]: _capture_snapshot(r["year"], r, db) for r in results}
    store_results(results, db, snapshots)

    return SimulationRunResponse(
        model_path=request.model_path,
        start_year=request.start_year,
        end_year=request.end_year,
        years_simulated=len(results),
        results=[SimulationYearResult(**r) for r in results],
    )
