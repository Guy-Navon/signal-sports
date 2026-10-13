#!/usr/bin/env bash
# Signal Sports — restore the corpus from a DECRYPTED backup (#266, HOSTING_PLAN
# §12.4). Run as root on the host. Decrypt on the PC (the backup private key
# never comes to the host), then copy the plain .db here over the admin path.
#
#   deploy/restore.sh verify   <backup.db>           integrity, FKs, counts (read-only)
#   deploy/restore.sh rehearse <backup.db>           a second API on 127.0.0.1:18081 over a
#                                                    scratch copy; side effects off
#   deploy/restore.sh rehearse --stop                remove the rehearsal container
#   deploy/restore.sh apply    <backup.db> --confirm REPLACE the corpus (see below)
#   deploy/restore.sh outbox                         notification outbox by status
#   deploy/restore.sh resume                         normal settings again (Telegram as configured)
#   deploy/restore.sh undo     <pre-restore-dir> --confirm   put the previous set back
#
# apply:
#   1. verifies the candidate; refuses a sanitized dev snapshot
#   2. stops EVERY writer: the worker, the API and any other container that
#      mounts the data dir; holds the ops lock so backup/devsnap/deploy wait
#   3. moves signal_sports.db, -wal and -shm TOGETHER into
#      $SIGNAL_DATA_DIR/pre-restore-<UTC>/ (never deletes them)
#   4. installs the candidate as signal_sports.db (uid 10001, 0600) with no
#      stale -wal/-shm beside it, and re-verifies it in place
#   5. starts the API, then the worker, with TELEGRAM_NOTIFICATIONS_ENABLED=false:
#      the restored outbox and watermarks date from the backup and could
#      re-send or suppress pushes. Review `outbox`, then run `resume`.
# If anything fails after step 3, run `undo <pre-restore-dir> --confirm`.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=deploy/lib.sh
. "$HERE/lib.sh"

REHEARSAL_NAME=${REHEARSAL_NAME:-signal-restore-rehearsal}
REHEARSAL_PORT=${REHEARSAL_PORT:-18081}

usage() { sed -n '2,25p' "$0"; exit 2; }

verify_file() {
  # Read-only mount + immutable open: verification cannot change the file.
  local file
  file=$(readlink -f "$1")
  [ -f "$file" ] || die "no such file: $1"
  # Root inside the throwaway container: the candidate may be a root-owned 0600 file.
  docker run --rm --network none --read-only --user 0:0 \
    -v "$file:/restore/candidate.db:ro" --entrypoint python "$SIGNAL_BACKEND_IMAGE" \
    scripts/verify_db.py /restore/candidate.db
}

refuse_dev_snapshot() {
  local file
  file=$(readlink -f "$1")
  # make_dev_snapshot.py rewrites every account email to user-<id>@example.invalid
  # and removes every password hash; a production corpus has neither pattern.
  local counts
  counts=$(docker run --rm --network none --read-only --user 0:0 -v "$file:/restore/c.db:ro" \
    --entrypoint python "$SIGNAL_BACKEND_IMAGE" -c \
    "import sqlite3; c=sqlite3.connect('file:/restore/c.db?mode=ro&immutable=1', uri=True); q=lambda s: c.execute(s).fetchone()[0]; \
print(q('SELECT COUNT(*) FROM users WHERE email IS NOT NULL'), \
q(\"SELECT COUNT(*) FROM users WHERE email LIKE 'user-%@example.invalid'\"), \
q('SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL'))")
  local total rewritten hashes
  read -r total rewritten hashes <<< "$counts"
  if [ "$total" -gt 0 ] && [ "$rewritten" -eq "$total" ] && [ "$hashes" -eq 0 ]; then
    die "this looks like a SANITIZED dev snapshot (all emails rewritten, no password hashes); refusing to restore it as production"
  fi
}

writers_on_data_dir() {
  local id
  for id in $(docker ps -q); do
    if docker inspect -f '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' "$id" | grep -qxF "$SIGNAL_DATA_DIR"; then
      docker inspect -f '{{.Name}}' "$id"
    fi
  done
}

stop_writers() {
  log "stopping the worker, then the API (the worker finishes its cycle first)"
  compose --profile worker stop worker api
  systemctl stop signal-backup.timer signal-devsnap.timer 2> /dev/null || true
  local left
  left=$(writers_on_data_dir)
  [ -z "$left" ] || die "still running with the data dir mounted: $left (stop them first)"
  if command -v fuser > /dev/null && fuser "$SIGNAL_DATA_DIR"/signal_sports.db* > /dev/null 2>&1; then
    die "a process still holds the database files (fuser)"
  fi
}

start_side_effects_off() {
  local override
  override=$(mktemp --suffix=.yaml)
  cat > "$override" <<'YAML'
services:
  api:
    environment:
      TELEGRAM_NOTIFICATIONS_ENABLED: "false"
  worker:
    environment:
      TELEGRAM_NOTIFICATIONS_ENABLED: "false"
YAML
  docker compose --project-directory "$SIGNAL_DEPLOY_DIR" -f "$SIGNAL_DEPLOY_DIR/compose.yaml" \
    -f "$override" up -d --wait --wait-timeout 180 api web
  if [[ ",${COMPOSE_PROFILES:-}," == *",worker,"* ]]; then
    docker compose --project-directory "$SIGNAL_DEPLOY_DIR" -f "$SIGNAL_DEPLOY_DIR/compose.yaml" \
      -f "$override" up -d worker
  fi
  rm -f "$override"
  log "running with Telegram OFF. Watch one cycle (docker compose logs -f worker),"
  log "review '$0 outbox', then run '$0 resume'."
}

swap_in() {
  # $1 = file to install as the corpus; moves the current set to $2 first.
  local candidate=$1 keep_dir=$2 name
  install -d -m 0700 -o "$SIGNAL_SERVICE_UID" -g "$SIGNAL_SERVICE_UID" "$keep_dir"
  for name in signal_sports.db signal_sports.db-wal signal_sports.db-shm; do
    [ -e "$SIGNAL_DATA_DIR/$name" ] && mv "$SIGNAL_DATA_DIR/$name" "$keep_dir/$name"
  done
  install -m 0600 -o "$SIGNAL_SERVICE_UID" -g "$SIGNAL_SERVICE_UID" "$candidate" \
    "$SIGNAL_DATA_DIR/signal_sports.db.incoming"
  mv "$SIGNAL_DATA_DIR/signal_sports.db.incoming" "$SIGNAL_DATA_DIR/signal_sports.db"
  for name in signal_sports.db-wal signal_sports.db-shm; do
    [ ! -e "$SIGNAL_DATA_DIR/$name" ] || die "stale $name beside the restored file"
  done
  verify_file "$SIGNAL_DATA_DIR/signal_sports.db" > /dev/null
}

cmd=${1:-}
[ -n "$cmd" ] || usage
shift
load_deploy_env
require_tools docker

case "$cmd" in
  verify)
    [ $# -eq 1 ] || usage
    verify_file "$1"
    ;;

  rehearse)
    if [ "${1:-}" = "--stop" ]; then
      docker rm -f "$REHEARSAL_NAME" > /dev/null 2>&1 || true
      log "rehearsal container removed (its scratch dir is kept)"
      exit 0
    fi
    [ $# -eq 1 ] || usage
    verify_file "$1" > /dev/null
    scratch="$(dirname "$SIGNAL_DATA_DIR")/restore-scratch/$(utc_stamp)"
    install -d -m 0700 -o "$SIGNAL_SERVICE_UID" -g "$SIGNAL_SERVICE_UID" "$scratch"
    install -m 0600 -o "$SIGNAL_SERVICE_UID" -g "$SIGNAL_SERVICE_UID" "$1" "$scratch/signal_sports.db"
    docker run -d --rm --name "$REHEARSAL_NAME" -p "127.0.0.1:${REHEARSAL_PORT}:8000" \
      --user "$SIGNAL_SERVICE_UID:$SIGNAL_SERVICE_UID" --read-only --tmpfs /tmp \
      --env-file "${SIGNAL_ENV_FILE:?}" \
      -e DATABASE_URL=sqlite:////app/data/signal_sports.db \
      -e SCHEDULER_ENABLED=false -e TELEGRAM_NOTIFICATIONS_ENABLED=false \
      -e RESULTS_SYNC_ENABLED=false -e CLASSIFICATION_PROVIDER=disabled \
      -e AUTH_COOKIE_SECURE=false -e CSRF_ALLOWED_ORIGINS="http://127.0.0.1:${REHEARSAL_PORT}" \
      -v "$scratch:/app/data" "$SIGNAL_BACKEND_IMAGE" > /dev/null
    for _ in $(seq 1 60); do
      curl -fsS "http://127.0.0.1:${REHEARSAL_PORT}/health" > /dev/null 2>&1 && break
      sleep 1
    done
    curl -fsS "http://127.0.0.1:${REHEARSAL_PORT}/health" > /dev/null || die "rehearsal API did not come up"
    log "rehearsal API on http://127.0.0.1:${REHEARSAL_PORT} (scratch copy: $scratch)."
    log "Open it through an SSH tunnel, check the feed, then: $0 rehearse --stop"
    ;;

  apply)
    [ $# -eq 2 ] && [ "$2" = "--confirm" ] || die "apply replaces the corpus: run '$0 apply <backup.db> --confirm'"
    candidate=$(readlink -f "$1")
    verify_file "$candidate"
    refuse_dev_snapshot "$candidate"
    take_lock
    stop_writers
    keep="$SIGNAL_DATA_DIR/pre-restore-$(utc_stamp)"
    swap_in "$candidate" "$keep"
    log "restored. The previous set is in $keep (undo: $0 undo $keep --confirm)"
    start_side_effects_off
    ;;

  outbox)
    compose run --rm -T --no-deps api python -c \
      "import sqlite3; c=sqlite3.connect('/app/data/signal_sports.db'); \
[print(f'{s:16} {n}') for s, n in c.execute('SELECT status, COUNT(*) FROM notification_events GROUP BY status ORDER BY status')]"
    ;;

  resume)
    compose up -d --wait --wait-timeout 180
    systemctl start signal-backup.timer signal-devsnap.timer 2> /dev/null || true
    log "normal settings restored (Telegram as configured); timers resumed"
    ;;

  undo)
    [ $# -eq 2 ] && [ "$2" = "--confirm" ] || die "run '$0 undo <pre-restore-dir> --confirm'"
    previous=$(readlink -f "$1")
    [ -f "$previous/signal_sports.db" ] || die "$previous holds no signal_sports.db"
    take_lock
    stop_writers
    failed="$SIGNAL_DATA_DIR/failed-restore-$(utc_stamp)"
    install -d -m 0700 -o "$SIGNAL_SERVICE_UID" -g "$SIGNAL_SERVICE_UID" "$failed"
    for name in signal_sports.db signal_sports.db-wal signal_sports.db-shm; do
      [ -e "$SIGNAL_DATA_DIR/$name" ] && mv "$SIGNAL_DATA_DIR/$name" "$failed/$name"
    done
    for name in signal_sports.db signal_sports.db-wal signal_sports.db-shm; do
      [ -e "$previous/$name" ] && mv "$previous/$name" "$SIGNAL_DATA_DIR/$name"
    done
    chown "$SIGNAL_SERVICE_UID:$SIGNAL_SERVICE_UID" "$SIGNAL_DATA_DIR"/signal_sports.db*
    log "previous set is back; the undone restore is in $failed"
    start_side_effects_off
    ;;

  *) usage ;;
esac
