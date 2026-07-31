from sqlalchemy import create_engine, inspect, text
from testcontainers.postgres import PostgresContainer

from alembic import command
from alembic.config import Config


def test_initial_migration_upgrades_and_downgrades_clean_database():
    with PostgresContainer("postgres:15") as postgres:
        url = postgres.get_connection_url()
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)

        command.upgrade(config, "20260730_0001")

        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(text("""INSERT INTO persons
                    (id, age, religious_background, gender, education_level,
                     location, origin)
                    VALUES
                    ('00000000-0000-0000-0000-000000000001', 30, 'CATHOLIC',
                     'FEMALE', 'TERTIARY', 'BELFAST_WEST', 'NI')"""))

        command.upgrade(config, "head")
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
        with engine.connect() as connection:
            location = connection.execute(text("SELECT location FROM persons")).scalar()
        assert location == "BELFAST"

        command.downgrade(config, "base")
        assert inspect(engine).get_table_names() == ["alembic_version"]
        engine.dispose()
