from collections import Counter

import pytest

from src.ni_model.core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)
from src.ni_model.data.population_generator import (
    calibrated_age_bands,
    generate_population,
    iter_population,
)

SIZE = 10_000


@pytest.fixture(scope="module")
def population():
    return generate_population(SIZE, seed=42)


def _shares(population, attr):
    counts = Counter(getattr(p, attr) for p in population)
    total = len(population)
    return {k: v / total for k, v in counts.items()}


def test_returns_correct_size(population):
    assert len(population) == SIZE


def test_returns_person_instances(population):
    assert all(isinstance(p, Person) for p in population)


def test_persons_have_no_ids(population):
    """Persons should be unsaved — id assigned by DB on insert"""
    assert all(p.id is None for p in population)


def test_religious_breakdown_catholic_plurality(population):
    shares = _shares(population, "religious_background")
    assert shares[ReligiousBackground.CATHOLIC] == pytest.approx(0.457, abs=0.02)


def test_religious_breakdown_protestant(population):
    shares = _shares(population, "religious_background")
    assert shares[ReligiousBackground.PROTESTANT] == pytest.approx(0.435, abs=0.02)


def test_community_background_other_and_none(population):
    shares = _shares(population, "religious_background")
    assert shares[ReligiousBackground.OTHER] == pytest.approx(0.015, abs=0.01)
    assert shares[ReligiousBackground.NONE] == pytest.approx(0.093, abs=0.02)


def test_all_religious_backgrounds_present(population):
    backgrounds = {p.religious_background for p in population}
    assert backgrounds == set(ReligiousBackground)


def test_probable_community_has_no_none_and_preserves_observed_groups(population):
    assert all(
        person.probable_community != ReligiousBackground.NONE for person in population
    )
    reported_none = [
        person
        for person in population
        if person.religious_background == ReligiousBackground.NONE
    ]
    probable_other_share = sum(
        person.probable_community == ReligiousBackground.OTHER
        for person in reported_none
    ) / len(reported_none)
    assert probable_other_share == pytest.approx(0.0304, abs=0.015)
    assert all(
        person.probable_community == person.religious_background
        for person in population
        if person.religious_background != ReligiousBackground.NONE
    )


def test_probable_none_assignment_reflects_shrunk_lgd_evidence(population):
    derry_none = [
        person
        for person in population
        if person.location == Location.DERRY_STRABANE
        and person.religious_background == ReligiousBackground.NONE
    ]
    mid_east_antrim_none = [
        person
        for person in population
        if person.location == Location.MID_EAST_ANTRIM
        and person.religious_background == ReligiousBackground.NONE
    ]
    derry_catholic = sum(
        person.probable_community == ReligiousBackground.CATHOLIC
        for person in derry_none
    ) / len(derry_none)
    mid_east_antrim_catholic = sum(
        person.probable_community == ReligiousBackground.CATHOLIC
        for person in mid_east_antrim_none
    ) / len(mid_east_antrim_none)

    assert derry_catholic > mid_east_antrim_catholic + 0.20


def test_gender_roughly_equal(population):
    shares = _shares(population, "gender")
    assert shares[Gender.MALE] == pytest.approx(0.494, abs=0.03)
    assert shares[Gender.FEMALE] == pytest.approx(0.504, abs=0.03)


def test_census_sex_categories_present(population):
    assert {p.gender for p in population} == {Gender.MALE, Gender.FEMALE}


def test_all_locations_present(population):
    assert {p.location for p in population} == set(Location)


def test_lgd_shares_match_census_marginals(population):
    shares = _shares(population, "location")
    assert shares[Location.BELFAST] == pytest.approx(345_418 / 1_903_175, abs=0.02)
    assert shares[Location.FERMANAGH_OMAGH] == pytest.approx(
        116_812 / 1_903_175, abs=0.02
    )


def test_community_background_preserves_lgd_joint_distribution(population):
    derry = [p for p in population if p.location == Location.DERRY_STRABANE]
    mid_east_antrim = [p for p in population if p.location == Location.MID_EAST_ANTRIM]

    derry_catholic = sum(
        p.religious_background == ReligiousBackground.CATHOLIC for p in derry
    ) / len(derry)
    mea_protestant = sum(
        p.religious_background == ReligiousBackground.PROTESTANT
        for p in mid_east_antrim
    ) / len(mid_east_antrim)

    assert derry_catholic == pytest.approx(109_131 / 150_756, abs=0.04)
    assert mea_protestant == pytest.approx(93_477 / 138_994, abs=0.04)


def test_historical_targets_retain_geographic_pattern():
    targets = [
        (ReligiousBackground.CATHOLIC, 0.311),
        (ReligiousBackground.PROTESTANT, 0.649),
        (ReligiousBackground.OTHER, 0.020),
        (ReligiousBackground.NONE, 0.020),
    ]
    historical = list(iter_population(20_000, seed=42, religion_weights=targets))
    shares = _shares(historical, "religious_background")
    derry = [p for p in historical if p.location == Location.DERRY_STRABANE]
    mid_east_antrim = [p for p in historical if p.location == Location.MID_EAST_ANTRIM]

    assert shares[ReligiousBackground.CATHOLIC] == pytest.approx(0.311, abs=0.02)
    assert shares[ReligiousBackground.PROTESTANT] == pytest.approx(0.649, abs=0.02)
    assert sum(
        p.religious_background == ReligiousBackground.CATHOLIC for p in derry
    ) / len(derry) > sum(
        p.religious_background == ReligiousBackground.CATHOLIC for p in mid_east_antrim
    ) / len(
        mid_east_antrim
    )


def test_historical_age_calibration_matches_1971_broad_marginals():
    total = 1_536_065
    bands = calibrated_age_bands(
        [
            (0, 14, 456_997 / total),
            (15, 39, 512_242 / total),
            (40, 64, 400_842 / total),
            (65, 110, 165_984 / total),
        ]
    )
    historical = list(iter_population(30_000, seed=42, age_bands=bands))

    assert sum(person.age <= 14 for person in historical) / len(
        historical
    ) == pytest.approx(456_997 / total, abs=0.015)
    assert sum(person.age >= 65 for person in historical) / len(
        historical
    ) == pytest.approx(165_984 / total, abs=0.015)


def test_origin_ni_dominant(population):
    shares = _shares(population, "origin")
    assert shares[Origin.NI] == pytest.approx(0.865, abs=0.02)


def test_origin_matches_census_country_of_birth(population):
    shares = _shares(population, "origin")
    assert shares[Origin.ROI] == pytest.approx(0.021, abs=0.01)
    assert shares[Origin.GB] == pytest.approx(0.048, abs=0.015)
    assert shares[Origin.OTHER] == pytest.approx(0.065, abs=0.015)


def test_all_origins_present(population):
    assert {p.origin for p in population} == set(Origin)


def test_age_range_valid(population):
    ages = [p.age for p in population]
    assert min(ages) >= 0
    assert max(ages) <= 110


def test_age_pyramid_working_age_bulk(population):
    working_age = sum(1 for p in population if 15 <= p.age <= 64)
    share = working_age / len(population)
    assert share == pytest.approx(0.625, abs=0.04)


def test_elderly_share(population):
    elderly = sum(1 for p in population if p.age >= 65)
    share = elderly / len(population)
    assert share == pytest.approx(0.17, abs=0.03)


def test_community_background_uses_census_age_distribution(population):
    catholic = [
        person
        for person in population
        if person.religious_background == ReligiousBackground.CATHOLIC
    ]
    protestant = [
        person
        for person in population
        if person.religious_background == ReligiousBackground.PROTESTANT
    ]
    catholic_65_plus = sum(person.age >= 65 for person in catholic) / len(catholic)
    protestant_65_plus = sum(person.age >= 65 for person in protestant) / len(
        protestant
    )

    assert catholic_65_plus == pytest.approx(123_700 / 869_749, abs=0.025)
    assert protestant_65_plus == pytest.approx(193_314 / 827_541, abs=0.025)
    assert protestant_65_plus - catholic_65_plus > 0.07


def test_centenarian_share_is_realistic(population):
    centenarians = sum(1 for p in population if p.age >= 100)
    assert centenarians / len(population) < 0.001


def test_all_education_levels_present(population):
    assert {p.education_level for p in population} == set(EducationLevel)


def test_young_children_pre_primary(population):
    under_5 = [p for p in population if p.age <= 4]
    assert all(
        p.education_level in (EducationLevel.PRE_PRIMARY, EducationLevel.PRIMARY)
        for p in under_5
    )


def test_reproducible_with_seed():
    pop1 = generate_population(100, seed=99)
    pop2 = generate_population(100, seed=99)
    assert [(p.age, p.religious_background, p.location) for p in pop1] == [
        (p.age, p.religious_background, p.location) for p in pop2
    ]


def test_iterator_is_reproducible_without_materialising_population():
    first = iter_population(3, seed=7)
    assert iter(first) is first
    rows = list(first)
    comparison = list(iter_population(3, seed=7))
    assert [person.age for person in rows] == [person.age for person in comparison]


def test_iterator_rejects_negative_size():
    with pytest.raises(ValueError, match="non-negative"):
        next(iter_population(-1))


def test_different_seeds_differ():
    pop1 = generate_population(100, seed=1)
    pop2 = generate_population(100, seed=2)
    assert [(p.age, p.location) for p in pop1] != [(p.age, p.location) for p in pop2]


def test_single_person():
    pop = generate_population(1, seed=0)
    assert len(pop) == 1
    assert isinstance(pop[0], Person)


def test_zero_size():
    assert generate_population(0) == []


def test_birth_year_uses_requested_reference_year():
    person = generate_population(1, seed=42, reference_year=1971)[0]
    assert person.birth_year == 1971 - person.age


def test_negative_size_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        generate_population(-1)
