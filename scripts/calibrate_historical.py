"""Search bounded causal inputs against historical Census checkpoints."""

import argparse
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.calibration import (  # noqa: E402
    HistoricalCalibration,
    HistoricalParameters,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--sample-size", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--parameters-file", type=Path)
    args = parser.parse_args()
    calibration = HistoricalCalibration(sample_size=args.sample_size, seed=args.seed)
    if args.parameters_file:
        with args.parameters_file.open(encoding="utf-8") as source:
            parameters = HistoricalParameters(**yaml.safe_load(source)["parameters"])
        result = calibration.evaluate_ensemble(parameters, args.replicates)
    else:
        result = calibration.search(
            args.iterations,
            workers=args.workers,
            replicates=args.replicates,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
