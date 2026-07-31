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


def _make_person(db, religion, origin, age, location=Location.BELFAST_NORTH):
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


def test_vote_counts_sum_to_population(db_session):
    for _ in range(50):
        _make_person(db_session, ReligiousBackground.OTHER, Origin.NI, 35)
    predictor = VotingPredictor(db_session)
    result = predictor.predict()
    assert result["unite"] + result["remain"] + result["undecided"] == pytest.approx(
        result["total_population"], abs=2
    )


def test_young_voters_higher_unite_than_old(db_session):
    _make_person(db_session, ReligiousBackground.CATHOLIC, Origin.NI, 25)
    _make_person(db_session, ReligiousBackground.CATHOLIC, Origin.NI, 70)
    predictor = VotingPredictor(db_session)
    # Young Catholic should have higher propensity than old Catholic
    young = predictor._unite_propensity(ReligiousBackground.CATHOLIC, Origin.NI, 25)
    old = predictor._unite_propensity(ReligiousBackground.CATHOLIC, Origin.NI, 70)
    assert young > old


def test_roi_origin_highest_unite_propensity(db_session):
    predictor = VotingPredictor(db_session)
    roi = predictor._unite_propensity(ReligiousBackground.OTHER, Origin.ROI, 40)
    gb = predictor._unite_propensity(ReligiousBackground.OTHER, Origin.GB, 40)
    assert roi > gb


def test_predict_by_location_returns_all_locations(db_session):
    _make_person(
        db_session, ReligiousBackground.CATHOLIC, Origin.NI, 30, Location.BELFAST_NORTH
    )
    _make_person(
        db_session, ReligiousBackground.PROTESTANT, Origin.NI, 40, Location.DERRY
    )
    predictor = VotingPredictor(db_session)
    by_loc = predictor.predict_by_location()
    from src.ni_model.core.models import Location as Loc

    assert set(by_loc.keys()) == {loc.value for loc in Loc}


def test_predict_by_location_empty_location_returns_zeros(db_session):
    predictor = VotingPredictor(db_session)
    by_loc = predictor.predict_by_location()
    fermanagh = by_loc["fermanagh"]
    assert fermanagh["total"] == 0
    assert fermanagh["unite_share"] == 0.0


def test_custom_rates_applied(db_session):
    _make_person(db_session, ReligiousBackground.CATHOLIC, Origin.NI, 30)
    custom_rates = {
        "by_religion": {ReligiousBackground.CATHOLIC: 0.99},
        "by_origin": {Origin.NI: 0.99},
        "age_modifiers": {(0, 200): 0.0},
        "religion_weight": 1.0,
        "origin_weight": 0.0,
    }
    predictor = VotingPredictor(db_session, rates=custom_rates)
    result = predictor.predict()
    assert result["unite_share"] > 0.95


def test_propensity_clamped_between_zero_and_one(db_session):
    predictor = VotingPredictor(db_session)
    p = predictor._unite_propensity(ReligiousBackground.CATHOLIC, Origin.ROI, 20)
    assert 0.0 <= p <= 1.0
