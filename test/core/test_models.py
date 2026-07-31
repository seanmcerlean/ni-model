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


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()


def test_person_model_creation(in_memory_db):
    """Test Person model can be created and saved"""
    person = Person(
        age=35,
        religious_background=ReligiousBackground.CATHOLIC,
        gender=Gender.FEMALE,
        education_level=EducationLevel.TERTIARY,
        location=Location.BELFAST,
        origin=Origin.NI,
    )

    in_memory_db.add(person)
    in_memory_db.commit()

    assert person.id is not None
    assert isinstance(person.id, uuid.UUID)


def test_person_model_constraints(in_memory_db):
    """Test Person model field constraints"""
    person = Person(
        age=25,
        religious_background=ReligiousBackground.PROTESTANT,
        gender=Gender.MALE,
        education_level=EducationLevel.SECONDARY,
        location=Location.DERRY_STRABANE,
        origin=Origin.NI,
    )

    in_memory_db.add(person)
    in_memory_db.commit()

    retrieved = in_memory_db.query(Person).filter_by(age=25).first()
    assert retrieved.religious_background == ReligiousBackground.PROTESTANT
    assert retrieved.gender == Gender.MALE
    assert retrieved.education_level == EducationLevel.SECONDARY
    assert retrieved.location == Location.DERRY_STRABANE
    assert retrieved.origin == Origin.NI


def test_person_model_enums():
    """Test enum values are correct"""
    assert ReligiousBackground.CATHOLIC.value == "catholic"
    assert Gender.FEMALE.value == "female"
    assert EducationLevel.TERTIARY.value == "tertiary"
    assert Location.BELFAST.value == "belfast"
    assert Origin.NI.value == "ni"


def test_bulk_person_creation(in_memory_db):
    """Test bulk creation of Person records"""
    persons = [
        Person(
            age=20 + (i % 60),
            religious_background=(
                ReligiousBackground.CATHOLIC
                if i % 2 == 0
                else ReligiousBackground.PROTESTANT
            ),
            gender=Gender.MALE if i % 2 == 0 else Gender.FEMALE,
            education_level=EducationLevel.SECONDARY,
            location=Location.BELFAST if i % 2 == 0 else Location.DERRY_STRABANE,
            origin=Origin.NI,
        )
        for i in range(1000)
    ]

    in_memory_db.add_all(persons)
    in_memory_db.commit()

    count = in_memory_db.query(Person).count()
    assert count == 1000
