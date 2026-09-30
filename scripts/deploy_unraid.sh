#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/mnt/user/hentaidisk/AnimeRenamer}"
ARCHIVE_PATH="${1:-$APP_DIR/anime-triage-unraid.tgz}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -d "$APP_DIR" ]] || fail "App directory not found: $APP_DIR"
[[ -f "$ARCHIVE_PATH" ]] || fail "Package not found: $ARCHIVE_PATH"

for required in docker-compose.yml .env config/series_config.yaml state.json; do
  [[ -e "$APP_DIR/$required" ]] || fail "Expected existing deployment file is missing: $APP_DIR/$required"
done

command -v docker >/dev/null 2>&1 || fail "docker is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose is unavailable"

FIRST_ENTRY="$(tar -tzf "$ARCHIVE_PATH" | sed -n '1p')"
[[ "$FIRST_ENTRY" == "anime_triage/" ]] || fail "Unexpected package root '$FIRST_ENTRY'; expected anime_triage/"

printf 'Extracting %s into %s\n' "$ARCHIVE_PATH" "$APP_DIR"
tar --strip-components=1 -xzf "$ARCHIVE_PATH" -C "$APP_DIR"
mkdir -p "$APP_DIR/logs" "$APP_DIR/user-config"

cd "$APP_DIR"
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 anime-triage
