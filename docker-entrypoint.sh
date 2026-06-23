#!/bin/bash
set -euo pipefail

PUID=${PUID:-1000}
PGID=${PGID:-100}
GROUP_NAME=abc
USER_NAME=abc

# Reuse existing group if the GID already exists (Unraid commonly uses 100:users).
if existing_group="$(getent group "$PGID" | cut -d: -f1)"; then
    GROUP_NAME="$existing_group"
elif ! getent group "$GROUP_NAME" >/dev/null; then
    groupadd -g "$PGID" "$GROUP_NAME"
fi

# Reuse existing user if the UID already exists.
if existing_user="$(getent passwd "$PUID" | cut -d: -f1)"; then
    USER_NAME="$existing_user"
elif ! getent passwd "$USER_NAME" >/dev/null; then
    useradd -u "$PUID" -g "$GROUP_NAME" -s /bin/sh -m "$USER_NAME"
else
    usermod -g "$GROUP_NAME" "$USER_NAME"
fi

HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
mkdir -p "${HOME_DIR}/.config/anime_renamer"
if [ ! -s /app/state.json ]; then
    printf '{\n  "history": [],\n  "timestamp": ""\n}\n' > /app/state.json
fi

# Set permissions for volume directories if they exist
for dir in /downloads /anime /jellyfin /app/config /app/logs "${HOME_DIR}/.config/anime_renamer"; do
    if [ -d "$dir" ]; then
        chown -R "${USER_NAME}:${GROUP_NAME}" "$dir"
    fi
done

if [ -e /app/state.json ]; then
    chown "${USER_NAME}:${GROUP_NAME}" /app/state.json
fi

# Run as the resolved user
exec gosu "${USER_NAME}" "$@"
