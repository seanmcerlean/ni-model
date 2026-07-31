from sqlalchemy import event, func

from src.ni_model.api.queries import (
    age_band_breakdown,
    gender_breakdown,
    location_totals,
    origin_breakdown,
    religious_breakdown,
    snapshot_aggregates,
)
from src.ni_model.core.models import Location, Person
from src.ni_model.simulation.voting_predictor import CALIBRATIONS, VotingPredictor


def test_snapshot_aggregates_match_legacy_queries(populated_db):
    aggregates = snapshot_aggregates(populated_db)

    assert aggregates.total == populated_db.query(func.count(Person.id)).scalar()
    assert aggregates.religious_breakdown == religious_breakdown(populated_db)
    assert aggregates.gender_breakdown == gender_breakdown(populated_db)
    assert {
        key: item.total for key, item in aggregates.locations.items() if item.total
    } == {location.value: count for location, count in location_totals(populated_db)}
    for location in Location:
        detail = aggregates.locations[location.value]
        assert detail.religious_breakdown == religious_breakdown(populated_db, location)
        assert detail.gender_breakdown == gender_breakdown(populated_db, location)
        assert detail.origin_breakdown == origin_breakdown(populated_db, location)
        assert detail.age_bands == age_band_breakdown(populated_db, location)


def test_snapshot_and_polling_inputs_require_two_selects(populated_db):
    selects = 0

    def count_selects(_conn, _cursor, statement, _parameters, _context, _many):
        nonlocal selects
        if statement.lstrip().upper().startswith("SELECT"):
            selects += 1

    event.listen(populated_db.bind, "before_cursor_execute", count_selects)
    try:
        aggregates = snapshot_aggregates(populated_db)
        rows = VotingPredictor.aggregate_population(populated_db)
        for calibration in CALIBRATIONS:
            predictor = VotingPredictor(
                populated_db,
                calibration=calibration,
                aggregate_rows=rows,
                total_population=aggregates.total,
            )
            predictor.predict()
            predictor.predict_by_location()
    finally:
        event.remove(populated_db.bind, "before_cursor_execute", count_selects)

    assert selects == 2


def test_shared_polling_rows_match_direct_predictions(populated_db):
    total = populated_db.query(func.count(Person.id)).scalar()
    rows = VotingPredictor.aggregate_population(populated_db)

    for calibration in CALIBRATIONS:
        direct = VotingPredictor(populated_db, calibration=calibration)
        shared = VotingPredictor(
            populated_db,
            calibration=calibration,
            aggregate_rows=rows,
            total_population=total,
        )
        assert shared.predict() == direct.predict()
        assert shared.predict_by_location() == direct.predict_by_location()
