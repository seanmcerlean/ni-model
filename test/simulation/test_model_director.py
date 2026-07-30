import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from src.ni_model.core.database import Base
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


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for testing"""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture
def postgres_db_session(postgres_container):
    """Create PostgreSQL database session"""
    engine = create_engine(postgres_container.get_connection_url())
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


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
            location=Location.BELFAST_NORTH if i < 50 else Location.DERRY,
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
                location=Location.BELFAST_NORTH,
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
                location=Location.BELFAST_NORTH,
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
                location=Location.BELFAST_NORTH,
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
                location=Location.BELFAST_NORTH,
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
