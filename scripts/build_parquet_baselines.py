"""Build deterministic full-population Parquet baselines without a database."""

import argparse
import sys
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed_population import PROFILES  # noqa: E402
from src.ni_model.data.population_generator import iter_population  # noqa: E402

SCHEMA = pa.schema(
    [
        ("person_id", pa.binary(16)),
        ("person_number", pa.int64()),
        ("birth_year", pa.int16()),
        ("religious_background", pa.string()),
        ("probable_community", pa.string()),
        ("gender", pa.string()),
        ("education_level", pa.string()),
        ("location", pa.string()),
        ("origin", pa.string()),
    ]
)
IDENTITY_NAMESPACE = uuid.UUID("a74113e1-ef3a-4785-9f4b-01708021b082")


def _record(profile_name: str, person_number: int, person) -> dict:
    identity = uuid.uuid5(IDENTITY_NAMESPACE, f"{profile_name}:{person_number}")
    return {
        "person_id": identity.bytes,
        "person_number": person_number,
        "birth_year": person.birth_year,
        "religious_background": person.religious_background.value,
        "probable_community": person.probable_community.value,
        "gender": person.gender.value,
        "education_level": person.education_level.value,
        "location": person.location.value,
        "origin": person.origin.value,
    }


def build_profile(
    profile_name: str, output_dir: Path, batch_size: int = 50_000, size: int = None
) -> Path:
    profile = PROFILES[profile_name]
    population_size = profile["size"] if size is None else size
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{profile_name}.parquet"
    temporary = target.with_suffix(".parquet.tmp")
    writer = pq.ParquetWriter(temporary, SCHEMA, compression="zstd")
    batch = []
    try:
        population = iter_population(
            population_size,
            seed=42,
            religion_weights=profile["religion_weights"],
            reference_year=profile["reference_year"],
            age_bands=profile["age_bands"],
            origin_weights=profile["origin_weights"],
        )
        for person_number, person in enumerate(population, start=1):
            batch.append(_record(profile_name, person_number, person))
            if len(batch) >= batch_size:
                writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
                batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=SCHEMA))
    finally:
        writer.close()
    temporary.replace(target)
    print(f"Built {target} with {population_size:,} residents")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profiles", nargs="*", choices=PROFILES)
    parser.add_argument("--output-dir", type=Path, default=Path("data/baselines"))
    parser.add_argument("--batch-size", type=int, default=50_000)
    parser.add_argument("--size", type=int, help="development-only size override")
    args = parser.parse_args()
    if args.batch_size < 1 or (args.size is not None and args.size < 1):
        parser.error("batch size and optional size must be positive")
    for profile_name in args.profiles or PROFILES:
        build_profile(profile_name, args.output_dir, args.batch_size, args.size)


if __name__ == "__main__":
    main()
