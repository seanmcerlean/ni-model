from pathlib import Path

import pytest

from src.ni_model.core.deployment import DeploymentMode, baseline_path, deployment_mode


def test_deployment_defaults_to_parquet(monkeypatch):
    monkeypatch.delenv("NI_MODEL_MODE", raising=False)

    assert deployment_mode() == DeploymentMode.PARQUET


@pytest.mark.parametrize("value", ["static", "parquet", "full"])
def test_supported_deployment_modes(monkeypatch, value):
    monkeypatch.setenv("NI_MODEL_MODE", value)

    assert deployment_mode().value == value


def test_invalid_deployment_mode_fails_clearly(monkeypatch):
    monkeypatch.setenv("NI_MODEL_MODE", "database")

    with pytest.raises(RuntimeError, match="static, parquet, full"):
        deployment_mode()


def test_baseline_path_uses_configured_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("BASELINE_PARQUET_DIR", str(tmp_path))

    assert baseline_path("current") == Path(tmp_path, "current.parquet")
