from sqlalchemy import create_engine, inspect
from testcontainers.postgres import PostgresContainer

from alembic import command
from alembic.config import Config


def test_initial_migration_upgrades_and_downgrades_clean_database():
    with PostgresContainer("postgres:15") as postgres:
        url = postgres.get_connection_url()
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)

        command.upgrade(config, "head")

        engine = create_engine(url)
        inspector = inspect(engine)
        assert {
            "persons",
            "simulation_runs",
            "simulation_snapshots",
            "alembic_version",
        }.issubset(inspector.get_table_names())
        assert "run_id" in {
            column["name"] for column in inspector.get_columns("persons")
        }

        command.downgrade(config, "base")
        assert inspect(engine).get_table_names() == ["alembic_version"]
        engine.dispose()
