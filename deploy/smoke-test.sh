#!/usr/bin/env bash
# Signal Sports — isolated smoke test of the two images (#263).
#
#   deploy/smoke-test.sh <backend-image> <web-image>
#
# Runs the Compose stack under its own project name on an EMPTY temp database,
# on 127.0.0.1:18080, with every external side effect off: no LLM, no Telegram,
# no results sync, and a worker that never runs a cycle (no source is fetched).
# It never touches /srv/signal or any real data. Used by CI; safe on a host.
#
# Needs docker with the compose plugin, curl and sudo (to own the temp data dir
# as the service uid). Exits non-zero on the first failed check.
set -euo pipefail

BACKEND_IMAGE=${1:?usage: smoke-test.sh <backend-image> <web-image>}
WEB_IMAGE=${2:?usage: smoke-test.sh <backend-image> <web-image>}
HERE=$(cd "$(dirname "$0")" && pwd)
PORT=18080
ORIGIN="http://127.0.0.1:${PORT}"
BASE="http://127.0.0.1:${PORT}"
WORK=$(mktemp -d)
PROJECT="signal-smoke-$$"

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }

compose() {
  SIGNAL_BACKEND_IMAGE="$BACKEND_IMAGE" SIGNAL_WEB_IMAGE="$WEB_IMAGE" \
  SIGNAL_ENV_FILE="$WORK/signal.env" SIGNAL_DATA_DIR="$WORK/data" \
  SIGNAL_WEB_PORT="$PORT" \
    docker compose -p "$PROJECT" -f "$HERE/compose.yaml" "$@"
}

cleanup() {
  compose --profile worker logs --no-color > "$WORK/compose.log" 2>&1 || true
  compose --profile worker down -v --remove-orphans > /dev/null 2>&1 || true
  if [ "${KEEP_SMOKE_LOGS:-}" = "1" ]; then cp "$WORK/compose.log" ./smoke-compose.log || true; fi
  sudo rm -rf "$WORK"
}
trap cleanup EXIT

# ── Image hygiene ────────────────────────────────────────────────────────────
uid=$(docker run --rm --entrypoint id "$BACKEND_IMAGE" -u)
[ "$uid" = "10001" ] && pass "backend runs as uid 10001" || fail "backend uid is $uid"
web_uid=$(docker run --rm --entrypoint id "$WEB_IMAGE" -u)
[ "$web_uid" != "0" ] && pass "web runs as non-root uid $web_uid" || fail "web runs as root"

leaks=$(docker run --rm --entrypoint sh "$BACKEND_IMAGE" -c \
  "find /app \( -name '.env' -o -name '.env.*' -o -name '*.db' -o -name '*.db-wal' -o -name '*.age' -o -name '*.log' -o -name '.venv' \) -print")
[ -z "$leaks" ] && pass "backend image has no .env, DB, key, log or venv under /app" || fail "backend image leaks: $leaks"
[ -z "$(docker run --rm --entrypoint sh "$BACKEND_IMAGE" -c 'ls -A /app/data')" ] \
  && pass "backend /app/data is empty" || fail "backend /app/data is not empty"
web_leaks=$(docker run --rm --entrypoint sh "$WEB_IMAGE" -c \
  "find /usr/share/nginx/html \( -name '.env*' -o -name '*.map' -o -name 'node_modules' \) -print")
[ -z "$web_leaks" ] && pass "web image serves no .env, source map or node_modules" || fail "web image leaks: $web_leaks"
docker run --rm --entrypoint test "$BACKEND_IMAGE" -s /app/PIP_FREEZE.txt \
  && pass "backend records its installed set (PIP_FREEZE.txt)" || fail "PIP_FREEZE.txt missing"

# ── An empty, hosted-mode stack ──────────────────────────────────────────────
mkdir -p "$WORK/data"
sudo chown 10001:10001 "$WORK/data"
sudo chmod 0700 "$WORK/data"
cat > "$WORK/signal.env" <<EOF
DEPLOY_ENV=hosted
CSRF_ALLOWED_ORIGINS=${ORIGIN}
# Plain HTTP in the smoke test only; DEPLOY_ENV=hosted warns about it.
AUTH_COOKIE_SECURE=false
AUTH_SIGNUP_ENABLED=false
AUTH_ADMIN_EMAIL=smoke-admin@example.invalid
AUTH_ADMIN_PASSWORD=smoke-test-only-password
SCHEDULER_ENABLED=false
CLASSIFICATION_PROVIDER=disabled
TELEGRAM_NOTIFICATIONS_ENABLED=false
RESULTS_SYNC_ENABLED=false
RETENTION_CLEANUP_ENABLED=false
EOF

compose config --quiet && pass "compose file is valid"
compose up -d --wait --wait-timeout 120 api web && pass "api and web are healthy"

# Substring tests without pipes: `curl | grep -q` can fail under pipefail when
# grep exits before curl has finished writing.
has() { [[ "$1" == *"$2"* ]]; }

body=$(curl -fsS "$BASE/health")
has "$body" '"ok"' && pass "/health through web: $body" || fail "/health: $body"
has "$(curl -fsS "$BASE/")" '<div id="root">' && pass "SPA index served" || fail "index not served"
has "$(curl -fsS "$BASE/login")" '<div id="root">' && pass "/login falls back to the SPA" || fail "/login fallback"
has "$(curl -fsS "$BASE/healthz")" ok && pass "nginx /healthz" || fail "/healthz"

session=$(curl -fsS "$BASE/api/auth/session")
has "$session" '"auth_enforced":true' && pass "auth enforced: $session" || fail "session: $session"
has "$session" '"signup_enabled":false' && pass "signup reported closed" || fail "signup not closed: $session"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/signup" \
  -H "Origin: $ORIGIN" -H 'Content-Type: application/json' \
  -d '{"email":"smoke-user@example.invalid","password":"smoke-test-only-password"}')
[ "$code" = "403" ] && pass "signup refused (403)" || fail "signup returned $code"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" \
  -H "Origin: https://evil.example" -H 'Content-Type: application/json' \
  -d '{"email":"smoke-admin@example.invalid","password":"smoke-test-only-password"}')
[ "$code" = "403" ] && pass "cross-origin login refused by CSRF (403)" || fail "cross-origin login returned $code"

headers=$(curl -s -D - -o /dev/null -X POST "$BASE/api/auth/login" \
  -H "Origin: $ORIGIN" -H 'Content-Type: application/json' \
  -d '{"email":"smoke-admin@example.invalid","password":"smoke-test-only-password"}')
status_line=${headers%%$'\r'*}
has "$status_line" ' 200' && has "${headers,,}" 'set-cookie: signal_session=' \
  && pass "same-origin admin login through the proxy sets signal_session" || fail "login: $headers"

owner=$(sudo stat -c '%u' "$WORK/data/signal_sports.db")
[ "$owner" = "10001" ] && pass "corpus file owned by the service uid" || fail "corpus owner uid $owner"

# ── Worker: starts, is healthy, stops gracefully. Never runs a cycle. ────────
cat >> "$WORK/signal.env" <<EOF
SCHEDULER_ENABLED=true
SCHEDULER_RUN_ON_STARTUP=false
SCHEDULER_STARTUP_CATCHUP=false
SCHEDULER_INTERVAL_SECONDS=3600
EOF
compose --profile worker up -d --wait --wait-timeout 180 worker && pass "worker is healthy"
start=$(date +%s)
compose --profile worker stop worker
elapsed=$(( $(date +%s) - start ))
[ "$elapsed" -lt 30 ] && pass "idle worker stopped on SIGTERM in ${elapsed}s" || fail "worker stop took ${elapsed}s"
exit_code=$(docker inspect -f '{{.State.ExitCode}}' "$(compose --profile worker ps -a -q worker)")
[ "$exit_code" = "0" ] && pass "worker exited 0" || fail "worker exit code $exit_code"
state=$(compose run --rm -T --no-deps --entrypoint python api -c \
  "import sqlite3; print(sqlite3.connect('/app/data/signal_sports.db').execute('SELECT state FROM worker_status').fetchone()[0])")
[ "$state" = "stopped" ] && pass "worker recorded state=stopped" || fail "worker state $state"
cycles=$(compose run --rm -T --no-deps --entrypoint python api -c \
  "import sqlite3; print(sqlite3.connect('/app/data/signal_sports.db').execute('SELECT COUNT(*) FROM scheduler_cycles').fetchone()[0])")
[ "$cycles" = "0" ] && pass "no ingestion cycle ran" || fail "$cycles cycles ran"

# ── Hosted mode refuses a dev flag ───────────────────────────────────────────
set +e
refusal=$(compose run --rm -T --no-deps -e ALLOW_DEV_RESET=true api 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] && has "$refusal" "ALLOW_DEV_RESET" \
  && pass "DEPLOY_ENV=hosted refuses ALLOW_DEV_RESET (exit $rc)" || fail "no refusal (exit $rc): $refusal"

echo "smoke test passed"
