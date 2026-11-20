#!/bin/sh
set -e
# Volumes mounted by Coolify/Docker are often root-owned: fix, then drop privileges.
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  chown -R cheezy "$DATA_DIR" 2>/dev/null || true
  exec setpriv --reuid=10001 --regid=$(id -g cheezy) --init-groups "$@"
fi
exec "$@"
