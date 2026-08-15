"""Deployment-mode configuration shared by API and simulation storage."""

import os
from enum import Enum
from pathlib import Path


class DeploymentMode(str, Enum):
    STATIC = "static"
    PARQUET = "parquet"
    FULL = "full"


def deployment_mode() -> DeploymentMode:
    """Return the configured mode, defaulting to the portable Parquet runtime."""
    value = os.getenv("NI_MODEL_MODE", DeploymentMode.PARQUET.value).lower()
    try:
        return DeploymentMode(value)
    except ValueError as exc:
        choices = ", ".join(mode.value for mode in DeploymentMode)
        raise RuntimeError(f"NI_MODEL_MODE must be one of: {choices}") from exc


def baseline_path(profile: str) -> Path:
    root = Path(os.getenv("BASELINE_PARQUET_DIR", "data/baselines"))
    return root / f"{profile}.parquet"
