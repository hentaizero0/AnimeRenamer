#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_PARENT="$(dirname "$ROOT_DIR")"
SOURCE_DIR="$(basename "$ROOT_DIR")"
DIST_DIR="$ROOT_DIR/dist"
ARCHIVE_PATH="${1:-$DIST_DIR/anime-triage-unraid.tgz}"

mkdir -p "$DIST_DIR" "$(dirname "$ARCHIVE_PATH")"

tar -czf "$ARCHIVE_PATH" \
  --exclude="$SOURCE_DIR/.git" \
  --exclude="$SOURCE_DIR/.pytest_cache" \
  --exclude="$SOURCE_DIR/__pycache__" \
  --exclude="$SOURCE_DIR/.venv" \
  --exclude="$SOURCE_DIR/venv" \
  --exclude="$SOURCE_DIR/dist" \
  --exclude="$SOURCE_DIR/logs" \
  --exclude="$SOURCE_DIR/user-config" \
  --exclude="$SOURCE_DIR/.env" \
  --exclude="$SOURCE_DIR/.env.local" \
  --exclude="$SOURCE_DIR/*.env.local" \
  --exclude="$SOURCE_DIR/state.json" \
  --exclude="$SOURCE_DIR/config/series_config.yaml" \
  --exclude="$SOURCE_DIR/config/*.local.*" \
  --exclude="$SOURCE_DIR/regression_downloads" \
  --exclude="$SOURCE_DIR/regression_target" \
  --exclude="$SOURCE_DIR/regression_anime" \
  --exclude="$SOURCE_DIR/unriad.output" \
  --exclude="$SOURCE_DIR/playwright-data" \
  --exclude="$SOURCE_DIR/.coverage" \
  -C "$SOURCE_PARENT" "$SOURCE_DIR"

cp "$ROOT_DIR/scripts/deploy_unraid.sh" "$DIST_DIR/deploy_unraid.sh"

printf 'Package: %s\n' "$ARCHIVE_PATH"
printf 'Deploy script: %s\n' "$DIST_DIR/deploy_unraid.sh"
