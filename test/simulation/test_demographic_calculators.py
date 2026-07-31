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
    InternalMigrationCalculator,
    MigrationCalculator,
)


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


def test_birth_calculator_basic(postgres_db_session, initial_population):
    """Test basic birth calculation on entire population"""
    calculator = BirthCalculator(postgres_db_session, rate=10.0)

    initial_count = initial_population.count()
    births = calculator.calculate()
    postgres_db_session.commit()

    assert births == 1  # 10/1000 * 100 = 1
    assert initial_population.count() == initial_count + births


def test_birth_calculator_with_cohort_filter(postgres_db_session, initial_population):
    """Test birth calculation on specific cohort"""
    # Only Catholic population
    calculator = BirthCalculator(
        postgres_db_session,
        rate=20.0,
        query_filters={"religious_background": ReligiousBackground.CATHOLIC},
    )

    initial_count = initial_population.count()
    births = calculator.calculate()
    postgres_db_session.commit()

    # 50 Catholics, 20/1000 * 50 = 1
    assert births == 1
    assert initial_population.count() == initial_count + births

    # Verify new births are Catholic
    all_persons = initial_population.get_all(limit=initial_population.count())
    new_births = [p for p in all_persons if p.age == 0]
    assert all(
        p.religious_background == ReligiousBackground.CATHOLIC for p in new_births
    )


def test_birth_calculator_age_range_filter(postgres_db_session, initial_population):
    """Test birth calculation on age range cohort"""
    # Women aged 20-40
    calculator = BirthCalculator(
        postgres_db_session,
        rate=50.0,
        query_filters={"gender": Gender.FEMALE, "age_min": 20, "age_max": 40},
    )

    births = calculator.calculate()
    postgres_db_session.commit()

    assert births >= 0
    assert isinstance(births, int)


def test_birth_calculator_zero_population(postgres_db_session):
    """Test birth calculation with zero population"""
    calculator = BirthCalculator(postgres_db_session, rate=10.0)

    births = calculator.calculate()

    assert births == 0


def test_birth_calculator_empty_cohort(postgres_db_session, initial_population):
    """Test birth calculation with empty cohort"""
    # Filter that matches no one
    calculator = BirthCalculator(
        postgres_db_session, rate=50.0, query_filters={"age_min": 100, "age_max": 110}
    )

    births = calculator.calculate()

    assert births == 0


def test_death_calculator_basic(postgres_db_session, initial_population):
    """Test basic death calculation"""
    calculator = DeathCalculator(postgres_db_session, rate=10.0)

    initial_count = initial_population.count()
    deaths = calculator.calculate()
    postgres_db_session.commit()

    assert deaths == 1  # 10/1000 * 100 = 1
    assert initial_population.count() == initial_count - deaths


def test_death_calculator_with_cohort_filter(postgres_db_session, initial_population):
    """Test death calculation on specific cohort"""
    # Only elderly (age 70+)
    calculator = DeathCalculator(
        postgres_db_session, rate=100.0, query_filters={"age_min": 70}
    )

    initial_count = initial_population.count()
    deaths = calculator.calculate()
    postgres_db_session.commit()

    assert deaths >= 0
    assert initial_population.count() == initial_count - deaths


def test_death_calculator_high_rate(postgres_db_session, initial_population):
    """Test death calculation with high rate"""
    calculator = DeathCalculator(postgres_db_session, rate=50.0)

    initial_count = initial_population.count()
    deaths = calculator.calculate()
    postgres_db_session.commit()

    assert deaths == 5  # 50/1000 * 100 = 5
    assert initial_population.count() == initial_count - deaths


def test_death_calculator_extreme_rate(postgres_db_session, initial_population):
    """Test death calculation doesn't exceed cohort size"""
    calculator = DeathCalculator(postgres_db_session, rate=2000.0)

    initial_count = initial_population.count()
    deaths = calculator.calculate()
    postgres_db_session.commit()

    assert deaths <= initial_count
    assert initial_population.count() >= 0


def test_migration_calculator_positive(postgres_db_session, initial_population):
    """Test positive migration (in-migration)"""
    calculator = MigrationCalculator(postgres_db_session, rate=10.0)

    initial_count = initial_population.count()
    net_migration = calculator.calculate()
    postgres_db_session.commit()

    assert net_migration == 1  # 10/1000 * 100 = 1
    assert initial_population.count() == initial_count + net_migration


def test_migration_calculator_with_cohort_filter(
    postgres_db_session, initial_population
):
    """Test migration on specific cohort"""
    # Protestant population only
    calculator = MigrationCalculator(
        postgres_db_session,
        rate=20.0,
        query_filters={"religious_background": ReligiousBackground.PROTESTANT},
    )

    initial_count = initial_population.count()
    net_migration = calculator.calculate()
    postgres_db_session.commit()

    # 50 Protestants, 20/1000 * 50 = 1
    assert net_migration == 1
    assert initial_population.count() == initial_count + net_migration


def test_migration_calculator_negative(postgres_db_session, initial_population):
    """Test negative migration (out-migration)"""
    calculator = MigrationCalculator(postgres_db_session, rate=-10.0)

    initial_count = initial_population.count()
    net_migration = calculator.calculate()
    postgres_db_session.commit()

    assert net_migration == -1  # -10/1000 * 100 = -1
    assert initial_population.count() == initial_count + net_migration


def test_migration_calculator_zero(postgres_db_session, initial_population):
    """Test zero migration"""
    calculator = MigrationCalculator(postgres_db_session, rate=0.0)

    initial_count = initial_population.count()
    net_migration = calculator.calculate()

    assert net_migration == 0
    assert initial_population.count() == initial_count


def test_sequential_demographic_changes(postgres_db_session, initial_population):
    """Test sequential application of births, deaths, migration"""
    initial_count = initial_population.count()

    # Apply births
    birth_calc = BirthCalculator(postgres_db_session, rate=15.0)
    births = birth_calc.calculate()
    postgres_db_session.commit()

    # Apply deaths
    death_calc = DeathCalculator(postgres_db_session, rate=10.0)
    deaths = death_calc.calculate()
    postgres_db_session.commit()

    # Apply migration
    migration_calc = MigrationCalculator(postgres_db_session, rate=5.0)
    migration = migration_calc.calculate()
    postgres_db_session.commit()

    # Verify net change
    final_count = initial_population.count()
    expected_change = births - deaths + migration

    assert final_count == initial_count + expected_change


def test_multiple_calculators_different_cohorts(
    postgres_db_session, initial_population
):
    """Test multiple calculators on different cohorts"""
    initial_count = initial_population.count()

    # High birth rate for Catholics
    catholic_births = BirthCalculator(
        postgres_db_session,
        rate=30.0,
        query_filters={"religious_background": ReligiousBackground.CATHOLIC},
    )

    # Lower birth rate for Protestants
    protestant_births = BirthCalculator(
        postgres_db_session,
        rate=15.0,
        query_filters={"religious_background": ReligiousBackground.PROTESTANT},
    )

    catholic_count = catholic_births.calculate()
    protestant_count = protestant_births.calculate()
    postgres_db_session.commit()

    total_births = catholic_count + protestant_count
    assert initial_population.count() == initial_count + total_births


def test_internal_migration_moves_persons(postgres_db_session, initial_population):
    """Test persons are relocated to destination, population size unchanged"""
    initial_count = initial_population.count()

    calculator = InternalMigrationCalculator(
        postgres_db_session,
        rate=100.0,
        destination=Location.LISBURN_CASTLEREAGH,
        query_filters={"location": Location.BELFAST},
    )
    moved = calculator.calculate()
    postgres_db_session.commit()

    assert moved == 5  # 100/1000 * 50 = 5
    assert initial_population.count() == initial_count  # no population change

    relocated = (
        postgres_db_session.query(Person)
        .filter(Person.location == Location.LISBURN_CASTLEREAGH)
        .count()
    )
    assert relocated == moved


def test_internal_migration_no_population_change(
    postgres_db_session, initial_population
):
    """Test internal migration never adds or removes persons"""
    initial_count = initial_population.count()

    calculator = InternalMigrationCalculator(
        postgres_db_session,
        rate=500.0,
        destination=Location.MID_ULSTER,
        query_filters={"age_min": 20, "age_max": 40},
    )
    calculator.calculate()
    postgres_db_session.commit()

    assert initial_population.count() == initial_count


def test_internal_migration_empty_cohort(postgres_db_session, initial_population):
    """Test internal migration with no matching cohort returns 0"""
    calculator = InternalMigrationCalculator(
        postgres_db_session,
        rate=100.0,
        destination=Location.FERMANAGH_OMAGH,
        query_filters={"location": Location.FERMANAGH_OMAGH},
    )
    moved = calculator.calculate()

    assert moved == 0


def test_internal_migration_age_filter(postgres_db_session, initial_population):
    """Test young adults (18-35) migrate to Belfast from rural area"""
    calculator = InternalMigrationCalculator(
        postgres_db_session,
        rate=200.0,
        destination=Location.ANTRIM_AND_NEWTOWNABBEY,
        query_filters={
            "location": Location.DERRY_STRABANE,
            "age_min": 18,
            "age_max": 35,
        },
    )
    moved = calculator.calculate()
    postgres_db_session.commit()

    assert moved >= 0
    assert isinstance(moved, int)
