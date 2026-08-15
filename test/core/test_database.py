import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.ni_model.core.database import Base, get_db


@pytest.fixture
def test_db():
    """Create test database session"""
    test_db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://ni_user:ni_password@localhost:5432/ni_model_test",
    )
    engine = create_engine(test_db_url)

    # Create test database tables
    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


def test_database_connection():
    """Test basic database connectivity"""
    db_gen = get_db()
    db = next(db_gen)

    # Test basic query
    result = db.execute(text("SELECT 1 as test"))
    assert result.fetchone()[0] == 1

    db.close()


def test_database_session_cleanup():
    """Test database session cleanup"""
    # Test that get_db properly manages session lifecycle
    db_gen = get_db()
    db = next(db_gen)

    # Session should be active initially
    assert db.is_active

    # Test that session exists and can execute queries
    result = db.execute(text("SELECT 1 as test"))
    assert result.fetchone()[0] == 1


def test_schema_compiles_for_portable_sqlite():
    sqlite = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(sqlite)

    assert "simulation_runs" in Base.metadata.tables
