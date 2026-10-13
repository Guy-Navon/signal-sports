#!/usr/bin/env bash
# Signal Sports — weekly SANITIZED dev snapshot (HOSTING_PLAN §12.3, #270). Run
# as root on the host by deploy/systemd/signal-devsnap.timer, or by hand.
#
#   deploy/devsnap.sh               make, verify, encrypt to the DEV key, upload
#   deploy/devsnap.sh --validate    check config, tools and access; change nothing
#
# A separate path from full backups, on purpose:
#   - content:   scripts/make_dev_snapshot.py (sessions and credentials removed,
#                personal fields rewritten, every id kept, verified, VACUUM INTO)
#   - key:       DEVSNAP_RECIPIENTS_FILE, the DEV public key. Dev holds its
#                private key; dev never holds a key that decrypts a full backup.
#   - target:    DEVSNAP_TARGET with its own write-only credentials
#                (DEVSNAP_B2_APPLICATION_KEY_ID / _KEY), never the backup key.
# Config: the same /etc/signal/backup.env (root:root 0600).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=deploy/lib.sh
. "$HERE/lib.sh"

VALIDATE=0
[ "${1:-}" = "--validate" ] && VALIDATE=1
[ $# -le 1 ] || die "usage: devsnap.sh [--validate]"

load_deploy_env
load_config "${SIGNAL_BACKUP_CONF:-/etc/signal/backup.env}"
: "${DEVSNAP_RECIPIENTS_FILE:?set in the backup config}"
: "${DEVSNAP_TARGET:?set in the backup config}"
DEVSNAP_PREFIX=${DEVSNAP_PREFIX:-devsnap}
DEVSNAP_ENC_DIR=${DEVSNAP_ENC_DIR:-$(dirname "$SIGNAL_DATA_DIR")/devsnap-enc}
DEVSNAP_KEEP=${DEVSNAP_KEEP:-4}
require_tools docker age gzip python3 flock

[ -s "$DEVSNAP_RECIPIENTS_FILE" ] || die "no recipients in $DEVSNAP_RECIPIENTS_FILE"
if grep -q "AGE-SECRET-KEY" "$DEVSNAP_RECIPIENTS_FILE"; then
  die "$DEVSNAP_RECIPIENTS_FILE holds a PRIVATE key; only public recipients belong on the host"
fi
if [ -n "${BACKUP_RECIPIENTS_FILE:-}" ] && [ -r "$BACKUP_RECIPIENTS_FILE" ] \
   && grep -qxFf "$BACKUP_RECIPIENTS_FILE" "$DEVSNAP_RECIPIENTS_FILE"; then
  die "a FULL-BACKUP recipient is in $DEVSNAP_RECIPIENTS_FILE; dev and backup keys must differ"
fi

# The uploader reads B2_* names; give it the dev-snapshot key for this run only.
upload_env=()
if [ "${DEVSNAP_TARGET%%:*}" = "b2" ]; then
  : "${DEVSNAP_B2_APPLICATION_KEY_ID:?set for a b2 target}"
  : "${DEVSNAP_B2_APPLICATION_KEY:?set for a b2 target}"
  upload_env=(env "B2_APPLICATION_KEY_ID=$DEVSNAP_B2_APPLICATION_KEY_ID"
                  "B2_APPLICATION_KEY=$DEVSNAP_B2_APPLICATION_KEY")
fi

if [ "$VALIDATE" = 1 ]; then
  compose config --quiet
  probe=$(mktemp --suffix=.age)
  echo validate | age -R "$DEVSNAP_RECIPIENTS_FILE" -o "$probe"
  "${upload_env[@]}" python3 "$HERE/offsite_upload.py" --dry-run --file "$probe" \
    --name "$DEVSNAP_PREFIX/validate/probe.age" --target "$DEVSNAP_TARGET" > /dev/null
  rm -f "$probe"
  log "validate: dev-snapshot config, recipients and tools OK; nothing was made or uploaded"
  exit 0
fi

take_lock
stamp=$(utc_stamp)
log "1/3 sanitized snapshot + verify"
compose run --rm -T --no-deps api python scripts/make_dev_snapshot.py \
  --src /app/data/signal_sports.db --out "/app/data/devsnap/devsnap_${stamp}.db" --manifest
plain="$SIGNAL_DATA_DIR/devsnap/devsnap_${stamp}.db"
[ -s "$plain" ] || die "snapshot file missing: $plain"

log "2/3 compress + encrypt to the DEV key"
install -d -m 0700 "$DEVSNAP_ENC_DIR"
encrypted="$DEVSNAP_ENC_DIR/devsnap_${stamp}.db.gz.age"
umask 077
gzip -9 -c "$plain" | age -R "$DEVSNAP_RECIPIENTS_FILE" -o "$encrypted.partial"
mv "$encrypted.partial" "$encrypted"
rm -f "$plain"   # the plaintext snapshot is not kept on the host

log "3/3 upload to the dev-snapshot target"
"${upload_env[@]}" python3 "$HERE/offsite_upload.py" --file "$encrypted" \
  --name "$DEVSNAP_PREFIX/devsnap_${stamp}.db.gz.age" --target "$DEVSNAP_TARGET"

# Keep the newest DEVSNAP_KEEP encrypted snapshots locally.
mapfile -t old < <(ls -1t "$DEVSNAP_ENC_DIR"/devsnap_*.db.gz.age 2> /dev/null | tail -n +"$((DEVSNAP_KEEP + 1))")
[ "${#old[@]}" -eq 0 ] || rm -f -- "${old[@]}"
log "dev snapshot done: devsnap_${stamp}"
