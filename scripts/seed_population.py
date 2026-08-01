"""Create a reproducible, full-scale baseline population database."""

import argparse
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.core.models import Origin, Person, ReligiousBackground  # noqa: E402
from src.ni_model.data.population_generator import (  # noqa: E402
    calibrated_age_bands,
    iter_population,
)

_HISTORICAL_TOTAL = 1_536_065
_HISTORICAL_AGE_BANDS = calibrated_age_bands(
    [
        (0, 14, 456_997 / _HISTORICAL_TOTAL),
        (15, 39, 512_242 / _HISTORICAL_TOTAL),
        (40, 64, 400_842 / _HISTORICAL_TOTAL),
        (65, 110, 165_984 / _HISTORICAL_TOTAL),
    ]
)
_HISTORICAL_ORIGIN_WEIGHTS = [
    (Origin.NI, 0.94),
    (Origin.ROI, 0.025),
    (Origin.GB, 0.03),
    (Origin.OTHER, 0.005),
]

PROFILES = {
    "current": {
        "size": 1_903_175,
        "reference_year": 2021,
        "religion_weights": None,
        "age_bands": None,
        "origin_weights": None,
        "status": "Census 2021 sourced baseline",
    },
    "historical": {
        "size": 1_536_065,
        "reference_year": 1971,
        "religion_weights": [
            (ReligiousBackground.CATHOLIC, 0.311),
            (ReligiousBackground.PROTESTANT, 0.649),
            (ReligiousBackground.OTHER, 0.020),
            (ReligiousBackground.NONE, 0.020),
        ],
        "age_bands": _HISTORICAL_AGE_BANDS,
        "origin_weights": _HISTORICAL_ORIGIN_WEIGHTS,
        "status": (
            "Best-effort 1971 baseline: exact Census total and broad-age marginals; "
            "community and origin are documented estimates; modern LGD spatial "
            "patterns are retained because equivalent 1971 LGDs did not exist"
        ),
    },
}


def _mapping(person: Person, person_number: int) -> dict:
    return {
        "id": uuid.uuid4(),
        "person_number": person_number,
        "run_id": None,
        "age": person.age,
        "birth_year": person.birth_year,
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
        for person_number, person in enumerate(
            iter_population(
                population_size,
                seed=42,
                religion_weights=profile["religion_weights"],
                reference_year=profile["reference_year"],
                age_bands=profile["age_bands"],
                origin_weights=profile["origin_weights"],
            ),
            start=1,
        ):
            batch.append(_mapping(person, person_number))
            if len(batch) == batch_size:
                session.bulk_insert_mappings(Person, batch)
                session.commit()
                batch = []
        if batch:
            session.bulk_insert_mappings(Person, batch)
            session.commit()
        if engine.dialect.name == "postgresql":
            session.execute(
                text(
                    "SELECT setval('persons_person_number_seq', "
                    "COALESCE((SELECT max(person_number) FROM persons), 0) + 1, false)"
                )
            )
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
