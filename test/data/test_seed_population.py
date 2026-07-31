from scripts.seed_population import PROFILES, _mapping
from src.ni_model.core.models import ReligiousBackground
from src.ni_model.data.population_generator import generate_population


def test_full_scale_profiles_have_documented_sizes():
    assert PROFILES["current"]["size"] == 1_903_175
    assert PROFILES["historical"]["size"] == 1_536_065
    assert "estimate" in PROFILES["historical"]["status"]


def test_mapping_creates_baseline_row():
    person = generate_population(1, seed=1)[0]
    person.religious_background = ReligiousBackground.CATHOLIC
    mapping = _mapping(person)
    assert mapping["run_id"] is None
    assert mapping["religious_background"] is ReligiousBackground.CATHOLIC
    assert mapping["id"] is not None
