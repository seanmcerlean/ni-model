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
            "simulation_checkpoints",
            "simulation_person_events",
            "simulation_runs",
            "simulation_snapshots",
            "alembic_version",
        }.issubset(inspector.get_table_names())
        person_columns = {column["name"] for column in inspector.get_columns("persons")}
        assert {
            "run_id",
            "person_number",
            "birth_year",
            "baseline_profile",
        }.issubset(person_columns)
        run_columns = {
            column["name"] for column in inspector.get_columns("simulation_runs")
        }
        assert "owner_key" in run_columns
        assert {
            "baseline_profile",
            "represented_population_count",
            "population_scale",
        }.issubset(run_columns)
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT location, person_number FROM persons")
            ).one()
        assert row.location == "BELFAST"
        assert row.person_number == 1

        command.downgrade(config, "base")
        assert inspect(engine).get_table_names() == ["alembic_version"]
        engine.dispose()
