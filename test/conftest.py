"""Shared infrastructure for database-backed tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from src.ni_model.core.database import Base


@pytest.fixture(scope="session")
def postgres_container():
    """Start one PostgreSQL container for the full test session."""
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def postgres_engine(postgres_container):
    engine = create_engine(postgres_container.get_connection_url())
    yield engine
    engine.dispose()


def _database_session(engine):
    """Provide the same per-test schema isolation as the original fixtures."""
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def postgres_db_session(postgres_engine):
    yield from _database_session(postgres_engine)


@pytest.fixture
def db_session(postgres_engine):
    yield from _database_session(postgres_engine)
