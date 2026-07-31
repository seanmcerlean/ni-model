"""Create a reproducible, full-scale baseline population database."""

import argparse
import os
import sys
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.core.models import Person, ReligiousBackground  # noqa: E402
from src.ni_model.data.population_generator import iter_population  # noqa: E402

PROFILES = {
    "current": {
        "size": 1_903_175,
        "religion_weights": None,
        "status": "Census 2021 sourced baseline",
    },
    "historical": {
        "size": 1_536_065,
        "religion_weights": [
            (ReligiousBackground.CATHOLIC, 0.311),
            (ReligiousBackground.PROTESTANT, 0.649),
            (ReligiousBackground.OTHER, 0.020),
            (ReligiousBackground.NONE, 0.020),
        ],
        "status": (
            "Best-effort 1971-scale representative estimate: community background "
            "matches the legacy NI-wide estimate and borrows the 2021 LGD spatial "
            "pattern; age, LGD, origin and education use current distributions"
        ),
    },
}


def _mapping(person: Person) -> dict:
    return {
        "id": uuid.uuid4(),
        "run_id": None,
        "age": person.age,
        "religious_background": person.religious_background,
        "gender": person.gender,
        "education_level": person.education_level,
        "location": person.location,
        "origin": person.origin,
    }


def seed(
    database_url: str,
    profile_name: str,
    batch_size: int,
    replace: bool,
    size: int = None,
) -> int:
    profile = PROFILES[profile_name]
    population_size = profile["size"] if size is None else size
    alembic = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic, "head")

    engine = create_engine(database_url)
    session = sessionmaker(bind=engine)()
    try:
        existing = session.query(Person).filter(Person.run_id.is_(None)).count()
        if existing and not replace:
            print(f"Baseline already contains {existing:,} residents; nothing changed.")
            return existing
        if replace:
            session.query(Person).filter(Person.run_id.is_(None)).delete(
                synchronize_session=False
            )
            session.commit()

        batch = []
        for person in iter_population(
            population_size, seed=42, religion_weights=profile["religion_weights"]
        ):
            batch.append(_mapping(person))
            if len(batch) == batch_size:
                session.bulk_insert_mappings(Person, batch)
                session.commit()
                batch = []
        if batch:
            session.bulk_insert_mappings(Person, batch)
            session.commit()
        print(f"Seeded {population_size:,} residents. {profile['status']}")
        return population_size
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--batch-size", type=int, default=25_000)
    parser.add_argument(
        "--size", type=int, help="development smoke-test override; omit for full scale"
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.size is not None and args.size < 0:
        parser.error("--size must be non-negative")
    seed(args.database_url, args.profile, args.batch_size, args.replace, args.size)


if __name__ == "__main__":
    main()
