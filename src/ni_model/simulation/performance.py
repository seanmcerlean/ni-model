"""Low-overhead instrumentation for repeatable simulation benchmarks."""

import json
import resource
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class StageMeasurement:
    calls: int = 0
    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0
    sql_statements: int = 0
    rows_affected: int = 0


class PerformanceRecorder:
    """Measure named stages and attribute SQL executed inside each stage."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.measurements: Dict[str, StageMeasurement] = defaultdict(StageMeasurement)
        self._active_stage = None
        self._listening = False

    def __enter__(self):
        event.listen(self.engine, "after_cursor_execute", self._after_cursor_execute)
        self._listening = True
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        if self._listening:
            event.remove(
                self.engine, "after_cursor_execute", self._after_cursor_execute
            )
            self._listening = False

    def _after_cursor_execute(
        self, _connection, cursor, _statement, _parameters, _context, _many
    ):
        if self._active_stage is None:
            return
        measurement = self.measurements[self._active_stage]
        measurement.sql_statements += 1
        if cursor.rowcount and cursor.rowcount > 0:
            measurement.rows_affected += cursor.rowcount

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        if self._active_stage is not None:
            raise RuntimeError("performance stages cannot be nested")
        measurement = self.measurements[name]
        measurement.calls += 1
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        self._active_stage = name
        try:
            yield
        finally:
            measurement.wall_seconds += time.perf_counter() - wall_start
            measurement.cpu_seconds += time.process_time() - cpu_start
            self._active_stage = None

    def report(self, metadata=None) -> dict:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "metadata": metadata or {},
            "peak_rss_kib": usage.ru_maxrss,
            "stages": {
                name: asdict(measurement)
                for name, measurement in sorted(self.measurements.items())
            },
        }

    def write_json(self, path: Path, metadata=None) -> None:
        path.write_text(
            json.dumps(self.report(metadata), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
