import pytest

from scripts.seed_population import PROFILES, _mapping, _seed_action, validate_baseline
from src.ni_model.core.models import Person, ReligiousBackground
from src.ni_model.data.population_generator import generate_population


def test_full_scale_profiles_have_documented_sizes():
    assert PROFILES["current"]["size"] == 1_903_175
    assert PROFILES["historical"]["size"] == 1_512_500
    assert "estimate" in PROFILES["historical"]["status"]


def test_mapping_creates_baseline_row():
    person = generate_population(1, seed=1)[0]
    person.religious_background = ReligiousBackground.CATHOLIC
    mapping = _mapping(person, 17)
    assert mapping["run_id"] is None
    assert mapping["person_number"] == 17
    assert mapping["birth_year"] == 2021 - mapping["age"]
    assert mapping["religious_background"] is ReligiousBackground.CATHOLIC
    assert mapping["probable_community"] is person.probable_community
    assert mapping["id"] is not None


def test_default_full_seed_replaces_a_truncated_baseline():
    assert _seed_action(25_000, 1_903_175, True, False) == "replace"
    assert _seed_action(1_903_175, 1_903_175, True, False) == "reuse"
    assert _seed_action(25_000, 25_000, False, False) == "reuse"


def test_profiles_define_their_population_reference_year():
    assert PROFILES["current"]["reference_year"] == 2021
    assert PROFILES["historical"]["reference_year"] == 1969
    assert PROFILES["historical"]["age_bands"] is not None
    assert PROFILES["historical"]["origin_weights"] is not None


def test_current_baseline_invariants_validate_joint_demographics(db_session):
    people = generate_population(10_000, seed=42)
    db_session.bulk_insert_mappings(
        Person,
        [_mapping(person, index) for index, person in enumerate(people, start=1)],
    )
    db_session.commit()

    validate_baseline(db_session, "current", 10_000)

    first = db_session.query(Person).first()
    first.birth_year += 1
    db_session.commit()
    with pytest.raises(RuntimeError, match="inconsistent birth years"):
        validate_baseline(db_session, "current", 10_000)
