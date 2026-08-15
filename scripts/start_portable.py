"""Initialize the lightweight metadata store and start the Parquet API."""

import os
import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.core import models  # noqa: E402,F401
from src.ni_model.core.database import Base, engine  # noqa: E402
from src.ni_model.core.deployment import baseline_path  # noqa: E402


def main() -> None:
    missing = [
        profile
        for profile in ("current", "historical")
        if not baseline_path(profile).is_file()
    ]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(
            f"Missing Parquet baseline(s): {names}. Run "
            "python scripts/build_parquet_baselines.py before starting."
        )
    Base.metadata.create_all(bind=engine)
    uvicorn.run(
        "src.ni_model.api.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
