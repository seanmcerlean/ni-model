import json
from types import SimpleNamespace

from scripts import export_static_recordings, validate_static_recordings


def _model():
    data = {"id": "current", "path": "models/current.yaml", "name": "Current"}
    return SimpleNamespace(
        id=data["id"],
        path=data["path"],
        model_dump=lambda mode: data,
    )


def _write_valid_recording(output_dir):
    scenario = {
        "id": "current-seed-1180",
        "model_path": "models/current.yaml",
        "asset": "/recordings/current.json",
        "seed": 1180,
        "start_year": 2021,
        "end_year": 2022,
        "population_size": 100,
        "final_population_size": 101,
    }
    snapshots = [
        {
            "year": 2021,
            "total_population": 100,
            "simulation_result": {"net_change": 0},
        },
        {
            "year": 2022,
            "total_population": 101,
            "simulation_result": {"net_change": 1},
        },
    ]
    (output_dir / "current.json").write_text(
        json.dumps({"scenario": scenario, "snapshots": snapshots}),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": validate_static_recordings.SCHEMA_VERSION,
        "application_version": "0.5.0",
        "recording_inputs_hash": "current-inputs",
        "models": [_model().model_dump(mode="json")],
        "scenarios": [scenario],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _patch_current_inputs(monkeypatch):
    monkeypatch.setattr(
        validate_static_recordings, "simulation_models", lambda: [_model()]
    )
    monkeypatch.setattr(
        validate_static_recordings,
        "recording_input_manifest",
        lambda *_args: {"recording_inputs_hash": "current-inputs"},
    )
    monkeypatch.setattr(
        validate_static_recordings, "application_version", lambda: "0.5.0"
    )


def test_static_recording_validator_accepts_complete_current_catalogue(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "recordings"
    output_dir.mkdir()
    _write_valid_recording(output_dir)
    _patch_current_inputs(monkeypatch)

    assert validate_static_recordings.validation_errors(tmp_path, output_dir) == []


def test_static_recording_validator_rejects_stale_or_unsafe_assets(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "recordings"
    output_dir.mkdir()
    _write_valid_recording(output_dir)
    _patch_current_inputs(monkeypatch)
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["recording_inputs_hash"] = "stale"
    manifest["scenarios"][0]["asset"] = "current.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = validate_static_recordings.validation_errors(tmp_path, output_dir)

    assert "recording source or baseline inputs have changed" in errors
    assert "invalid scenario asset path: 'current.json'" in errors


def test_static_export_discards_unpublished_individual_events():
    class Worker:
        def __init__(self):
            self.events = []

        def run_year(self, year):
            self.events.extend([object(), object()])
            return {"year": year}

    worker = Worker()

    result = export_static_recordings._recording_year_result(worker, 2022, 2021)

    assert result == {"year": 2022}
    assert worker.events == []
