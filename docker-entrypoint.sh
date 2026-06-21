#!/bin/bash
set -e

PUID=${PUID:-1000}
PGID=${PGID:-100}

# Create group if not exists
if ! getent group abc >/dev/null; then
    groupadd -g "$PGID" abc
fi

# Create user if not exists
if ! getent passwd abc >/dev/null; then
    useradd -u "$PUID" -g "$PGID" -s /bin/sh -m abc
fi

# Set permissions for volume directories if they exist
for dir in /downloads /anime /jellyfin /app/config /app/logs; do
    if [ -d "$dir" ]; then
        chown -R abc:abc "$dir"
    fi
done

# Run as abc user
exec gosu abc "$@"
