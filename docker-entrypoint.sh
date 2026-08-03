#!/bin/sh
set -eu

if [ "${1#-}" != "$1" ]; then
    set -- busybar-msteams "$@"
fi

if [ "$(id -u)" = "0" ]; then
    chown busybar:busybar /data
    exec gosu busybar "$@"
fi

exec "$@"
