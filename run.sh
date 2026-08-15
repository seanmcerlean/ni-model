#!/usr/bin/env bash
set -euo pipefail

mode="parquet"
port="8000"

usage() {
  echo "Usage: ./run.sh [--mode static|parquet|full] [--port 1-65535]"
}

while (($#)); do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      mode="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      port="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$mode" in
  static|parquet|full) ;;
  *) echo "Mode must be static, parquet, or full." >&2; exit 2 ;;
esac

if [[ ! "$port" =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
  echo "Port must be an integer from 1 to 65535." >&2
  exit 2
fi

./check-dependencies.sh
NI_MODEL_MODE="$mode" NI_MODEL_PORT="$port" exec ./deploy.sh
