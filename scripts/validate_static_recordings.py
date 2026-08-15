"""Validate static recordings against all current source and baseline inputs."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_static_recordings import (  # noqa: E402
    SCHEMA_VERSION,
    application_version,
    recording_input_manifest,
)
from src.ni_model.api.routes.simulation import simulation_models  # noqa: E402


def validation_errors(baseline_dir: Path, output_dir: Path) -> list[str]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"manifest.json cannot be read: {exc}"]

    models = simulation_models()
    expected_paths = {model.path for model in models}
    expected_inputs = recording_input_manifest(baseline_dir, models)
    errors = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("snapshot schema version is stale")
    if manifest.get("application_version") != application_version():
        errors.append("application version is stale")
    if (
        manifest.get("recording_inputs_hash")
        != expected_inputs["recording_inputs_hash"]
    ):
        errors.append("recording source or baseline inputs have changed")
    if manifest.get("models") != [model.model_dump(mode="json") for model in models]:
        errors.append("recorded model catalogue is stale")

    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        return [*errors, "scenario list is missing"]
    scenario_paths = [scenario.get("model_path") for scenario in scenarios]
    if len(scenario_paths) != len(set(scenario_paths)):
        errors.append("a model has duplicate scenarios")
    if set(scenario_paths) != expected_paths:
        errors.append("scenario coverage does not match selectable models")

    for scenario in scenarios:
        asset = scenario.get("asset")
        if (
            not isinstance(asset, str)
            or not asset.startswith("/recordings/")
            or Path(asset).name != asset.removeprefix("/recordings/")
        ):
            errors.append(f"invalid scenario asset path: {asset!r}")
            continue
        asset_path = output_dir / Path(asset).name
        if not asset_path.is_file():
            errors.append(f"recording is missing: {asset_path.name}")
            continue
        try:
            payload = json.loads(asset_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"recording cannot be read ({asset_path.name}): {exc}")
            continue
        if payload.get("scenario") != scenario:
            errors.append(f"scenario metadata differs in {asset_path.name}")
        snapshots = payload.get("snapshots")
        expected_years = list(range(scenario["start_year"], scenario["end_year"] + 1))
        if (
            not isinstance(snapshots, list)
            or [snapshot.get("year") for snapshot in snapshots] != expected_years
        ):
            errors.append(f"snapshot years are incomplete in {asset_path.name}")
            continue
        first = snapshots[0]
        if (
            first.get("total_population") != scenario.get("population_size")
            or first.get("simulation_result", {}).get("net_change") != 0
        ):
            errors.append(f"baseline snapshot is not immutable in {asset_path.name}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=Path("data/baselines"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("frontend/public/recordings")
    )
    args = parser.parse_args()
    errors = validation_errors(args.baseline_dir, args.output_dir)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print("Static recordings match current models, code, and baselines.")


if __name__ == "__main__":
    main()
