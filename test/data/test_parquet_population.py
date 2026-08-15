import uuid

import polars as pl

from src.ni_model.data import parquet_population
from src.ni_model.simulation.columnar_worker import COLUMN_TYPES


def test_parquet_baseline_is_loaded_and_cached(monkeypatch, tmp_path):
    path = tmp_path / "current.parquet"
    pl.DataFrame(
        {
            "person_id": [uuid.uuid4().bytes],
            "person_number": [1],
            "birth_year": [1990],
            "religious_background": ["catholic"],
            "probable_community": ["catholic"],
            "gender": ["female"],
            "education_level": ["tertiary"],
            "location": ["belfast"],
            "origin": ["ni"],
        }
    ).cast(COLUMN_TYPES).write_parquet(path)
    monkeypatch.setenv("BASELINE_PARQUET_DIR", str(tmp_path))
    parquet_population.baseline_frame.cache_clear()

    first = parquet_population.baseline_frame()
    second = parquet_population.baseline_frame()

    assert first.height == 1
    assert first is second
