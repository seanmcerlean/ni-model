import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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


@pytest.fixture
def test_db_session():
    """Create test database session"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()


@pytest.fixture
def person_repo(test_db_session):
    """Create PersonRepository with test database"""
    return PersonRepository(db=test_db_session)


@pytest.fixture
def sample_person():
    """Create sample person for testing"""
    return Person(
        age=30,
        religious_background=ReligiousBackground.CATHOLIC,
        gender=Gender.MALE,
        education_level=EducationLevel.TERTIARY,
        location=Location.BELFAST_NORTH,
        origin=Origin.NI,
    )


def test_create_person(person_repo, sample_person):
    """Test creating a person"""
    created_person = person_repo.create(sample_person)

    assert created_person.id is not None
    assert created_person.age == 30
    assert created_person.location == Location.BELFAST_NORTH


def test_get_person_by_id(person_repo, sample_person):
    """Test retrieving person by ID"""
    created_person = person_repo.create(sample_person)
    retrieved_person = person_repo.get_by_id(created_person.id)

    assert retrieved_person is not None
    assert retrieved_person.id == created_person.id
    assert retrieved_person.age == 30


def test_get_person_by_nonexistent_id(person_repo):
    """Test retrieving person with non-existent ID"""
    fake_id = uuid.uuid4()
    person = person_repo.get_by_id(fake_id)

    assert person is None


def test_update_person(person_repo, sample_person):
    """Test updating person"""
    created_person = person_repo.create(sample_person)

    updated_person = person_repo.update(created_person.id, age=35)

    assert updated_person.age == 35
    assert updated_person.religious_background == ReligiousBackground.CATHOLIC


def test_delete_person(person_repo, sample_person):
    """Test deleting person"""
    created_person = person_repo.create(sample_person)

    deleted = person_repo.delete(created_person.id)
    assert deleted is True

    retrieved_person = person_repo.get_by_id(created_person.id)
    assert retrieved_person is None


def test_bulk_create_persons(person_repo):
    """Test bulk creating persons"""
    persons = [
        Person(
            age=20 + i,
            religious_background=ReligiousBackground.PROTESTANT,
            gender=Gender.FEMALE,
            education_level=EducationLevel.SECONDARY,
            location=Location.DERRY,
            origin=Origin.NI,
        )
        for i in range(100)
    ]

    created_persons = person_repo.bulk_create(persons)

    assert len(created_persons) == 100
    assert person_repo.count() == 100


def test_get_by_location(person_repo):
    """Test getting persons by location"""
    for i in range(10):
        person = Person(
            age=25,
            religious_background=ReligiousBackground.CATHOLIC,
            gender=Gender.MALE,
            education_level=EducationLevel.TERTIARY,
            location=Location.BELFAST_NORTH if i < 5 else Location.DERRY,
            origin=Origin.NI,
        )
        person_repo.create(person)

    belfast_persons = person_repo.get_by_location(Location.BELFAST_NORTH)
    derry_persons = person_repo.get_by_location(Location.DERRY)

    assert len(belfast_persons) == 5
    assert len(derry_persons) == 5


def test_get_by_age_range(person_repo):
    """Test getting persons by age range"""
    for age in [20, 25, 30, 35, 40, 45]:
        person = Person(
            age=age,
            religious_background=ReligiousBackground.CATHOLIC,
            gender=Gender.MALE,
            education_level=EducationLevel.TERTIARY,
            location=Location.BELFAST_NORTH,
            origin=Origin.NI,
        )
        person_repo.create(person)

    young_adults = person_repo.get_by_age_range(20, 30)
    middle_aged = person_repo.get_by_age_range(35, 45)

    assert len(young_adults) == 3  # ages 20, 25, 30
    assert len(middle_aged) == 3  # ages 35, 40, 45


def test_demographics_summary(person_repo):
    """Test demographics summary"""
    persons = [
        Person(
            age=25,
            religious_background=ReligiousBackground.CATHOLIC,
            gender=Gender.MALE,
            education_level=EducationLevel.TERTIARY,
            location=Location.BELFAST_NORTH,
            origin=Origin.NI,
        ),
        Person(
            age=35,
            religious_background=ReligiousBackground.PROTESTANT,
            gender=Gender.FEMALE,
            education_level=EducationLevel.SECONDARY,
            location=Location.DERRY,
            origin=Origin.NI,
        ),
        Person(
            age=45,
            religious_background=ReligiousBackground.CATHOLIC,
            gender=Gender.MALE,
            education_level=EducationLevel.PRIMARY,
            location=Location.BELFAST_NORTH,
            origin=Origin.ROI,
        ),
    ]

    person_repo.bulk_create(persons)

    summary = person_repo.get_demographics_summary()

    assert summary["total_population"] == 3
    assert summary["age_stats"]["average"] == 35.0
    assert summary["age_stats"]["minimum"] == 25
    assert summary["age_stats"]["maximum"] == 45
    assert summary["religious_breakdown"]["catholic"] == 2
    assert summary["religious_breakdown"]["protestant"] == 1
    assert summary["gender_breakdown"]["male"] == 2
    assert summary["gender_breakdown"]["female"] == 1


def test_repository_session_cleanup(person_repo):
    """Test repository session cleanup"""
    person_repo.close()
