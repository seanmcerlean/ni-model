import pytest

from src.ni_model.core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)
from src.ni_model.simulation.voting_predictor import VotingPredictor


def _make_person(db, religion, origin, age, location=Location.BELFAST):
    p = Person(
        age=age,
        religious_background=religion,
        gender=Gender.FEMALE,
        education_level=EducationLevel.TERTIARY,
        location=location,
        origin=origin,
    )
    db.add(p)
    db.flush()
    return p


def test_empty_population_returns_zeros(db_session):
    predictor = VotingPredictor(db_session)
    result = predictor.predict()
    assert result["total_population"] == 0
    assert result["unite"] == 0
    assert result["unite_share"] == 0.0
    assert result["eligible_population"] == 0


def test_all_catholic_ni_origin_high_unite(db_session):
    for _ in range(100):
        _make_person(db_session, ReligiousBackground.CATHOLIC, Origin.NI, 30)
    predictor = VotingPredictor(db_session)
    result = predictor.predict()
    assert result["unite_share"] > 0.60


def test_all_protestant_gb_origin_low_unite(db_session):
    for _ in range(100):
        _make_person(db_session, ReligiousBackground.PROTESTANT, Origin.GB, 50)
    predictor = VotingPredictor(db_session)
    result = predictor.predict()
    assert result["unite_share"] < 0.20


def test_vote_shares_sum_to_one(db_session):
    _make_person(db_session, ReligiousBackground.CATHOLIC, Origin.NI, 25)
    _make_person(db_session, ReligiousBackground.PROTESTANT, Origin.NI, 45)
    predictor = VotingPredictor(db_session)
    result = predictor.predict()
    total = result["unite_share"] + result["remain_share"] + result["undecided_share"]
    assert total == pytest.approx(1.0, abs=0.01)


def test_vote_counts_sum_to_projected_turnout(db_session):
    for _ in range(50):
        _make_person(db_session, ReligiousBackground.OTHER, Origin.NI, 35)
    predictor = VotingPredictor(db_session)
    result = predictor.predict()
    assert result["unite"] + result["remain"] + result["undecided"] == pytest.approx(
        result["projected_turnout"], abs=2
    )


def test_age_affects_turnout_not_preference(db_session):
    predictor = VotingPredictor(db_session)
    young = predictor._turnout(20, ReligiousBackground.CATHOLIC)
    middle = predictor._turnout(40, ReligiousBackground.CATHOLIC)
    assert young > middle


def test_children_are_not_counted_as_eligible(db_session):
    _make_person(db_session, ReligiousBackground.CATHOLIC, Origin.NI, 17)
    _make_person(db_session, ReligiousBackground.CATHOLIC, Origin.NI, 18)
    result = VotingPredictor(db_session).predict()
    assert result["total_population"] == 2
    assert result["eligible_population"] == 1


def test_predict_by_location_returns_all_locations(db_session):
    _make_person(
        db_session, ReligiousBackground.CATHOLIC, Origin.NI, 30, Location.BELFAST
    )
    _make_person(
        db_session,
        ReligiousBackground.PROTESTANT,
        Origin.NI,
        40,
        Location.DERRY_STRABANE,
    )
    predictor = VotingPredictor(db_session)
    by_loc = predictor.predict_by_location()
    from src.ni_model.core.models import Location as Loc

    assert set(by_loc.keys()) == {loc.value for loc in Loc}


def test_predict_by_location_empty_location_returns_zeros(db_session):
    predictor = VotingPredictor(db_session)
    by_loc = predictor.predict_by_location()
    fermanagh = by_loc["fermanagh_omagh"]
    assert fermanagh["eligible_population"] == 0
    assert fermanagh["unite_share"] == 0.0


def test_uncertainty_and_scenarios_are_ordered(db_session):
    _make_person(db_session, ReligiousBackground.NONE, Origin.NI, 40)
    result = VotingPredictor(db_session).predict()
    interval = result["intervals"]["unite_share"]
    assert interval["low"] < interval["estimate"] < interval["high"]
    shares = [scenario["unite_share"] for scenario in result["scenarios"]]
    assert shares == sorted(shares)
