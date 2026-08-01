from scripts.seed_population import PROFILES, _mapping
from src.ni_model.core.models import ReligiousBackground
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
    assert mapping["id"] is not None


def test_profiles_define_their_population_reference_year():
    assert PROFILES["current"]["reference_year"] == 2021
    assert PROFILES["historical"]["reference_year"] == 1969
    assert PROFILES["historical"]["age_bands"] is not None
    assert PROFILES["historical"]["origin_weights"] is not None
