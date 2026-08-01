import json

import pytest
from sqlalchemy import text

from src.ni_model.simulation.performance import PerformanceRecorder


def test_recorder_attributes_time_and_sql_to_stages(postgres_engine, tmp_path):
    with PerformanceRecorder(postgres_engine) as recorder:
        with recorder.stage("example"):
            with postgres_engine.connect() as connection:
                connection.execute(text("SELECT 1"))

    report = recorder.report({"seed": 42})
    example = report["stages"]["example"]
    assert report["metadata"] == {"seed": 42}
    assert report["peak_rss_kib"] > 0
    assert example["calls"] == 1
    assert example["sql_statements"] == 1
    assert example["wall_seconds"] >= 0
    assert example["wall_median_seconds"] >= 0
    assert example["wall_p95_seconds"] >= example["wall_median_seconds"]
    assert example["cpu_seconds"] >= 0
    assert report["total_wall_seconds"] >= example["wall_seconds"]
    assert report["unattributed_wall_seconds"] >= 0

    output = tmp_path / "benchmark.json"
    recorder.write_json(output, {"seed": 42})
    assert json.loads(output.read_text(encoding="utf-8"))["metadata"]["seed"] == 42


def test_recorder_rejects_nested_stages(postgres_engine):
    recorder = PerformanceRecorder(postgres_engine)
    with recorder.stage("outer"):
        with pytest.raises(RuntimeError, match="cannot be nested"):
            with recorder.stage("inner"):
                pass


def test_recorder_reports_median_and_nearest_rank_p95(postgres_engine, monkeypatch):
    clock = iter([0.0, 0.0, 1.0, 1.0, 3.0, 3.0])
    monkeypatch.setattr(
        "src.ni_model.simulation.performance.time.perf_counter", lambda: next(clock)
    )
    monkeypatch.setattr(
        "src.ni_model.simulation.performance.time.process_time", lambda: 0
    )

    with PerformanceRecorder(postgres_engine) as recorder:
        with recorder.stage("sample"):
            pass
        with recorder.stage("sample"):
            pass

    sample = recorder.report()["stages"]["sample"]
    assert sample["wall_median_seconds"] == 1.5
    assert sample["wall_p95_seconds"] == 2.0
