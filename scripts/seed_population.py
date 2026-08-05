"""Create a reproducible, full-scale baseline population database."""

import argparse
import math
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import case, create_engine, func, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.core.models import (  # noqa: E402
    Location,
    Origin,
    Person,
    ReligiousBackground,
)
from src.ni_model.data.population_generator import (  # noqa: E402
    calibrated_age_bands,
    iter_population,
)
from src.ni_model.data.probable_community import (  # noqa: E402
    NONE_PROBABLE_CATHOLIC_BY_LOCATION,
    NONE_PROBABLE_OTHER,
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
        "community_shares": {
            ReligiousBackground.CATHOLIC: 869_749 / 1_903_167,
            ReligiousBackground.PROTESTANT: 827_541 / 1_903_167,
            ReligiousBackground.OTHER: 28_516 / 1_903_167,
            ReligiousBackground.NONE: 177_361 / 1_903_167,
        },
        "age_shares": (
            (0, 14, 365_212 / 1_903_167),
            (15, 39, 594_363 / 1_903_167),
            (40, 64, 617_124 / 1_903_167),
            (65, 110, 326_468 / 1_903_167),
        ),
        "background_65_plus": {
            ReligiousBackground.CATHOLIC: 123_700 / 869_749,
            ReligiousBackground.PROTESTANT: 193_314 / 827_541,
        },
    },
    "historical": {
        "size": 1_512_500,
        "reference_year": 1969,
        "religion_weights": [
            (ReligiousBackground.CATHOLIC, 0.33830865933327126),
            (ReligiousBackground.PROTESTANT, 0.6451932760847402),
            (ReligiousBackground.OTHER, 0.007642683798507095),
            (ReligiousBackground.NONE, 0.008855380783481519),
        ],
        "age_bands": _HISTORICAL_AGE_BANDS,
        "origin_weights": _HISTORICAL_ORIGIN_WEIGHTS,
        "status": (
            "Best-effort 1969 baseline: exact NISRA total and 1971 Census broad-age "
            "marginals; "
            "community is a causally calibrated estimate (fit to 2001/2011, with "
            "2021 held out) and origin is estimated; modern LGD spatial "
            "patterns are retained because equivalent 1971 LGDs did not exist"
        ),
        "community_shares": {
            ReligiousBackground.CATHOLIC: 0.33830865933327126,
            ReligiousBackground.PROTESTANT: 0.6451932760847402,
            ReligiousBackground.OTHER: 0.007642683798507095,
            ReligiousBackground.NONE: 0.008855380783481519,
        },
        "age_shares": (
            (0, 14, 456_997 / _HISTORICAL_TOTAL),
            (15, 39, 512_242 / _HISTORICAL_TOTAL),
            (40, 64, 400_842 / _HISTORICAL_TOTAL),
            (65, 110, 165_984 / _HISTORICAL_TOTAL),
        ),
        "background_65_plus": {},
    },
}


def _share_tolerance(expected: float, denominator: int) -> float:
    """Four-sigma sampling tolerance with a strict full-scale floor."""
    return max(0.002, 4 * math.sqrt(expected * (1 - expected) / denominator))


def validate_baseline(session, profile_name: str, expected_size: int) -> None:
    """Fail when a generated profile violates its defining demographic facts."""
    profile = PROFILES[profile_name]
    filters = (
        Person.run_id.is_(None),
        Person.baseline_profile == profile_name,
    )
    actual_size = session.query(func.count(Person.id)).filter(*filters).scalar() or 0
    if actual_size != expected_size:
        raise RuntimeError(
            f"{profile_name} baseline row count {actual_size:,} != {expected_size:,}"
        )
    inconsistent_birth_years = (
        session.query(func.count(Person.id))
        .filter(
            *filters,
            Person.birth_year != profile["reference_year"] - Person.age,
        )
        .scalar()
        or 0
    )
    if inconsistent_birth_years:
        raise RuntimeError(
            f"{profile_name} baseline has {inconsistent_birth_years:,} "
            "inconsistent birth years"
        )

    community_counts = dict(
        session.query(Person.religious_background, func.count(Person.id))
        .filter(*filters)
        .group_by(Person.religious_background)
        .all()
    )
    for background, expected in profile["community_shares"].items():
        actual = community_counts.get(background, 0) / actual_size
        tolerance = _share_tolerance(expected, actual_size)
        if abs(actual - expected) > tolerance:
            raise RuntimeError(
                f"{profile_name} {background.value} share {actual:.4f} outside "
                f"{expected:.4f} +/- {tolerance:.4f}"
            )

    for age_min, age_max, expected in profile["age_shares"]:
        count = (
            session.query(
                func.sum(case((Person.age.between(age_min, age_max), 1), else_=0))
            )
            .filter(*filters)
            .scalar()
            or 0
        )
        actual = count / actual_size
        tolerance = _share_tolerance(expected, actual_size)
        if abs(actual - expected) > tolerance:
            raise RuntimeError(
                f"{profile_name} age {age_min}-{age_max} share {actual:.4f} outside "
                f"{expected:.4f} +/- {tolerance:.4f}"
            )

    for background, expected in profile["background_65_plus"].items():
        denominator = community_counts.get(background, 0)
        count = (
            session.query(func.count(Person.id))
            .filter(
                *filters, Person.religious_background == background, Person.age >= 65
            )
            .scalar()
            or 0
        )
        actual = count / denominator
        tolerance = _share_tolerance(expected, denominator)
        if abs(actual - expected) > tolerance:
            raise RuntimeError(
                f"{profile_name} {background.value} age 65+ share {actual:.4f} "
                f"outside {expected:.4f} +/- {tolerance:.4f}"
            )

    if profile_name == "current":
        _validate_lgd_community_joint(session, filters)


def _validate_lgd_community_joint(session, filters) -> None:
    """Protect the Census LGD pattern and estimated None allocation."""
    reported_checks = (
        (Location.DERRY_STRABANE, ReligiousBackground.CATHOLIC, 109_131 / 150_756),
        (
            Location.MID_EAST_ANTRIM,
            ReligiousBackground.PROTESTANT,
            93_477 / 138_994,
        ),
    )
    for location, background, expected in reported_checks:
        denominator = (
            session.query(func.count(Person.id))
            .filter(*filters, Person.location == location)
            .scalar()
            or 0
        )
        count = (
            session.query(func.count(Person.id))
            .filter(
                *filters,
                Person.location == location,
                Person.religious_background == background,
            )
            .scalar()
            or 0
        )
        if denominator == 0:
            raise RuntimeError(f"current {location.value} has no seeded residents")
        tolerance = _share_tolerance(expected, denominator)
        if abs(count / denominator - expected) > tolerance:
            raise RuntimeError(
                f"current {location.value} {background.value} share outside "
                "the Census LGD tolerance"
            )

    for location in (Location.DERRY_STRABANE, Location.MID_EAST_ANTRIM):
        none_count = (
            session.query(func.count(Person.id))
            .filter(
                *filters,
                Person.location == location,
                Person.religious_background == ReligiousBackground.NONE,
            )
            .scalar()
            or 0
        )
        if not none_count:
            raise RuntimeError(f"current {location.value} has no reported None cohort")
        probable_counts = dict(
            session.query(Person.probable_community, func.count(Person.id))
            .filter(
                *filters,
                Person.location == location,
                Person.religious_background == ReligiousBackground.NONE,
            )
            .group_by(Person.probable_community)
            .all()
        )
        catholic = probable_counts.get(ReligiousBackground.CATHOLIC, 0) / none_count
        other = probable_counts.get(ReligiousBackground.OTHER, 0) / none_count
        catholic_expected = NONE_PROBABLE_CATHOLIC_BY_LOCATION[location] * (
            1 - NONE_PROBABLE_OTHER
        )
        if abs(catholic - catholic_expected) > _share_tolerance(
            catholic_expected, none_count
        ):
            raise RuntimeError(
                f"current {location.value} probable Catholic share outside tolerance"
            )
        if abs(other - NONE_PROBABLE_OTHER) > _share_tolerance(
            NONE_PROBABLE_OTHER, none_count
        ):
            raise RuntimeError(
                f"current {location.value} probable Other share outside tolerance"
            )


def _seed_action(
    existing: int, target_size: int, requested_default: bool, replace: bool
) -> str:
    """Choose a safe action without accepting a truncated production baseline."""
    if not existing:
        return "seed"
    if replace or (requested_default and existing != target_size):
        return "replace"
    return "reuse"


def _mapping(
    person: Person, person_number: int, baseline_profile: str = "current"
) -> dict:
    return {
        "id": uuid.uuid4(),
        "person_number": person_number,
        "run_id": None,
        "baseline_profile": baseline_profile,
        "age": person.age,
        "birth_year": person.birth_year,
        "religious_background": person.religious_background,
        "probable_community": person.probable_community,
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
        profile_filter = (
            Person.run_id.is_(None),
            Person.baseline_profile == profile_name,
        )
        existing = session.query(Person).filter(*profile_filter).count()
        action = _seed_action(existing, population_size, size is None, replace)
        if action == "reuse":
            validate_baseline(session, profile_name, existing)
            print(f"Baseline already contains {existing:,} residents; nothing changed.")
            return existing
        if action == "replace":
            if existing != population_size:
                print(
                    f"Replacing undersized {existing:,}-row {profile_name} baseline "
                    f"with {population_size:,} rows."
                )
            session.query(Person).filter(*profile_filter).delete(
                synchronize_session=False
            )
            session.commit()

        next_person_number = (
            session.query(func.max(Person.person_number)).scalar() or 0
        ) + 1

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
            start=next_person_number,
        ):
            batch.append(_mapping(person, person_number, profile_name))
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
        validate_baseline(session, profile_name, population_size)
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
