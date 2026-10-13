#!/usr/bin/env bash
# Signal Sports — rehearsal of validate / deploy / rollback / auto-rollback and
# the SSH forced command, against a LOCAL registry and a throwaway stack.
#
#   deploy/rehearse-deploy.sh <backend-image> <web-image>
#
# Three "releases" are pushed to a registry on 127.0.0.1:5000:
#   A = the images under test, B = the same with a label (a different digest),
#   C = broken (the API cannot start; preflight cannot see it).
# Nothing touches GHCR, a host, /srv/signal or real data. Used by CI.
set -euo pipefail

BACKEND_IMAGE=${1:?usage: rehearse-deploy.sh <backend-image> <web-image>}
WEB_IMAGE=${2:?usage: rehearse-deploy.sh <backend-image> <web-image>}
SRC=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
PORT=18095
REG=127.0.0.1:5000
REGISTRY_IMAGE="registry:2@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"
SHA_A=$(printf 'a%.0s' $(seq 1 40))
SHA_B=$(printf 'b%.0s' $(seq 1 40))
SHA_C=$(printf 'c%.0s' $(seq 1 40))
export COMPOSE_PROJECT_NAME="signal-deploy-rehearsal-$$"
export SIGNAL_DEPLOY_DIR="$WORK/deploy"
export SIGNAL_LOCK="$WORK/ops.lock"
export SIGNAL_DEPLOY_WAIT_SECONDS=60
export SIGNAL_MIN_FREE_MB=100

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
has() { [[ "$1" == *"$2"* ]]; }
deploy_cmd() { sudo -E bash "$SIGNAL_DEPLOY_DIR/signal-deploy.sh" "$@"; }
current() { grep "^SIGNAL_${1}_IMAGE=" "$SIGNAL_DEPLOY_DIR/.env" | cut -d= -f2-; }

cleanup() {
  (cd "$SIGNAL_DEPLOY_DIR" 2> /dev/null && docker compose --profile worker logs --no-color > "$WORK/compose.log" 2>&1) || true
  (cd "$SIGNAL_DEPLOY_DIR" 2> /dev/null && docker compose --profile worker down -v --remove-orphans > /dev/null 2>&1) || true
  docker rm -f signal-rehearsal-registry > /dev/null 2>&1 || true
  [ "${KEEP_REHEARSAL_LOGS:-}" = "1" ] && cp "$WORK/compose.log" ./deploy-rehearsal-compose.log 2> /dev/null || true
  sudo rm -rf "$WORK" /opt/signal-rehearsal-stub 2> /dev/null || true
}
trap cleanup EXIT

# ── Registry and three releases ──────────────────────────────────────────────
docker run -d --name signal-rehearsal-registry -p "$REG:5000" "$REGISTRY_IMAGE" > /dev/null
for _ in $(seq 1 30); do curl -fsS "http://$REG/v2/" > /dev/null 2>&1 && break; sleep 1; done
push() { docker tag "$1" "$2" && docker push -q "$2" > /dev/null; }
push "$BACKEND_IMAGE" "$REG/signal-backend:sha-$SHA_A"
push "$WEB_IMAGE" "$REG/signal-web:sha-$SHA_A"
printf 'FROM %s\nLABEL rehearsal=b\n' "$BACKEND_IMAGE" | docker build -q -t "$REG/signal-backend:sha-$SHA_B" - > /dev/null
printf 'FROM %s\nLABEL rehearsal=b\n' "$WEB_IMAGE" | docker build -q -t "$REG/signal-web:sha-$SHA_B" - > /dev/null
docker push -q "$REG/signal-backend:sha-$SHA_B" > /dev/null
docker push -q "$REG/signal-web:sha-$SHA_B" > /dev/null
# C: the API module graph is broken, but deploy_mode (the preflight) still imports.
printf 'FROM %s\nUSER root\nRUN rm /app/app/api/routes_health.py\nUSER 10001:10001\n' "$BACKEND_IMAGE" \
  | docker build -q -t "$REG/signal-backend:sha-$SHA_C" - > /dev/null
docker push -q "$REG/signal-backend:sha-$SHA_C" > /dev/null
push "$WEB_IMAGE" "$REG/signal-web:sha-$SHA_C"
pass "registry with releases A, B (new digests) and C (broken)"

# ── A throwaway deployment, starting from release A by tag ───────────────────
mkdir -p "$SIGNAL_DEPLOY_DIR" "$WORK/data"
cp "$SRC"/compose.yaml "$SRC"/lib.sh "$SRC"/signal-deploy.sh "$SRC"/backup.sh "$SRC"/offsite_upload.py "$SIGNAL_DEPLOY_DIR/"
sudo chown 10001:10001 "$WORK/data"
sudo chmod 0700 "$WORK/data"
cat > "$SIGNAL_DEPLOY_DIR/.env" <<EOF
SIGNAL_IMAGE_REPO=$REG
SIGNAL_BACKEND_IMAGE=$REG/signal-backend:sha-$SHA_A
SIGNAL_WEB_IMAGE=$REG/signal-web:sha-$SHA_A
SIGNAL_ENV_FILE=$WORK/signal.env
SIGNAL_DATA_DIR=$WORK/data
SIGNAL_WEB_PORT=$PORT
COMPOSE_PROFILES=
EOF
cat > "$WORK/signal.env" <<EOF
DEPLOY_ENV=hosted
CSRF_ALLOWED_ORIGINS=http://127.0.0.1:$PORT
AUTH_COOKIE_SECURE=false
AUTH_SIGNUP_ENABLED=false
AUTH_ADMIN_EMAIL=deploy-rehearsal@rehearsal.test
AUTH_ADMIN_PASSWORD=deploy-rehearsal-only
SCHEDULER_ENABLED=false
TELEGRAM_NOTIFICATIONS_ENABLED=false
RESULTS_SYNC_ENABLED=false
EOF
chmod 0600 "$WORK/signal.env"
before=$(sha256sum "$SIGNAL_DEPLOY_DIR/.env")

# ── validate changes nothing ─────────────────────────────────────────────────
deploy_cmd validate "$SHA_A" > "$WORK/validate.txt" 2>&1 || fail "validate: $(cat "$WORK/validate.txt")"
[ "$(sha256sum "$SIGNAL_DEPLOY_DIR/.env")" = "$before" ] && pass "validate left deploy/.env untouched" || fail ".env changed"
[ -z "$(cd "$SIGNAL_DEPLOY_DIR" && docker compose ps -q)" ] && pass "validate started no container" || fail "containers started"
if deploy_cmd validate "$(printf 'd%.0s' $(seq 1 40))" > /dev/null 2>&1; then fail "validate accepted a missing release"; fi
pass "validate refuses a release that is not in the registry"
if deploy_cmd deploy "not-a-sha" > /dev/null 2>&1; then fail "a malformed sha was accepted"; fi
pass "deploy refuses a malformed sha"

# ── First deploy (empty host), then B, then rollback ─────────────────────────
deploy_cmd deploy "$SHA_A" --no-wait-cycle > "$WORK/a.txt" 2>&1 || fail "deploy A: $(cat "$WORK/a.txt")"
digest_a=$(current BACKEND)
[[ "$digest_a" == "$REG/signal-backend@sha256:"* ]] && pass "deploy A pinned a digest" || fail "not a digest: $digest_a"
has "$(cat "$WORK/a.txt")" "nothing to back up" && pass "first deploy on an empty host skips the backup" || fail "first-deploy backup"
curl -fsS "http://127.0.0.1:$PORT/health" > /dev/null && pass "A is healthy through nginx" || fail "A health"

deploy_cmd deploy "$SHA_B" --no-wait-cycle > "$WORK/b.txt" 2>&1 || fail "deploy B: $(cat "$WORK/b.txt")"
digest_b=$(current BACKEND)
[ "$digest_b" != "$digest_a" ] && [[ "$digest_b" == *"@sha256:"* ]] && pass "deploy B pinned a different digest" || fail "B digest"
sudo find "$WORK/data/backups" -name "pre-deploy_bbbbbbbbbbbb_*.db" | grep -q . && pass "pre-deploy backup taken before B" || fail "no pre-deploy backup"
[ "$(docker inspect -f '{{.Config.Labels.rehearsal}}' "$(cd "$SIGNAL_DEPLOY_DIR" && docker compose ps -q api)")" = "b" ] \
  && pass "the API now runs release B" || fail "API is not B"

deploy_cmd rollback > "$WORK/rb.txt" 2>&1 || fail "rollback: $(cat "$WORK/rb.txt")"
[ "$(current BACKEND)" = "$digest_a" ] && pass "rollback returned to A's digest" || fail "rollback digest"
curl -fsS "http://127.0.0.1:$PORT/health" > /dev/null && pass "healthy after rollback" || fail "health after rollback"

# ── A broken release is rolled back automatically ───────────────────────────
if deploy_cmd deploy "$SHA_C" --no-wait-cycle > "$WORK/c.txt" 2>&1; then fail "the broken release C was accepted"; fi
has "$(cat "$WORK/c.txt")" "was rolled back" && pass "broken release C was rolled back automatically" || fail "C: $(cat "$WORK/c.txt")"
[ "$(current BACKEND)" = "$digest_a" ] && curl -fsS "http://127.0.0.1:$PORT/health" > /dev/null \
  && pass "the previous release (A) is running and healthy" || fail "after C"
grep -q "auto-rollback after failed sha=$SHA_C" "$SIGNAL_DEPLOY_DIR/releases.log" && pass "releases.log records it" || fail "releases.log"

deploy_cmd status > "$WORK/status.txt" 2>&1 || fail "status"
has "$(cat "$WORK/status.txt")" "health through nginx: ok" && pass "status" || fail "status: $(cat "$WORK/status.txt")"

# ── The SSH forced command passes only the allowlist ─────────────────────────
sudo mkdir -p /opt/signal/deploy
if [ ! -e /opt/signal/deploy/signal-deploy.sh ]; then
  printf '#!/bin/sh\necho "STUB $*"\n' | sudo tee /opt/signal/deploy/signal-deploy.sh > /dev/null
  sudo chmod 0755 /opt/signal/deploy/signal-deploy.sh
  sudo touch /opt/signal-rehearsal-stub
fi
ssh_cmd() { SSH_ORIGINAL_COMMAND="$1" sh "$SRC/host/signal-deploy-ssh" 2>&1; }
[ "$(ssh_cmd "deploy $SHA_B --class 2")" = "STUB deploy $SHA_B --class 2" ] && pass "forced command: deploy passes" || fail "deploy via ssh"
[ "$(ssh_cmd "status")" = "STUB status" ] && pass "forced command: status passes" || fail "status via ssh"
for bad in "deploy $SHA_B --class 3" "deploy $SHA_B; rm -rf /" "bash" "deploy abc" "rollback now" ""; do
  has "$(ssh_cmd "$bad" || true)" "refused" || fail "forced command allowed: '$bad'"
done
pass "forced command refuses class 3, injection, shells and malformed input"
[ -e /opt/signal-rehearsal-stub ] && sudo rm -f /opt/signal/deploy/signal-deploy.sh

echo "deploy rehearsal passed"
