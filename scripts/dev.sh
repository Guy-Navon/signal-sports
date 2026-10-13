#!/usr/bin/env bash
# Signal Sports — development commands for Linux: a codespace, a devcontainer,
# or the dev user on a host. The Windows PC keeps scripts/worker.ps1 and the
# commands in docs/CURRENT_PROJECT_STATE.md section 12.
#
#   scripts/dev.sh api             API on 127.0.0.1:8000 (--reload), dev DB
#   scripts/dev.sh web             Vite on 127.0.0.1:5173, proxying /api to 8000
#   scripts/dev.sh test [args]     backend suite (hermetic: temp DB, no network)
#   scripts/dev.sh test-web        frontend lint, typecheck, tests, build
#   scripts/dev.sh check           everything CI's checks.yml runs
#   scripts/dev.sh gate <snapshot.db>
#                                  N05 gate against a SANITIZED snapshot copy
#   scripts/dev.sh env             print the effective dev settings
#
# Always DEPLOY_ENV=dev: the app refuses Telegram and any production database
# (backend/app/core/deploy_mode.py). No command here starts a worker.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PY="$BACKEND/.venv/bin/python"

if [ "${DEPLOY_ENV:-dev}" != "dev" ]; then
  echo "scripts/dev.sh refuses DEPLOY_ENV=${DEPLOY_ENV}: it is for development only." >&2
  exit 2
fi
export DEPLOY_ENV=dev
export DATABASE_URL="${DATABASE_URL:-sqlite:///$BACKEND/data/dev/signal_dev.db}"
export SCHEDULER_ENABLED=false
export TELEGRAM_NOTIFICATIONS_ENABLED=false
export CLASSIFICATION_PROVIDER="${CLASSIFICATION_PROVIDER:-disabled}"
export RESULTS_SYNC_ENABLED="${RESULTS_SYNC_ENABLED:-false}"
export VITE_DATA_MODE="${VITE_DATA_MODE:-backend}"

# In a codespace the browser reaches Vite at an exact forwarded hostname.
# Allow that one host (no wildcard; same approach as docs/MOBILE_REMOTE_ACCESS.md)
# and accept its origin for the CSRF check.
origins="http://localhost:5173,http://127.0.0.1:5173"
if [ -n "${CODESPACE_NAME:-}" ] && [ -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]; then
  host="${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
  export __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS="$host"
  origins="https://${host},${origins}"
fi
export CSRF_ALLOWED_ORIGINS="${CSRF_ALLOWED_ORIGINS:-$origins}"

need_venv() {
  [ -x "$PY" ] || { echo "backend/.venv missing: run bash .devcontainer/post-create.sh" >&2; exit 1; }
}

cmd=${1:-}
[ $# -gt 0 ] && shift
case "$cmd" in
  api)
    need_venv
    mkdir -p "$BACKEND/data/dev"
    cd "$BACKEND"
    exec "$PY" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    ;;
  web)
    cd "$FRONTEND"
    exec npm run dev
    ;;
  test)
    need_venv
    cd "$BACKEND"
    exec "$PY" -m pytest tests -q "$@"
    ;;
  test-web)
    cd "$FRONTEND"
    npm run lint
    npm run typecheck
    npm run test -- --maxWorkers=2
    npm run build
    ;;
  check)
    "$0" test
    "$0" test-web
    ;;
  gate)
    need_venv
    snapshot=${1:?usage: scripts/dev.sh gate <snapshot.db>}
    [ -f "$snapshot" ] || { echo "no such file: $snapshot" >&2; exit 1; }
    abs=$(cd "$(dirname "$snapshot")" && pwd)/$(basename "$snapshot")
    cd "$BACKEND"
    echo "Measured on a snapshot: $abs (not the live corpus)."
    DATABASE_URL="sqlite:///$abs" exec "$PY" scripts/feed_ground_truth.py gate
    ;;
  env)
    for name in DEPLOY_ENV DATABASE_URL SCHEDULER_ENABLED TELEGRAM_NOTIFICATIONS_ENABLED \
                CLASSIFICATION_PROVIDER RESULTS_SYNC_ENABLED VITE_DATA_MODE CSRF_ALLOWED_ORIGINS \
                __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS CLAUDE_CONFIG_DIR; do
      printf '%s=%s\n' "$name" "${!name:-}"
    done
    ;;
  *)
    sed -n '2,17p' "$0"
    exit 2
    ;;
esac
