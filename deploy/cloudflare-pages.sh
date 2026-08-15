#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

project_name="ni-model"
branch="main"
refresh=false

usage() {
  echo "Usage: deploy/cloudflare-pages.sh [--project NAME] [--branch NAME] [--refresh-recordings]"
}

while (($#)); do
  case "$1" in
    --project) project_name="$2"; shift 2 ;;
    --branch) branch="$2"; shift 2 ;;
    --refresh-recordings) refresh=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID first.}"
: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN first.}"

build_args=()
$refresh && build_args+=(--refresh-recordings)
scripts/build_static_site.sh "${build_args[@]}"

docker run --rm \
  -e CLOUDFLARE_ACCOUNT_ID \
  -e CLOUDFLARE_API_TOKEN \
  -v "$PWD:/app" -w /app node:22-bookworm-slim \
  sh -c 'npx --yes wrangler@latest pages deploy build/static-site --project-name "$1" --branch "$2"' \
  deploy "$project_name" "$branch"

echo "Cloudflare Pages deployment submitted for project: $project_name"
