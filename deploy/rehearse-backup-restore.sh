#!/usr/bin/env bash
# Signal Sports — end-to-end rehearsal of backup, encryption, off-host copy,
# restore, undo and the dev snapshot, on a THROWAWAY stack (#266, #270).
#
#   deploy/rehearse-backup-restore.sh <backend-image> <web-image>
#
# Everything is temporary: its own Compose project, a temp data dir, a
# generated age key pair, a local "off-host" directory and a local fake
# monitor. Nothing touches /srv/signal, /etc/signal, a bucket or the network
# beyond the local Docker daemon. Used by CI (images.yml). Needs docker, age,
# python3, curl, sudo and flock.
set -euo pipefail

BACKEND_IMAGE=${1:?usage: rehearse-backup-restore.sh <backend-image> <web-image>}
WEB_IMAGE=${2:?usage: rehearse-backup-restore.sh <backend-image> <web-image>}
SRC=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
PORT=18090
BASE="http://127.0.0.1:${PORT}"
ORIGIN=$BASE
export COMPOSE_PROJECT_NAME="signal-rehearsal-$$"
export SIGNAL_DEPLOY_DIR="$WORK/deploy"
export SIGNAL_LOCK="$WORK/ops.lock"
export SIGNAL_BACKUP_CONF="$WORK/backup.env"

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
has() { [[ "$1" == *"$2"* ]]; }

cleanup() {
  [ -n "${MONITOR_PID:-}" ] && kill "$MONITOR_PID" 2> /dev/null || true
  (cd "$SIGNAL_DEPLOY_DIR" 2> /dev/null && docker compose --profile worker logs --no-color > "$WORK/compose.log" 2>&1) || true
  (cd "$SIGNAL_DEPLOY_DIR" 2> /dev/null && docker compose --profile worker down -v --remove-orphans > /dev/null 2>&1) || true
  docker rm -f signal-restore-rehearsal > /dev/null 2>&1 || true
  [ "${KEEP_REHEARSAL_LOGS:-}" = "1" ] && cp "$WORK/compose.log" ./rehearsal-compose.log 2> /dev/null || true
  sudo rm -rf "$WORK"
}
trap cleanup EXIT

# ── A throwaway deployment ───────────────────────────────────────────────────
mkdir -p "$SIGNAL_DEPLOY_DIR" "$WORK/data" "$WORK/offsite" "$WORK/keys"
cp "$SRC"/compose.yaml "$SRC"/lib.sh "$SRC"/backup.sh "$SRC"/devsnap.sh "$SRC"/restore.sh \
   "$SRC"/offsite_upload.py "$SIGNAL_DEPLOY_DIR/"
sudo chown 10001:10001 "$WORK/data"
sudo chmod 0700 "$WORK/data"
cat > "$SIGNAL_DEPLOY_DIR/.env" <<EOF
SIGNAL_BACKEND_IMAGE=$BACKEND_IMAGE
SIGNAL_WEB_IMAGE=$WEB_IMAGE
SIGNAL_ENV_FILE=$WORK/signal.env
SIGNAL_DATA_DIR=$WORK/data
SIGNAL_WEB_PORT=$PORT
COMPOSE_PROFILES=
EOF
cat > "$WORK/signal.env" <<EOF
DEPLOY_ENV=hosted
CSRF_ALLOWED_ORIGINS=$ORIGIN
AUTH_COOKIE_SECURE=false
AUTH_SIGNUP_ENABLED=false
AUTH_ADMIN_EMAIL=rehearsal-admin@rehearsal.test
AUTH_ADMIN_PASSWORD=rehearsal-only-password
SCHEDULER_ENABLED=false
TELEGRAM_NOTIFICATIONS_ENABLED=false
RESULTS_SYNC_ENABLED=false
EOF

# Keys: the "offline" backup key and the separate dev key.
age-keygen -o "$WORK/keys/backup.key" 2> /dev/null
age-keygen -o "$WORK/keys/dev.key" 2> /dev/null
age-keygen -y "$WORK/keys/backup.key" > "$WORK/backup-recipients.txt"
age-keygen -y "$WORK/keys/dev.key" > "$WORK/devsnap-recipients.txt"

# A local fake monitor that records which paths were pinged.
python3 - "$WORK/pings.log" <<'PY' &
import http.server, sys
log = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        open(log, "a").write(self.path + "\n")
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", 18099), H).serve_forever()
PY
MONITOR_PID=$!

cat > "$SIGNAL_BACKUP_CONF" <<EOF
BACKUP_RECIPIENTS_FILE=$WORK/backup-recipients.txt
BACKUP_ENC_DIR=$WORK/backups-enc
OFFSITE_TARGET=local:$WORK/offsite
OFFSITE_PREFIX=prod
MONITOR_BACKUP_URL=http://127.0.0.1:18099/ping/backup-check
LOCAL_KEEP_DAYS=7
DEVSNAP_RECIPIENTS_FILE=$WORK/devsnap-recipients.txt
DEVSNAP_ENC_DIR=$WORK/devsnap-enc
DEVSNAP_TARGET=local:$WORK/offsite-dev
EOF
chmod 0600 "$SIGNAL_BACKUP_CONF"

cd "$SIGNAL_DEPLOY_DIR"
docker compose up -d --wait --wait-timeout 120 api web > /dev/null && pass "throwaway stack up"

login() {
  curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" -H "Origin: $ORIGIN" \
    -H 'Content-Type: application/json' \
    -d '{"email":"rehearsal-admin@rehearsal.test","password":"rehearsal-only-password"}'
}
sessions() {
  docker compose run --rm -T --no-deps --entrypoint python api -c \
    "import sqlite3; print(sqlite3.connect('/app/data/signal_sports.db').execute('SELECT COUNT(*) FROM auth_sessions').fetchone()[0])"
}
[ "$(login)" = "200" ] && pass "admin login (1 session)" || fail "login"
[ "$(sessions)" = "1" ] || fail "expected 1 session"

# ── Validate mode changes nothing ────────────────────────────────────────────
sudo -E bash ./backup.sh --validate && pass "backup.sh --validate"
[ -z "$(ls -A "$WORK/offsite")" ] && pass "validate uploaded nothing" || fail "validate uploaded something"

# ── Nightly backup: copy -> encrypt -> off-host -> ping ───────────────────────
sudo -E bash ./backup.sh && pass "backup.sh ran"
object=$(sudo find "$WORK/offsite" -name 'signal_*.db.gz.age' | head -1)
[ -n "$object" ] && pass "encrypted object off-host: ${object#"$WORK"/offsite/}" || fail "no off-host object"
[ "$(cat "$WORK/pings.log")" = "/ping/backup-check" ] && pass "backup-ok pinged once, after the upload" || fail "pings: $(cat "$WORK/pings.log")"
if sudo head -c 64 "$object" | grep -qa "SQLite format"; then fail "object is not encrypted"; fi
pass "object is ciphertext (no SQLite header)"

# A change AFTER the backup: this is the loss window a restore gives up.
[ "$(login)" = "200" ] && [ "$(sessions)" = "2" ] && pass "post-backup change (2 sessions)" || fail "post-backup login"

# ── Decrypt as the owner would (the private key never goes to the host) ──────
sudo cat "$object" | age -d -i "$WORK/keys/backup.key" | gunzip > "$WORK/restored.db"
if age -d -i "$WORK/keys/dev.key" < <(sudo cat "$object") > /dev/null 2>&1; then
  fail "the DEV key decrypted a full backup"
fi
pass "only the backup key decrypts the backup; the dev key cannot"

sudo -E bash ./restore.sh verify "$WORK/restored.db" > "$WORK/verify.txt" && pass "restore.sh verify" || fail "verify: $(cat "$WORK/verify.txt")"

# ── Restore: stop writers, swap the set, start with Telegram off ─────────────
sudo -E bash ./restore.sh apply "$WORK/restored.db" --confirm > "$WORK/apply.txt" 2>&1 || fail "apply: $(cat "$WORK/apply.txt")"
has "$(cat "$WORK/apply.txt")" "running with Telegram OFF" && pass "restore.sh apply (Telegram forced off)" || fail "apply output"
curl -fsS "$BASE/health" > /dev/null && pass "API healthy after restore" || fail "health after restore"
[ "$(sessions)" = "1" ] && pass "data is the backup's (the post-backup session is gone)" || fail "sessions after restore: $(sessions)"
pre=$(sudo find "$WORK/data" -maxdepth 1 -type d -name 'pre-restore-*' | head -1)
sudo test -f "$pre/signal_sports.db" && pass "previous set kept in ${pre##*/}" || fail "no pre-restore copy"
sudo test ! -e "$WORK/data/signal_sports.db-wal.incoming" || fail "leftover"

# The restore refuses a sanitized dev snapshot as production.
docker compose run --rm -T --no-deps api python scripts/make_dev_snapshot.py \
  --src /app/data/signal_sports.db --out /app/data/devsnap/check.db > /dev/null
sudo cp "$WORK/data/devsnap/check.db" "$WORK/dev-as-prod.db"
if sudo -E bash ./restore.sh apply "$WORK/dev-as-prod.db" --confirm > "$WORK/refuse.txt" 2>&1; then
  fail "a dev snapshot was accepted as production"
fi
has "$(cat "$WORK/refuse.txt")" "SANITIZED dev snapshot" && pass "restore refuses a dev snapshot" || fail "refusal: $(cat "$WORK/refuse.txt")"

# ── Undo the restore ─────────────────────────────────────────────────────────
sudo -E bash ./restore.sh undo "$pre" --confirm > /dev/null 2>&1 || fail "undo"
[ "$(sessions)" = "2" ] && pass "undo brought the post-backup state back" || fail "sessions after undo: $(sessions)"
sudo -E bash ./restore.sh resume > /dev/null 2>&1 && curl -fsS "$BASE/health" > /dev/null && pass "resume" || fail "resume"

# ── Dev snapshot: sanitized, encrypted to the DEV key only ───────────────────
sudo -E bash ./devsnap.sh > /dev/null && pass "devsnap.sh ran"
snap=$(sudo find "$WORK/offsite-dev" -name 'devsnap_*.db.gz.age' | head -1)
[ -n "$snap" ] || fail "no dev snapshot object"
if age -d -i "$WORK/keys/backup.key" < <(sudo cat "$snap") > /dev/null 2>&1; then
  fail "the BACKUP key decrypted a dev snapshot (keys must be separate)"
fi
sudo cat "$snap" | age -d -i "$WORK/keys/dev.key" | gunzip > "$WORK/dev.db"
python3 - "$WORK/dev.db" <<'PY' && pass "dev snapshot: no real email, no hash, no session, ids kept"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
assert c.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
assert c.execute("SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL").fetchone()[0] == 0
emails = [r[0] for r in c.execute("SELECT email FROM users WHERE email IS NOT NULL")]
assert emails and all(e.endswith("@example.invalid") and e.startswith("user-") for e in emails), emails
assert c.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] > 0
raw = open(sys.argv[1], "rb").read()
assert b"rehearsal-admin@rehearsal.test" not in raw
PY
sudo test ! -e "$WORK/data/devsnap/$(basename "${snap%.gz.age}")" && pass "plaintext dev snapshot not kept on the host" || fail "plaintext kept"

echo "rehearsal passed"
