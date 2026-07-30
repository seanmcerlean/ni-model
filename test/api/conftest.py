import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from src.ni_model.api.app import create_app
from src.ni_model.api.routes.population import get_db
from src.ni_model.core.database import Base
from src.ni_model.core.models import (
    EducationLevel,
    Gender,
    Location,
    Origin,
    Person,
    ReligiousBackground,
)


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture
def db_session(postgres_container):
    engine = create_engine(postgres_container.get_connection_url())
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def populated_db(db_session):
    """50 Catholics in Belfast North, 30 Protestants in Derry, 20 Other in Antrim"""
    persons = (
        [
            Person(
                age=25 + i,
                religious_background=ReligiousBackground.CATHOLIC,
                gender=Gender.FEMALE,
                education_level=EducationLevel.TERTIARY,
                location=Location.BELFAST_NORTH,
                origin=Origin.NI,
            )
            for i in range(50)
        ]
        + [
            Person(
                age=35 + i,
                religious_background=ReligiousBackground.PROTESTANT,
                gender=Gender.MALE,
                education_level=EducationLevel.SECONDARY,
                location=Location.DERRY,
                origin=Origin.NI,
            )
            for i in range(30)
        ]
        + [
            Person(
                age=45 + i,
                religious_background=ReligiousBackground.OTHER,
                gender=Gender.MALE,
                education_level=EducationLevel.PRIMARY,
                location=Location.ANTRIM,
                origin=Origin.GB,
            )
            for i in range(20)
        ]
    )
    db_session.add_all(persons)
    db_session.commit()
    return db_session


@pytest.fixture
def client(populated_db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: populated_db
    return TestClient(app)
