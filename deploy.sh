#!/bin/bash
set -euo pipefail

mode="${NI_MODEL_MODE:-parquet}"
port="${NI_MODEL_PORT:-8000}"

case "$mode" in
  parquet)
    docker compose -f compose.static.yaml stop site >/dev/null 2>&1 || true
    docker compose -f compose.yaml stop worker current-db >/dev/null 2>&1 || true
    if [[ ! -f data/baselines/current.parquet || ! -f data/baselines/historical.parquet ]]; then
      docker compose -f compose.parquet.yaml run --rm --build baseline-builder \
        python scripts/build_parquet_baselines.py --output-dir /app/data/baselines
    fi
    docker compose -f compose.parquet.yaml up -d --build app
    ;;
  static)
    docker compose -f compose.parquet.yaml stop app >/dev/null 2>&1 || true
    docker compose -f compose.yaml stop app worker current-db >/dev/null 2>&1 || true
    if [[ ! -f data/baselines/current.parquet || ! -f data/baselines/historical.parquet ]]; then
      docker compose -f compose.parquet.yaml run --rm --build baseline-builder \
        python scripts/build_parquet_baselines.py --output-dir /app/data/baselines
    fi
    docker compose -f compose.parquet.yaml run --rm --build baseline-builder \
      python scripts/export_static_recordings.py \
      --baseline-dir /app/data/baselines --output-dir /recordings
    docker compose -f compose.static.yaml up -d --build
    ;;
  full)
    docker compose -f compose.static.yaml stop site >/dev/null 2>&1 || true
    docker compose up -d --build
    ;;
  *)
    echo "NI_MODEL_MODE must be static, parquet, or full" >&2
    exit 2
    ;;
esac

echo "NI Model $mode mode is available at http://localhost:$port"
