#!/usr/bin/env bash
set -euo pipefail

refresh_recordings=false
if [[ "${1:-}" == "--refresh-recordings" ]]; then
  refresh_recordings=true
  shift
fi
if (($#)); then
  echo "Usage: scripts/build_static_site.sh [--refresh-recordings]" >&2
  exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
./check-dependencies.sh

if [[ ! -f data/baselines/current.parquet || ! -f data/baselines/historical.parquet ]]; then
  docker compose -f compose.parquet.yaml run --rm --build baseline-builder \
    python scripts/build_parquet_baselines.py --output-dir /app/data/baselines
fi

recordings_valid=false
if ! $refresh_recordings; then
  if docker compose -f compose.parquet.yaml run --rm --build baseline-builder \
    python scripts/validate_static_recordings.py \
    --baseline-dir /app/data/baselines --output-dir /recordings; then
    recordings_valid=true
  fi
fi

if ! $recordings_valid; then
  docker compose -f compose.parquet.yaml run --rm --build baseline-builder \
    python scripts/export_static_recordings.py \
    --baseline-dir /app/data/baselines --output-dir /recordings
fi

image="ni-model-static-export:local"
docker build --target static --build-arg VITE_DEPLOYMENT_MODE=static -t "$image" .
container="$(docker create "$image")"
temporary_dir="$(mktemp -d)"
cleanup() {
  docker rm "$container" >/dev/null 2>&1 || true
  rm -rf "$temporary_dir"
}
trap cleanup EXIT

docker cp "$container:/usr/share/nginx/html/." "$temporary_dir/"
mkdir -p build
rm -rf build/static-site
mv "$temporary_dir" build/static-site
trap - EXIT
docker rm "$container" >/dev/null

echo "Static site built at $project_root/build/static-site"
