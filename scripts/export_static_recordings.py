"""Record every selectable model as aggregate-only static-site JSON."""

import argparse
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ni_model.api.routes.simulation import (  # noqa: E402
    _capture_columnar_snapshot,
    simulation_models,
)
from src.ni_model.simulation.columnar_worker import (  # noqa: E402
    ColumnarSimulationWorker,
)
from src.ni_model.simulation.historical_configuration import (  # noqa: E402
    configure_historical_model_from_file,
)
from src.ni_model.simulation.voting_predictor import (  # noqa: E402
    CALIBRATIONS,
    VotingPredictor,
)

SCHEMA_VERSION = 1
STATIC_SEEDS = (1180, 1690, 1921, 1969)


def _load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        config = yaml.safe_load(source) or {}
    return configure_historical_model_from_file(config, path)


def _frame(baseline_dir: Path, profile: str) -> pl.DataFrame:
    path = baseline_dir / f"{profile}.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"missing baseline: {path}")
    return pl.read_parquet(path)


def _prediction(rows, reference_rows, calibration: str, basis: str) -> dict:
    predictor = VotingPredictor(
        None,
        calibration=calibration,
        aggregate_rows=rows,
        total_population=sum(row.count for row in rows),
        custom_reference_rows=reference_rows,
        community_basis=basis,
    )
    return {**predictor.predict(), "by_location": predictor.predict_by_location()}


def export_recordings(
    baseline_dir: Path, output_dir: Path, selected_model_ids: set[str] | None = None
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_summaries = simulation_models()
    seed_by_model = {
        model.id: seed
        for model, seed in zip(model_summaries, STATIC_SEEDS, strict=True)
    }
    selected_summaries = [
        model
        for model in model_summaries
        if not selected_model_ids or model.id in selected_model_ids
    ]
    missing = (selected_model_ids or set()) - {model.id for model in model_summaries}
    if missing:
        raise ValueError(f"unknown model ids: {', '.join(sorted(missing))}")

    if selected_model_ids:
        manifest_path = output_dir / "manifest.json"
        existing_manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {"scenarios": []}
        )
        selected_paths = {model.path for model in selected_summaries}
        scenarios = [
            scenario
            for scenario in existing_manifest["scenarios"]
            if scenario["model_path"] not in selected_paths
        ]
    else:
        for stale_recording in output_dir.glob("*.json"):
            stale_recording.unlink()
        scenarios = []

    current_reference = ColumnarSimulationWorker(
        _frame(baseline_dir, "current"), {}, uuid.uuid4(), seed=42
    ).voting_rows(2021)

    frames = {
        profile: _frame(baseline_dir, profile) for profile in ("current", "historical")
    }

    for summary in selected_summaries:
        seed = seed_by_model[summary.id]
        model_path = PROJECT_ROOT / summary.path
        config = _load_config(model_path)
        profile = config.get("baseline_profile", "current")
        start_year = config.get("default_start_year") or config.get("baseline_year")
        start_year = int(start_year or 2021)
        end_year = int(config.get("default_end_year") or 2050)
        baseline_population_size = frames[profile].height

        run_id = uuid.uuid5(uuid.NAMESPACE_URL, f"ni-model:{summary.id}:{seed}")
        worker = ColumnarSimulationWorker(frames[profile], config, run_id, seed=seed)
        snapshots = []
        for year in range(start_year, end_year + 1):
            result = worker.run_year(year)
            snapshot = _capture_columnar_snapshot(
                worker, run_id, year, result, None, population_scale=1.0
            ).model_dump(mode="json")
            rows = worker.voting_rows(year)
            snapshot["voting_predictions"] = {
                f"{calibration}:{basis}": _prediction(
                    rows, current_reference, calibration, basis
                )
                for calibration in CALIBRATIONS
                for basis in ("reported", "probable")
            }
            snapshots.append(snapshot)

        scenario_id = f"{summary.id}-seed-{seed}"
        asset_name = f"{scenario_id}.json"
        scenario = {
            "id": scenario_id,
            "model_path": summary.path,
            "asset": f"/recordings/{asset_name}",
            "seed": seed,
            "start_year": start_year,
            "end_year": end_year,
            "population_size": baseline_population_size,
            "final_population_size": worker.population.height,
        }
        payload = {"scenario": scenario, "snapshots": snapshots}
        (output_dir / asset_name).write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        scenarios.append(scenario)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "models_hash": hashlib.sha256(
            "".join(
                (PROJECT_ROOT / model.path).read_text(encoding="utf-8")
                for model in model_summaries
            ).encode()
        ).hexdigest(),
        "models": [model.model_dump(mode="json") for model in model_summaries],
        "scenarios": scenarios,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":")), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=Path("data/baselines"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("frontend/public/recordings")
    )
    parser.add_argument(
        "--model-id",
        action="append",
        dest="model_ids",
        help="Regenerate only this model while preserving other manifest scenarios.",
    )
    args = parser.parse_args()
    export_recordings(
        args.baseline_dir,
        args.output_dir,
        set(args.model_ids) if args.model_ids else None,
    )


if __name__ == "__main__":
    main()
