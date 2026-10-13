# Signal Sports — shared helpers for the host scripts in deploy/. Sourced, not run.
#
# Layout these scripts assume on a host (docs/DEPLOYMENT.md):
#   SIGNAL_DEPLOY_DIR   this directory: compose.yaml, .env (interpolation), scripts
#   SIGNAL_DATA_DIR     the corpus bind mount (from deploy/.env), owned 10001:10001
# Every value comes from deploy/.env or the script's own config file; nothing
# personal or secret is hard-coded here.

SIGNAL_DEPLOY_DIR=${SIGNAL_DEPLOY_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
SIGNAL_SERVICE_UID=10001
SIGNAL_LOCK=${SIGNAL_LOCK:-/run/lock/signal-ops.lock}

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# Read deploy/.env (simple KEY=VALUE lines) without executing it.
load_deploy_env() {
  local file="$SIGNAL_DEPLOY_DIR/.env" line key value
  [ -r "$file" ] || die "missing $file (copy deploy/.env.example)"
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    key=${line%%=*}
    value=${line#*=}
    [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || die "bad line in $file: $key"
    # The environment wins, as it does for docker compose itself.
    [ -n "${!key+x}" ] || export "$key=$value"
  done < "$file"
  [ -n "${SIGNAL_DATA_DIR:-}" ] || die "SIGNAL_DATA_DIR is not set in $file"
  # Compose resolves a relative path against the project directory; do the same.
  case "$SIGNAL_DATA_DIR" in
    /*) ;;
    *) SIGNAL_DATA_DIR="$SIGNAL_DEPLOY_DIR/${SIGNAL_DATA_DIR#./}" ;;
  esac
  export SIGNAL_DATA_DIR
  SIGNAL_ENV_FILE=${SIGNAL_ENV_FILE:-./signal.env}
  case "$SIGNAL_ENV_FILE" in
    /*) ;;
    *) SIGNAL_ENV_FILE="$SIGNAL_DEPLOY_DIR/${SIGNAL_ENV_FILE#./}" ;;
  esac
  export SIGNAL_ENV_FILE
}

# Read a root-only config file (backup.env etc.): KEY=VALUE, no shell code.
load_config() {
  local file=$1 line key value
  [ -r "$file" ] || die "missing config $file"
  if [ "$(stat -c %a "$file")" != "600" ]; then die "$file must be mode 0600"; fi
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    key=${line%%=*}
    value=${line#*=}
    [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || die "bad line in $file: $key"
    [ -n "${!key+x}" ] || export "$key=$value"
  done < "$file"
}

compose() {
  docker compose --project-directory "$SIGNAL_DEPLOY_DIR" -f "$SIGNAL_DEPLOY_DIR/compose.yaml" "$@"
}

require_tools() {
  local tool
  for tool in "$@"; do command -v "$tool" > /dev/null || die "required tool not found: $tool"; done
}

# One host-ops script at a time (backup, dev snapshot, restore, deploy).
take_lock() {
  mkdir -p "$(dirname "$SIGNAL_LOCK")"
  exec 9> "$SIGNAL_LOCK"
  flock -n 9 || die "another Signal ops script holds $SIGNAL_LOCK"
}

# POST to a monitoring URL. Never prints the URL (it is a credential) and never
# fails the caller. Usage: ping_url <url> [fail]
ping_url() {
  local url=${1:-} suffix=""
  [ -n "$url" ] || return 0
  [ "${2:-}" = "fail" ] && suffix="/fail"
  curl -fsS -m 10 --retry 2 -o /dev/null -X POST "${url%/}${suffix}" 2> /dev/null \
    || log "warning: monitor ping${suffix:+ (fail)} did not go through"
}

utc_stamp() { date -u +%Y%m%dT%H%M%SZ; }
