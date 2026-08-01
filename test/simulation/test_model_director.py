import pytest

from src.ni_model.core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)
from src.ni_model.data.repository import PersonRepository
from src.ni_model.simulation.demographic_calculators import (
    BirthCalculator,
    DeathCalculator,
    MigrationCalculator,
)
from src.ni_model.simulation.model_director import ModelDirector


@pytest.fixture
def initial_population(postgres_db_session):
    """Create initial population for testing"""
    repo = PersonRepository(postgres_db_session)
    persons = []

    for i in range(100):
        person = Person(
            age=20 + (i % 60),
            religious_background=(
                ReligiousBackground.CATHOLIC
                if i % 2 == 0
                else ReligiousBackground.PROTESTANT
            ),
            gender=Gender.MALE if (i // 2) % 2 == 0 else Gender.FEMALE,
            education_level=EducationLevel.TERTIARY,
            location=Location.BELFAST if i < 50 else Location.DERRY_STRABANE,
            origin=Origin.NI,
        )
        persons.append(person)

    repo.bulk_create(persons)
    return repo


def test_model_director_basic(postgres_db_session, initial_population):
    """Test basic ModelDirector creation from config"""
    config = {"birth_rates": [], "death_rates": [], "migration_rates": []}
    director = ModelDirector(postgres_db_session, config)

    assert director.db_session == postgres_db_session


def test_model_director_from_yaml(postgres_db_session, initial_population):
    """Test loading model from YAML file"""
    director = ModelDirector.from_yaml(postgres_db_session, "models/ni_base_2024.yaml")

    assert director.config["name"] == "NI Historical Model"


def test_yaml_model_simulate_births(postgres_db_session, initial_population):
    """Test birth simulation with YAML model"""
    director = ModelDirector.from_yaml(postgres_db_session, "models/ni_base_2024.yaml")

    initial_count = initial_population.count()
    births = director.simulate_births(2024)
    postgres_db_session.commit()

    assert births >= 0
    assert initial_population.count() == initial_count + births


def test_yaml_model_full_simulation(postgres_db_session, initial_population):
    """Test complete simulation with YAML model"""
    director = ModelDirector.from_yaml(postgres_db_session, "models/ni_base_2024.yaml")

    initial_count = initial_population.count()

    births = director.simulate_births(2024)
    postgres_db_session.commit()

    deaths = director.simulate_deaths(2024)
    postgres_db_session.commit()

    migration = director.simulate_migration(2024)
    postgres_db_session.commit()

    final_count = initial_population.count()
    assert final_count == initial_count + births - deaths + migration


def test_model_director_dict_config(postgres_db_session, initial_population):
    """Test ModelDirector with dict configuration"""
    config = {
        "birth_rates": [
            {"rate": 15.0, "filters": {"religious_background": "CATHOLIC"}},
            {"rate": 11.0, "filters": {"religious_background": "PROTESTANT"}},
        ],
        "death_rates": [{"rate": 10.0, "filters": {}}],
        "migration_rates": [{"rate": 2.0, "filters": {}}],
    }
    director = ModelDirector(postgres_db_session, config)

    assert (
        len(director._build_calculators(config["birth_rates"], BirthCalculator, 2024))
        == 2
    )
    assert (
        len(director._build_calculators(config["death_rates"], DeathCalculator, 2024))
        == 1
    )
    assert (
        len(
            director._build_calculators(
                config["migration_rates"], MigrationCalculator, 2024
            )
        )
        == 1
    )


def test_internal_migration_rules_are_applied_simultaneously(postgres_db_session):
    repo = PersonRepository(postgres_db_session)
    repo.bulk_create(
        [
            Person(
                age=30,
                religious_background=ReligiousBackground.CATHOLIC,
                gender=Gender.FEMALE,
                education_level=EducationLevel.TERTIARY,
                location=Location.BELFAST,
                origin=Origin.NI,
            )
            for _ in range(100)
        ]
    )
    director = ModelDirector(
        postgres_db_session,
        {
            "rate_jitter": 0,
            "random_seed": 7,
            "internal_migration_rates": [
                {
                    "rate": 100,
                    "destination": "ARDS_NORTH_DOWN",
                    "filters": {"location": "BELFAST"},
                },
                {
                    "rate": 100,
                    "destination": "LISBURN_CASTLEREAGH",
                    "filters": {"location": "BELFAST"},
                },
            ],
        },
    )

    assert director.simulate_internal_migration(2024) == 20
    postgres_db_session.flush()
    assert len(repo.get_by_location(Location.BELFAST)) == 80
    assert len(repo.get_by_location(Location.ARDS_NORTH_DOWN)) == 10
    assert len(repo.get_by_location(Location.LISBURN_CASTLEREAGH)) == 10


def test_year_min_excludes_earlier_years(postgres_db_session, initial_population):
    """Test rate with year_min is not applied before that year"""
    config = {
        "birth_rates": [{"rate": 20.0, "year_min": 2000, "filters": {}}],
        "death_rates": [],
        "migration_rates": [],
    }
    director = ModelDirector(postgres_db_session, config)

    assert director.simulate_births(1999) == 0
    assert director.simulate_births(2000) > 0


def test_year_max_excludes_later_years(postgres_db_session, initial_population):
    """Test rate with year_max is not applied after that year"""
    config = {
        "birth_rates": [{"rate": 20.0, "year_max": 1994, "filters": {}}],
        "death_rates": [],
        "migration_rates": [],
    }
    director = ModelDirector(postgres_db_session, config)

    assert director.simulate_births(1994) > 0
    assert director.simulate_births(1995) == 0


def test_year_range_selects_correct_block(postgres_db_session, initial_population):
    """Test only the matching year block is applied when multiple blocks exist"""
    config = {
        "birth_rates": [
            {
                "rate": 26.0,
                "year_min": 1969,
                "year_max": 1994,
                "filters": {"religious_background": "CATHOLIC"},
            },
            {
                "rate": 15.0,
                "year_min": 2010,
                "filters": {"religious_background": "CATHOLIC"},
            },
        ],
        "death_rates": [],
        "migration_rates": [],
    }
    director = ModelDirector(postgres_db_session, config)

    troubles_births = director.simulate_births(1980)
    postgres_db_session.rollback()
    modern_births = director.simulate_births(2024)
    postgres_db_session.rollback()

    assert troubles_births > modern_births


def test_no_year_bounds_applies_to_all_years(postgres_db_session):
    """Test rate with no year bounds applies to any year"""
    repo = PersonRepository(postgres_db_session)
    repo.bulk_create(
        [
            Person(
                age=30,
                religious_background=ReligiousBackground.CATHOLIC,
                gender=Gender.FEMALE,
                education_level=EducationLevel.TERTIARY,
                location=Location.BELFAST,
                origin=Origin.NI,
            )
            for _ in range(1_000)
        ]
    )
    config = {
        "rate_jitter": 0.0,
        "birth_rates": [{"rate": 10.0, "filters": {}}],
        "death_rates": [],
        "migration_rates": [],
    }
    director = ModelDirector(postgres_db_session, config)

    assert director.simulate_births(1969) > 0
    postgres_db_session.rollback()
    assert director.simulate_births(2050) > 0
    postgres_db_session.rollback()


def test_troubles_era_higher_birth_rate_than_modern(
    postgres_db_session, initial_population
):
    """Test Troubles-era Catholic birth rate exceeds modern rate"""
    director = ModelDirector.from_yaml(postgres_db_session, "models/ni_base_2024.yaml")

    troubles_births = director.simulate_births(1980)
    postgres_db_session.rollback()
    modern_births = director.simulate_births(2024)
    postgres_db_session.rollback()

    assert troubles_births > modern_births


def test_troubles_era_net_emigration(postgres_db_session, initial_population):
    """Test Troubles era has net emigration (negative migration)"""
    repo = PersonRepository(postgres_db_session)
    repo.bulk_create(
        [
            Person(
                age=30,
                religious_background=ReligiousBackground.CATHOLIC,
                gender=Gender.MALE,
                education_level=EducationLevel.TERTIARY,
                location=Location.BELFAST,
                origin=Origin.NI,
            )
            for _ in range(900)  # 900 extra: -8/1000 * 1000 = -8
        ]
    )
    director = ModelDirector.from_yaml(postgres_db_session, "models/ni_base_2024.yaml")

    troubles_migration = director.simulate_migration(1980)
    postgres_db_session.rollback()
    modern_migration = director.simulate_migration(2024)
    postgres_db_session.rollback()

    assert troubles_migration < 0
    assert modern_migration >= 0


def test_jitter_varies_births_across_years(postgres_db_session):
    """Test that jitter produces different birth counts across repeated calls"""
    repo = PersonRepository(postgres_db_session)
    repo.bulk_create(
        [
            Person(
                age=30,
                religious_background=ReligiousBackground.CATHOLIC,
                gender=Gender.FEMALE,
                education_level=EducationLevel.TERTIARY,
                location=Location.BELFAST,
                origin=Origin.NI,
            )
            for _ in range(10_000)
        ]
    )
    config = {
        "rate_jitter": 0.10,
        "birth_rates": [{"rate": 20.0, "filters": {}}],
        "death_rates": [],
        "migration_rates": [],
    }
    director = ModelDirector(postgres_db_session, config)

    counts = set()
    for _ in range(10):
        counts.add(director.simulate_births(2024))
        postgres_db_session.rollback()

    assert len(counts) > 1


def test_zero_jitter_produces_deterministic_rate(postgres_db_session):
    """Test jitter=0 always applies the exact configured rate"""
    repo = PersonRepository(postgres_db_session)
    repo.bulk_create(
        [
            Person(
                age=30,
                religious_background=ReligiousBackground.CATHOLIC,
                gender=Gender.FEMALE,
                education_level=EducationLevel.TERTIARY,
                location=Location.BELFAST,
                origin=Origin.NI,
            )
            for _ in range(1_000)
        ]
    )
    config = {
        "rate_jitter": 0.0,
        "birth_rates": [{"rate": 20.0, "filters": {}}],
        "death_rates": [],
        "migration_rates": [],
    }
    director = ModelDirector(postgres_db_session, config)

    counts = {director.simulate_births(2024) for _ in range(5)}
    postgres_db_session.rollback()

    assert counts == {20}  # 20/1000 * 1000 = exactly 20 every time


def test_default_jitter_applied_when_not_configured(postgres_db_session):
    """Test default jitter of 0.05 is used when rate_jitter not in config"""
    config = {
        "birth_rates": [{"rate": 10.0, "filters": {}}],
        "death_rates": [],
        "migration_rates": [],
    }
    director = ModelDirector(postgres_db_session, config)

    assert director.jitter == 0.05


def test_per_community_adjustments_split_unfiltered_rules(
    postgres_db_session, tmp_path
):
    model_path = tmp_path / "model.yaml"
    model_path.write_text(
        "rate_jitter: 0\nrandom_seed: 42\nbirth_rates:\n"
        "- rate: 10\n  filters: {}\ndeath_rates: []\n"
        "migration_rates: []\ninternal_migration_rates: []\n",
        encoding="utf-8",
    )
    community = {
        group: {
            "birth_multiplier": 2.0 if group == "catholic" else 1.0,
            "death_multiplier": 1.0,
            "migration_multiplier": 1.0,
            "relocation_multiplier": 1.0,
        }
        for group in ("catholic", "protestant", "other", "none")
    }

    director = ModelDirector.from_yaml(
        postgres_db_session, model_path, adjustments={"community": community}
    )

    rules = director.config["birth_rates"]
    assert len(rules) == 4
    rates = {rule["filters"]["religious_background"]: rule["rate"] for rule in rules}
    assert rates == {"CATHOLIC": 20.0, "PROTESTANT": 10.0, "OTHER": 10.0, "NONE": 10.0}


def test_per_community_adjustments_modify_existing_group_rules(postgres_db_session):
    adjustments = {
        "community": {
            "catholic": {"birth_multiplier": 1.5},
            "protestant": {"birth_multiplier": 1.0},
            "other": {"birth_multiplier": 1.0},
            "none": {"birth_multiplier": 1.0},
        }
    }

    director = ModelDirector.from_yaml(
        postgres_db_session,
        "models/ni_current_community.yaml",
        adjustments=adjustments,
    )

    catholic = next(
        rule
        for rule in director.config["birth_rates"]
        if rule["filters"]["religious_background"] == "CATHOLIC"
    )
    assert catholic["rate"] == pytest.approx(12.135442 * 1.5)


def test_same_seed_produces_same_rate_sequence(postgres_db_session):
    config = {
        "random_seed": 123,
        "rate_jitter": 0.10,
        "birth_rates": [],
        "death_rates": [],
        "migration_rates": [],
    }
    first = ModelDirector(postgres_db_session, config)
    second = ModelDirector(postgres_db_session, config)

    assert [first._jittered_rate(10) for _ in range(5)] == [
        second._jittered_rate(10) for _ in range(5)
    ]


@pytest.mark.parametrize(
    "config, message",
    [
        (None, "mapping"),
        ({"rate_jitter": 1.1}, "rate_jitter"),
        ({"rate_jitter": "0.1"}, "rate_jitter"),
        ({"random_seed": "42"}, "random_seed"),
        ({"death_rates": [{"rate": -1}]}, "non-negative"),
        ({"birth_rates": [{"rate": 1, "filters": []}]}, "filters"),
        (
            {"birth_rates": [{"rate": 1, "filters": {"unknown": 1}}]},
            "unsupported filters",
        ),
        (
            {"death_rates": [{"rate": 1, "year_min": 2025, "year_max": 2024}]},
            "year_min",
        ),
    ],
)
def test_invalid_model_config_rejected(postgres_db_session, config, message):
    with pytest.raises(ValueError, match=message):
        ModelDirector(postgres_db_session, config)


@pytest.mark.parametrize(
    "profile,message",
    [
        ([], "non-empty"),
        ([{"age_min": 1, "age_max": 130, "rate": 1}], "contiguous"),
        ([{"age_min": 0, "age_max": 50, "rate": 1}], "age 120"),
        ([{"age_min": 0, "age_max": 130, "rate": 0}], "positive"),
    ],
)
def test_invalid_mortality_age_profile_rejected(postgres_db_session, profile, message):
    with pytest.raises(ValueError, match=message):
        ModelDirector(postgres_db_session, {"mortality_age_rates": profile})


def test_current_model_uses_observed_age_specific_mortality(postgres_db_session):
    director = ModelDirector.from_yaml(postgres_db_session, "models/ni_current.yaml")

    profile = director.config["mortality_age_rates"]
    assert profile[1] == {"age_min": 1, "age_max": 4, "rate": 0.091557}
    assert profile[-1]["age_min"] == 85
    assert profile[-1]["rate"] == pytest.approx(149.379433)
