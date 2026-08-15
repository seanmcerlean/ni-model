import sys

from scripts import build_parquet_baselines


def test_builder_defaults_to_every_profile(monkeypatch, tmp_path):
    built = []
    monkeypatch.setattr(
        build_parquet_baselines,
        "build_profile",
        lambda profile, *args: built.append(profile),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_parquet_baselines.py", "--output-dir", str(tmp_path)],
    )

    build_parquet_baselines.main()

    assert built == list(build_parquet_baselines.PROFILES)
