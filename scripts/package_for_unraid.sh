#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
DIST_DIR="${ROOT_DIR}/dist"
ARCHIVE_PATH="${1:-${DIST_DIR}/anime-triage-unraid-${STAMP}.tgz}"

mkdir -p "$(dirname "${ARCHIVE_PATH}")"

tar \
  --exclude='.git' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='dist' \
  --exclude='logs' \
  --exclude='user-config' \
  --exclude='.env' \
  --exclude='state.json' \
  --exclude='regression_downloads' \
  --exclude='regression_target' \
  -czf "${ARCHIVE_PATH}" \
  -C "${ROOT_DIR}" .

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${ARCHIVE_PATH}" > "${ARCHIVE_PATH}.sha256"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "${ARCHIVE_PATH}" > "${ARCHIVE_PATH}.sha256"
fi

echo "Created: ${ARCHIVE_PATH}"
if [ -f "${ARCHIVE_PATH}.sha256" ]; then
  echo "Checksum: ${ARCHIVE_PATH}.sha256"
fi
