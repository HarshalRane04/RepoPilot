#!/bin/sh
set -eu

WEB_ROOT="/app/apps/web"

mkdir -p "$WEB_ROOT/node_modules" "$WEB_ROOT/.next"
chown -R appuser:appuser "$WEB_ROOT/node_modules" "$WEB_ROOT/.next"

exec su appuser -s /bin/sh -c "$*"
