"""Read-only population access for the portable Parquet deployment."""

from functools import lru_cache

import polars as pl

from ..core.deployment import baseline_path


@lru_cache(maxsize=2)
def baseline_frame(profile: str = "current") -> pl.DataFrame:
    path = baseline_path(profile)
    if not path.is_file():
        raise FileNotFoundError(f"Parquet baseline is missing: {path}")
    return pl.read_parquet(path)
