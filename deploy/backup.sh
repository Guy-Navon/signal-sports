#!/usr/bin/env bash
# Signal Sports — nightly off-host backup (#266). Run as root on the host by
# deploy/systemd/signal-backup.timer, or by hand.
#
#   deploy/backup.sh               take, encrypt, upload, ping
#   deploy/backup.sh --validate    check config, tools and access; change nothing
#
# Three separate steps; each must succeed before the next:
#   1. COPY     scripts/backup_db.py inside the backend image, as the service
#               uid: the WAL-safe backup API, then integrity / foreign-key /
#               count verification. Lands in $SIGNAL_DATA_DIR/backups.
#   2. ENCRYPT  gzip + age to the BACKUP public key(s). The private key is
#               offline (the owner); it is never on this host or in dev.
#   3. UPLOAD   deploy/offsite_upload.py (write-only key; only *.age leaves).
# Then, and only then, MONITOR_BACKUP_URL is pinged. Any failure pings
# MONITOR_BACKUP_URL/fail and exits non-zero. Local copies older than
# LOCAL_KEEP_DAYS are pruned; REMOTE cleanup is the bucket's lifecycle rules,
# so this host never holds a delete permission.
#
# Config: /etc/signal/backup.env (root:root 0600), see deploy/backup.env.example.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=deploy/lib.sh
. "$HERE/lib.sh"

VALIDATE=0
[ "${1:-}" = "--validate" ] && VALIDATE=1
[ $# -le 1 ] || die "usage: backup.sh [--validate]"

load_deploy_env
load_config "${SIGNAL_BACKUP_CONF:-/etc/signal/backup.env}"
: "${BACKUP_RECIPIENTS_FILE:?set in the backup config}"
: "${OFFSITE_TARGET:?set in the backup config}"
OFFSITE_PREFIX=${OFFSITE_PREFIX:-prod}
BACKUP_ENC_DIR=${BACKUP_ENC_DIR:-$(dirname "$SIGNAL_DATA_DIR")/backups-enc}
LOCAL_KEEP_DAYS=${LOCAL_KEEP_DAYS:-7}
require_tools docker age gzip python3 curl flock

# Any non-zero exit of a real run (a failed command or a die) reports /fail.
DONE=0
on_exit() {
  local rc=$?
  if [ "$VALIDATE" = 0 ] && [ "$DONE" = 0 ]; then
    log "backup FAILED (exit $rc); the off-host backup was NOT made"
    ping_url "${MONITOR_BACKUP_URL:-}" fail
  fi
}
trap on_exit EXIT

[ -s "$BACKUP_RECIPIENTS_FILE" ] || die "no recipients in $BACKUP_RECIPIENTS_FILE"
if grep -q "AGE-SECRET-KEY" "$BACKUP_RECIPIENTS_FILE"; then
  die "$BACKUP_RECIPIENTS_FILE holds a PRIVATE key; only public recipients belong on the host"
fi
compose config --quiet

if [ "$VALIDATE" = 1 ]; then
  probe=$(mktemp --suffix=.age)
  echo validate | age -R "$BACKUP_RECIPIENTS_FILE" -o "$probe"
  python3 "$HERE/offsite_upload.py" --dry-run --file "$probe" \
    --name "$OFFSITE_PREFIX/validate/probe.age" --target "$OFFSITE_TARGET" > /dev/null
  rm -f "$probe"
  log "validate: config, recipients, tools and compose OK; nothing was backed up or uploaded"
  exit 0
fi

take_lock
stamp=$(utc_stamp)
case "$(date -u +%d):$(date -u +%u)" in
  01:*) tier=monthly ;;
  *:7)  tier=weekly ;;
  *)    tier=daily ;;
esac

log "1/3 copy + verify"
compose run --rm -T --no-deps api \
  python scripts/backup_db.py "/app/data/backups/backup_${stamp}.db" --manifest
plain="$SIGNAL_DATA_DIR/backups/backup_${stamp}.db"
[ -s "$plain" ] || die "backup file missing: $plain"

log "2/3 compress + encrypt (age, public recipients only)"
install -d -m 0700 "$BACKUP_ENC_DIR"
encrypted="$BACKUP_ENC_DIR/signal_${stamp}.db.gz.age"
umask 077
gzip -9 -c "$plain" | age -R "$BACKUP_RECIPIENTS_FILE" -o "$encrypted.partial"
mv "$encrypted.partial" "$encrypted"

log "3/3 upload off-host ($tier)"
result=$(python3 "$HERE/offsite_upload.py" --file "$encrypted" \
  --name "$OFFSITE_PREFIX/$tier/signal_${stamp}.db.gz.age" --target "$OFFSITE_TARGET")
log "uploaded: $result"

DONE=1
ping_url "${MONITOR_BACKUP_URL:-}"

find "$SIGNAL_DATA_DIR/backups" -maxdepth 1 -type f \
  \( -name 'backup_*.db' -o -name 'backup_*.db.manifest.json' \) -mtime +"$LOCAL_KEEP_DAYS" -delete
find "$BACKUP_ENC_DIR" -maxdepth 1 -type f -name 'signal_*.db.gz.age' -mtime +"$LOCAL_KEEP_DAYS" -delete
log "backup done: $tier signal_${stamp}"
