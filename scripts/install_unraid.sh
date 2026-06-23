#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(pwd)}"
APP_PORT="${APP_PORT:-8765}"
HOST_DOWNLOAD_DIR="${HOST_DOWNLOAD_DIR:-/mnt/user/hentaidisk/Downloads}"
HOST_STORAGE_DIR="${HOST_STORAGE_DIR:-/mnt/user/hentaidisk/video/anime}"
HOST_JELLYFIN_LINK_DIR="${HOST_JELLYFIN_LINK_DIR:-/mnt/user/hentaidisk/video/link}"
HOST_JELLYFIN_COLLECT_DIR="${HOST_JELLYFIN_COLLECT_DIR:-/mnt/user/hentaidisk/video/link/anime/动漫}"
HOST_JELLYFIN_AIRING_DIR="${HOST_JELLYFIN_AIRING_DIR:-/mnt/user/hentaidisk/video/link/Bangumi}"
HOST_JELLYFIN_MOVIE_DIR="${HOST_JELLYFIN_MOVIE_DIR:-}"
TMDB_API_KEY="${TMDB_API_KEY:-}"
FORCE_CONFIG="${FORCE_CONFIG:-0}"
SKIP_UP="${SKIP_UP:-0}"

usage() {
  cat <<'EOF'
Usage: install_unraid.sh [--app-dir PATH] [--port N] [--tmdb-key KEY] [--skip-up] [--force-config]

Environment overrides:
  APP_DIR
  APP_PORT
  HOST_DOWNLOAD_DIR
  HOST_STORAGE_DIR
  HOST_JELLYFIN_LINK_DIR
  HOST_JELLYFIN_COLLECT_DIR
  HOST_JELLYFIN_AIRING_DIR
  HOST_JELLYFIN_MOVIE_DIR
  TMDB_API_KEY
  PUID
  PGID
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --app-dir) APP_DIR="$2"; shift 2 ;;
    --port) APP_PORT="$2"; shift 2 ;;
    --tmdb-key) TMDB_API_KEY="$2"; shift 2 ;;
    --skip-up) SKIP_UP=1; shift ;;
    --force-config) FORCE_CONFIG=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [ "$(uname -s)" != "Linux" ]; then
  echo "This installer is for Linux/Unraid." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "docker compose plugin is missing." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not reachable." >&2
  exit 1
fi

for required in docker-compose.yml Dockerfile config frontend backend docker-entrypoint.sh; do
  if [ ! -e "${APP_DIR}/${required}" ]; then
    echo "Missing ${required} in ${APP_DIR}" >&2
    exit 1
  fi
done

for path in "${HOST_DOWNLOAD_DIR}" "${HOST_STORAGE_DIR}" "${HOST_JELLYFIN_LINK_DIR}"; do
  if [ ! -d "${path}" ]; then
    echo "Missing required directory: ${path}" >&2
    exit 1
  fi
done

for optional_dir in "${HOST_JELLYFIN_COLLECT_DIR}" "${HOST_JELLYFIN_AIRING_DIR}"; do
  if [ ! -d "${optional_dir}" ]; then
    echo "Warning: directory does not exist yet: ${optional_dir}" >&2
  fi
done

if [ -z "${TMDB_API_KEY}" ]; then
  read -r -s -p "TMDB_API_KEY: " TMDB_API_KEY
  echo
fi

if [ -z "${TMDB_API_KEY}" ]; then
  echo "TMDB_API_KEY is required." >&2
  exit 1
fi

DETECTED_UID="$(stat -c '%u' "${HOST_DOWNLOAD_DIR}")"
DETECTED_GID="$(stat -c '%g' "${HOST_DOWNLOAD_DIR}")"
if [ "${DETECTED_UID}" = "0" ]; then
  DETECTED_UID=99
fi
if [ "${DETECTED_GID}" = "0" ]; then
  DETECTED_GID=100
fi
PUID="${PUID:-${DETECTED_UID}}"
PGID="${PGID:-${DETECTED_GID}}"

mkdir -p "${APP_DIR}/config" "${APP_DIR}/logs" "${APP_DIR}/user-config"
if [ ! -s "${APP_DIR}/state.json" ]; then
  printf '{\n  "history": [],\n  "timestamp": ""\n}\n' > "${APP_DIR}/state.json"
fi

cat > "${APP_DIR}/.env" <<EOF
APP_PORT=${APP_PORT}
PUID=${PUID}
PGID=${PGID}
TMDB_API_KEY=${TMDB_API_KEY}
HOST_DOWNLOAD_DIR=${HOST_DOWNLOAD_DIR}
HOST_STORAGE_DIR=${HOST_STORAGE_DIR}
HOST_JELLYFIN_LINK_DIR=${HOST_JELLYFIN_LINK_DIR}
# future placeholders
HOST_JELLYFIN_COLLECT_DIR=${HOST_JELLYFIN_COLLECT_DIR}
HOST_JELLYFIN_AIRING_DIR=${HOST_JELLYFIN_AIRING_DIR}
HOST_JELLYFIN_MOVIE_DIR=${HOST_JELLYFIN_MOVIE_DIR}
EOF
chmod 600 "${APP_DIR}/.env"

CONFIG_PATH="${APP_DIR}/config/series_config.yaml"
NEEDS_CONFIG_WRITE=0
if [ ! -f "${CONFIG_PATH}" ]; then
  NEEDS_CONFIG_WRITE=1
elif grep -Eq 'regression_downloads|/workspaces/anime_triage' "${CONFIG_PATH}"; then
  NEEDS_CONFIG_WRITE=1
fi

if [ "${FORCE_CONFIG}" = "1" ]; then
  NEEDS_CONFIG_WRITE=1
fi

if [ "${NEEDS_CONFIG_WRITE}" = "1" ]; then
  if [ -f "${CONFIG_PATH}" ]; then
    cp "${CONFIG_PATH}" "${CONFIG_PATH}.bak.$(date +%Y%m%d-%H%M%S)"
  fi
  cat > "${CONFIG_PATH}" <<'EOF'
settings:
  default_mode: confirm
  download_dir: /downloads
  storage_dir: /anime
  jellyfin_airing_dir: /jellyfin/Bangumi
  jellyfin_collect_dir: /jellyfin/anime/动漫
  tmdb_api_key: ${TMDB_API_KEY}

series: {}
EOF
fi

echo "APP_DIR=${APP_DIR}"
echo "APP_PORT=${APP_PORT}"
echo "PUID:PGID=${PUID}:${PGID}"
echo "DOWNLOAD=${HOST_DOWNLOAD_DIR}"
echo "STORAGE=${HOST_STORAGE_DIR}"
echo "JELLYFIN_LINK=${HOST_JELLYFIN_LINK_DIR}"
# ponytail: movie path is only recorded for future wiring; current app does not consume it yet.
if [ -n "${HOST_JELLYFIN_MOVIE_DIR}" ]; then
  echo "JELLYFIN_MOVIE=${HOST_JELLYFIN_MOVIE_DIR} (placeholder only)"
fi

if [ "${SKIP_UP}" = "1" ]; then
  echo "Prepared files only; skipped docker compose up."
  exit 0
fi

(
  cd "${APP_DIR}"
  "${COMPOSE_CMD[@]}" up -d --build
)

echo "Install complete."
echo "Open: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${APP_PORT}"
