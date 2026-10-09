#!/bin/sh
# Starts as root only to hand the data directory (a bind mount, which Docker creates
# root-owned) to the app user, then drops privileges for the real process.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    # Only what is not ours yet: instant on every start after the first
    find "$DATA_DIR" ! -user scraper -exec chown scraper:scraper {} +
    exec setpriv --reuid=scraper --regid=scraper --init-groups "$@"
fi

exec "$@"
