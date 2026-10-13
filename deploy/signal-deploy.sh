#!/usr/bin/env bash
# Signal Sports — deploy, roll back and inspect the hosted stack (HOSTING_PLAN §9.1).
# Run as root on the host, normally through the SSH forced command
# (deploy/host/signal-deploy-ssh) from the owner's PC.
#
#   signal-deploy.sh validate <git-sha>             NON-MUTATING: resolve digests, preflight,
#                                                   print the plan. Pulls into the local image
#                                                   cache only; no config or container changes
#   signal-deploy.sh deploy   <git-sha> [--class 1|2] [--no-wait-cycle]
#   signal-deploy.sh deploy   <git-sha> --class 3 --plan-acknowledged
#   signal-deploy.sh rollback                       back to the previous release's digests
#   signal-deploy.sh status
#
# deploy:
#   1. resolve <repo>/signal-{backend,web}:sha-<git-sha> to immutable DIGESTS
#   2. preflight: compose config, disk space, data-dir ownership, env-file mode,
#      and the NEW image's own DEPLOY_ENV startup checks against the real
#      settings (a refused configuration stops here, before anything changes)
#   3. a verified local backup (class 1/2), or the full off-host backup.sh (class 3)
#   4. pin the digests in deploy/.env (the old file is kept as .env.previous)
#   5. recreate api + web, then the worker (it finishes its cycle: stop grace 300 s)
#   6. verify: health through nginx, the worker heartbeat, and (when the worker
#      runs) one completed cycle after the deploy
#   7. class 1/2 failure: automatic rollback to the previous digests.
#      class 3 (data semantics, HOSTING_PLAN §12.5): NO automatic rollback; old
#      code may misread new data. Restore the pre-deploy backup or roll forward.
# Every release is appended to deploy/releases.log.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=deploy/lib.sh
. "$HERE/lib.sh"

RELEASES="$SIGNAL_DEPLOY_DIR/releases.log"
ENV_FILE="$SIGNAL_DEPLOY_DIR/.env"
MIN_FREE_MB=${SIGNAL_MIN_FREE_MB:-2048}
WAIT_SECONDS=${SIGNAL_DEPLOY_WAIT_SECONDS:-180}

usage() { sed -n '2,13p' "$0"; exit 2; }

valid_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "not a full 40-character git sha: $1"; }

repo() { echo "${SIGNAL_IMAGE_REPO:?set SIGNAL_IMAGE_REPO in deploy/.env, e.g. ghcr.io/<owner>}"; }

# <ref> -> <repo>@sha256:..., pulling it into the local cache.
resolve_digest() {
  local ref=$1 name digest
  name=${ref%:*}
  docker pull -q "$ref" > /dev/null || die "cannot pull $ref (published? readable from this host?)"
  digest=$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$ref" \
    | grep -F "${name}@sha256:" | head -1)
  [ -n "$digest" ] || die "no registry digest for $ref"
  echo "$digest"
}

health_url() { echo "http://${SIGNAL_WEB_BIND:-127.0.0.1}:${SIGNAL_WEB_PORT:-8080}/health"; }

worker_enabled() { [[ ",${COMPOSE_PROFILES:-}," == *",worker,"* ]]; }

preflight() {
  local backend=$1 web=$2 free
  SIGNAL_BACKEND_IMAGE=$backend SIGNAL_WEB_IMAGE=$web compose config --quiet \
    || die "compose config failed with the new images"
  free=$(df -Pm "$SIGNAL_DATA_DIR" | awk 'NR==2 {print $4}')
  [ "$free" -ge "$MIN_FREE_MB" ] || die "only ${free} MB free on the data filesystem (need $MIN_FREE_MB)"
  [ "$(stat -c %u "$SIGNAL_DATA_DIR")" = "$SIGNAL_SERVICE_UID" ] \
    || die "$SIGNAL_DATA_DIR must be owned by uid $SIGNAL_SERVICE_UID"
  [ -r "$SIGNAL_ENV_FILE" ] || die "missing app settings $SIGNAL_ENV_FILE"
  [ "$(stat -c %a "$SIGNAL_ENV_FILE")" = "600" ] || log "warning: $SIGNAL_ENV_FILE should be mode 0600"
  # The new code judges the real settings before anything changes.
  docker run --rm --network none --read-only --env-file "$SIGNAL_ENV_FILE" \
    -e DATABASE_URL=sqlite:////tmp/preflight.db --tmpfs /tmp --entrypoint python "$backend" -c \
    "from app.core.deploy_mode import validate_deploy_startup_config as v; [print('warning:', w) for w in v()]" \
    || die "the new image refuses the current settings (see above); nothing was changed"
}

pin_images() {
  local backend=$1 web=$2 tmp
  tmp=$(mktemp "$ENV_FILE.XXXXXX")
  grep -v -e '^SIGNAL_BACKEND_IMAGE=' -e '^SIGNAL_WEB_IMAGE=' "$ENV_FILE" > "$tmp" || true
  printf 'SIGNAL_BACKEND_IMAGE=%s\nSIGNAL_WEB_IMAGE=%s\n' "$backend" "$web" >> "$tmp"
  chmod 0644 "$tmp"
  mv "$tmp" "$ENV_FILE"
  export SIGNAL_BACKEND_IMAGE=$backend SIGNAL_WEB_IMAGE=$web
}

last_cycle_after() {
  # Prints the status of the newest cycle that finished after $1 (ISO UTC), if any.
  compose run --rm -T --no-deps --entrypoint python api -c \
    "import sqlite3,sys; r=sqlite3.connect('/app/data/signal_sports.db').execute(\"SELECT status FROM scheduler_cycles WHERE finished_at > ? AND status != 'skipped_active_run' ORDER BY finished_at DESC LIMIT 1\", (sys.argv[1],)).fetchone(); print(r[0] if r else '')" \
    "$1" 2> /dev/null || true
}

bring_up_and_verify() {
  local since=$1 wait_cycle=$2
  compose up -d --wait --wait-timeout "$WAIT_SECONDS" api web || return 1
  curl -fsS -m 10 "$(health_url)" > /dev/null || { log "health through nginx failed"; return 1; }
  if worker_enabled; then
    compose up -d --wait --wait-timeout 420 worker || return 1
    if [ "$wait_cycle" = 1 ]; then
      local deadline status
      deadline=$(( $(date +%s) + ${SCHEDULER_INTERVAL_SECONDS:-300} + 300 ))
      log "waiting for one completed cycle after the deploy"
      while [ "$(date +%s)" -lt "$deadline" ]; do
        status=$(last_cycle_after "$since")
        case "$status" in
          succeeded|succeeded_with_warnings) log "cycle after deploy: $status"; return 0 ;;
          failed) log "the first cycle after the deploy FAILED"; return 1 ;;
        esac
        sleep 15
      done
      log "no completed cycle within the window"
      return 1
    fi
  fi
  return 0
}

current_images() {
  echo "${SIGNAL_BACKEND_IMAGE:-} ${SIGNAL_WEB_IMAGE:-}"
}

record() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$RELEASES"; }

cmd=${1:-}
[ -n "$cmd" ] || usage
shift
load_deploy_env
require_tools docker curl flock awk

case "$cmd" in
  validate|deploy)
    [ $# -ge 1 ] || usage
    sha=$1; shift
    valid_sha "$sha"
    class=1; wait_cycle=1; acknowledged=0
    while [ $# -gt 0 ]; do
      case "$1" in
        --class) class=${2:-}; shift 2 ;;
        --no-wait-cycle) wait_cycle=0; shift ;;
        --plan-acknowledged) acknowledged=1; shift ;;
        *) usage ;;
      esac
    done
    [[ "$class" =~ ^[123]$ ]] || die "--class must be 1, 2 or 3"
    [ "$class" != 3 ] || [ "$acknowledged" = 1 ] \
      || die "class 3 (data semantics) needs a written plan and --plan-acknowledged (HOSTING_PLAN §12.5)"

    r=$(repo)
    new_backend=$(resolve_digest "$r/signal-backend:sha-$sha")
    new_web=$(resolve_digest "$r/signal-web:sha-$sha")
    read -r old_backend old_web <<< "$(current_images)"
    preflight "$new_backend" "$new_web"
    log "plan: class $class"
    log "  backend $old_backend -> $new_backend"
    log "  web     $old_web -> $new_web"
    if [ "$cmd" = validate ]; then
      log "validate: OK. Nothing was changed (images were only pulled into the local cache)."
      exit 0
    fi

    take_lock
    stamp=$(utc_stamp)
    since=$(date -u +%Y-%m-%dT%H:%M:%S)
    if [ "$class" = 3 ]; then
      log "class 3: full off-host backup first"
      SIGNAL_LOCK="$SIGNAL_LOCK.backup" bash "$HERE/backup.sh"
    elif [ ! -s "$SIGNAL_DATA_DIR/signal_sports.db" ]; then
      log "no database yet (first deploy on an empty host): nothing to back up"
    else
      compose run --rm -T --no-deps api python scripts/backup_db.py \
        "/app/data/backups/pre-deploy_${sha:0:12}_${stamp}.db" --manifest > /dev/null \
        || die "pre-deploy backup failed; nothing was changed"
      log "pre-deploy backup: backups/pre-deploy_${sha:0:12}_${stamp}.db"
    fi
    cp -p "$ENV_FILE" "$ENV_FILE.previous"
    pin_images "$new_backend" "$new_web"
    if bring_up_and_verify "$since" "$wait_cycle"; then
      record "deployed sha=$sha class=$class backend=$new_backend web=$new_web previous_backend=$old_backend previous_web=$old_web"
      log "deployed $sha"
      exit 0
    fi
    record "FAILED sha=$sha class=$class backend=$new_backend web=$new_web"
    if [ "$class" = 3 ]; then
      die "class 3 deploy failed verification. NO automatic rollback: old code may misread new data. Restore the pre-deploy backup (deploy/restore.sh) or roll forward."
    fi
    log "verification failed: rolling back to the previous digests"
    cp -p "$ENV_FILE.previous" "$ENV_FILE"
    export SIGNAL_BACKEND_IMAGE=$old_backend SIGNAL_WEB_IMAGE=$old_web
    if bring_up_and_verify "$since" 0; then
      record "auto-rollback after failed sha=$sha to backend=$old_backend web=$old_web"
      die "deploy of $sha failed and was rolled back; the previous release is running"
    fi
    die "deploy of $sha failed AND the rollback did not verify; check 'status' and the logs now"
    ;;

  rollback)
    [ $# -eq 0 ] || usage
    line=$(grep ' deployed ' "$RELEASES" 2> /dev/null | tail -1 || true)
    [ -n "$line" ] || die "no recorded release to roll back from"
    prev_backend=$(sed -n 's/.* previous_backend=\([^ ]*\).*/\1/p' <<< "$line")
    prev_web=$(sed -n 's/.* previous_web=\([^ ]*\).*/\1/p' <<< "$line")
    [[ "$prev_backend" == *@sha256:* && "$prev_web" == *@sha256:* ]] \
      || die "the last release has no previous digests to return to"
    take_lock
    since=$(date -u +%Y-%m-%dT%H:%M:%S)
    cp -p "$ENV_FILE" "$ENV_FILE.previous"
    pin_images "$prev_backend" "$prev_web"
    bring_up_and_verify "$since" 0 || die "rollback did not verify; check 'status' and the logs"
    # Not a "deployed" line: a second rollback returns to the same release
    # instead of flipping back and forth.
    record "rolled-back to backend=$prev_backend web=$prev_web"
    log "rolled back. A class 3 release is NOT undone by this: restore its pre-deploy backup."
    ;;

  status)
    echo "images:"
    echo "  backend ${SIGNAL_BACKEND_IMAGE:-?}"
    echo "  web     ${SIGNAL_WEB_IMAGE:-?}"
    echo "worker profile: $(worker_enabled && echo on || echo off)"
    compose --profile worker ps --format 'table {{.Service}}\t{{.State}}\t{{.Health}}' 2> /dev/null || compose ps
    curl -fsS -m 10 "$(health_url)" > /dev/null && echo "health through nginx: ok" || echo "health through nginx: FAILED"
    if worker_enabled; then
      compose exec -T worker python -m app.healthcheck worker || true
    fi
    echo "last releases:"
    tail -n 5 "$RELEASES" 2> /dev/null | sed 's/^/  /' || echo "  (none)"
    ;;

  *) usage ;;
esac
