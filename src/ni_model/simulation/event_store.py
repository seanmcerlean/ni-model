"""Persistence for append-only individual events and Parquet checkpoints."""

import csv
import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

import polars as pl
from sqlalchemy.orm import Session

from ..core.models import SimulationCheckpoint, SimulationPersonEvent
from .columnar_worker import PopulationEvent


class EventStore:
    def __init__(self, db: Session, checkpoint_root: Path = None):
        self.db = db
        configured = os.getenv("CHECKPOINT_DIR", "data/checkpoints")
        self.checkpoint_root = checkpoint_root or Path(configured)

    def append(self, run_id: uuid.UUID, events: Iterable[PopulationEvent]) -> int:
        events = list(events)
        if not events:
            return 0
        if self.db.get_bind().dialect.name == "postgresql":
            with tempfile.TemporaryFile(mode="w+", newline="") as stream:
                writer = csv.writer(stream)
                created_at = datetime.now(UTC).isoformat()
                for item in events:
                    writer.writerow(
                        (
                            str(run_id),
                            str(uuid.UUID(bytes=item.person_id)),
                            item.year,
                            item.event_type,
                            json.dumps(
                                self._json_data(item.data), separators=(",", ":")
                            ),
                            created_at,
                        )
                    )
                stream.seek(0)
                cursor = self.db.connection().connection.cursor()
                cursor.copy_expert(
                    "COPY simulation_person_events "
                    "(run_id, person_id, year, event_type, data, created_at) "
                    "FROM STDIN WITH (FORMAT CSV)",
                    stream,
                )
            return len(events)
        mappings = [
            {
                "run_id": run_id,
                "person_id": uuid.UUID(bytes=item.person_id),
                "year": item.year,
                "event_type": item.event_type,
                "data": self._json_data(item.data),
            }
            for item in events
        ]
        if mappings:
            self.db.bulk_insert_mappings(SimulationPersonEvent, mappings)
        return len(mappings)

    @staticmethod
    def _json_data(data: dict) -> dict:
        converted = dict(data)
        person_id = converted.get("person_id")
        if isinstance(person_id, bytes):
            converted["person_id"] = str(uuid.UUID(bytes=person_id))
        return converted

    def checkpoint(
        self, run_id: uuid.UUID, year: int, population: pl.DataFrame
    ) -> SimulationCheckpoint:
        directory = self.checkpoint_root / str(run_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{year}.parquet"
        temporary = directory / f".{year}.{uuid.uuid4().hex}.tmp"
        population.write_parquet(temporary, compression="zstd", statistics=True)
        existing_bytes = (
            self.db.query(SimulationCheckpoint.byte_size)
            .filter(SimulationCheckpoint.run_id == run_id)
            .all()
        )
        maximum = int(os.getenv("MAX_CHECKPOINT_BYTES_PER_RUN", str(10 * 1024**3)))
        projected = (
            sum(row.byte_size for row in existing_bytes) + temporary.stat().st_size
        )
        if projected > maximum:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("run checkpoint storage limit exceeded")
        temporary.replace(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checkpoint = SimulationCheckpoint(
            run_id=run_id,
            year=year,
            storage_uri=path.resolve().as_uri(),
            population_count=population.height,
            byte_size=path.stat().st_size,
            checksum=digest,
        )
        self.db.add(checkpoint)
        return checkpoint

    def delete_run(self, run_id: uuid.UUID) -> None:
        """Remove checkpoint files; database rows are removed by run cascade."""
        checkpoints = (
            self.db.query(SimulationCheckpoint)
            .filter(SimulationCheckpoint.run_id == run_id)
            .all()
        )
        for checkpoint in checkpoints:
            parsed = urlparse(checkpoint.storage_uri)
            if parsed.scheme == "file":
                Path(unquote(parsed.path)).unlink(missing_ok=True)
        directory = self.checkpoint_root / str(run_id)
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()

    @staticmethod
    def load(checkpoint: SimulationCheckpoint) -> pl.DataFrame:
        prefix = "file://"
        if not checkpoint.storage_uri.startswith(prefix):
            raise ValueError("only local file checkpoints are currently supported")
        path = Path(checkpoint.storage_uri.removeprefix(prefix))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != checkpoint.checksum:
            raise ValueError("checkpoint checksum does not match stored metadata")
        return pl.read_parquet(path)
