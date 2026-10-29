#!/usr/bin/env bash
# Signal Sports — rehearsal of the UNUSED Postgres db service (groundwork; see
# docs/DEPLOYMENT.md, "Postgres groundwork").
#
#   deploy/rehearse-postgres.sh <backend-image> <web-image>
#
# Two separate throwaway Compose projects, each with its own temp dir and its
# own cleanup, so neither phase can see the other's containers:
#   A  signal-pgrh-default  the normal start path (no profile): config passes
#      with no postgres.env, api and web come up, and no db container exists.
#   B  signal-pgrh-pg       db alone: a from-scratch init on an empty data dir
#      prepared as the docs say, the hardening holds, the ORM's PostgreSQL DDL
#      is accepted, and a second start on the same dir keeps the data.
# What this proves and what it does not: docs/DEPLOYMENT.md. Nothing connects
# the app to Postgres. Nothing touches /srv/signal or real data. Used by CI.
# Needs docker with the compose plugin, curl, jq, openssl and sudo.
set -euo pipefail

BACKEND_IMAGE=${1:?usage: rehearse-postgres.sh <backend-image> <web-image>}
WEB_IMAGE=${2:?usage: rehearse-postgres.sh <backend-image> <web-image>}
HERE=$(cd "$(dirname "$0")" && pwd)
PORT=18097
PROJECT_A=signal-pgrh-default
PROJECT_B=signal-pgrh-pg
# Rehearse the committed defaults (pinned image, ./postgres.env, ./pgdata).
unset SIGNAL_POSTGRES_IMAGE SIGNAL_POSTGRES_ENV_FILE SIGNAL_POSTGRES_DATA_DIR

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
has() { [[ "$1" == *"$2"* ]]; }

# compose <project> <project-dir> <args...>: relative paths in compose.yaml
# (./postgres.env, ./pgdata) resolve inside the phase's own temp dir.
compose() {
  local project=$1 dir=$2
  shift 2
  SIGNAL_BACKEND_IMAGE="$BACKEND_IMAGE" SIGNAL_WEB_IMAGE="$WEB_IMAGE" \
  SIGNAL_ENV_FILE="$dir/signal.env" SIGNAL_DATA_DIR="$dir/data" \
  SIGNAL_WEB_PORT="$PORT" COMPOSE_PROFILES="" \
    docker compose -p "$project" --project-directory "$dir" -f "$HERE/compose.yaml" "$@"
}

# Services of every container (running or not) labelled with this project.
project_services() {
  docker ps -a --filter "label=com.docker.compose.project=$1" \
    --format '{{.Label "com.docker.compose.service"}}' | sort | tr '\n' ' '
}

write_signal_env() {
  cat > "$1/signal.env" <<EOF
DEPLOY_ENV=hosted
CSRF_ALLOWED_ORIGINS=http://127.0.0.1:$PORT
AUTH_COOKIE_SECURE=false
AUTH_SIGNUP_ENABLED=false
AUTH_ADMIN_EMAIL=pg-rehearsal@rehearsal.test
AUTH_ADMIN_PASSWORD=pg-rehearsal-only
SCHEDULER_ENABLED=false
CLASSIFICATION_PROVIDER=disabled
TELEGRAM_NOTIFICATIONS_ENABLED=false
RESULTS_SYNC_ENABLED=false
RETENTION_CLEANUP_ENABLED=false
EOF
  chmod 0600 "$1/signal.env"
}

# ── Phase A: the normal start path never starts db ───────────────────────────
WORK_A=$(mktemp -d)
cleanup_a() {
  compose "$PROJECT_A" "$WORK_A" --profile worker --profile postgres logs --no-color > "$WORK_A/compose.log" 2>&1 || true
  compose "$PROJECT_A" "$WORK_A" --profile worker --profile postgres down -v --remove-orphans > /dev/null 2>&1 || true
  [ "${KEEP_REHEARSAL_LOGS:-}" = "1" ] && cp "$WORK_A/compose.log" ./pg-rehearsal-default-compose.log 2> /dev/null || true
  sudo rm -rf "$WORK_A"
}
trap cleanup_a EXIT

mkdir -p "$WORK_A/data"
sudo chown 10001:10001 "$WORK_A/data"
sudo chmod 0700 "$WORK_A/data"
write_signal_env "$WORK_A"
[ ! -e "$WORK_A/postgres.env" ] && [ ! -e "$WORK_A/pgdata" ] || fail "phase A dir is not clean"

compose "$PROJECT_A" "$WORK_A" config --quiet && pass "compose config passes with no postgres.env and no pgdata dir" || fail "compose config"
compose "$PROJECT_A" "$WORK_A" up -d --wait --wait-timeout 120 api web && pass "api and web are healthy (no profile)" || fail "api/web did not become healthy"
curl -fsS "http://127.0.0.1:$PORT/health" > /dev/null && pass "/health through web" || fail "/health"
[ -z "$(docker ps -a -q --filter "label=com.docker.compose.project=$PROJECT_A" --filter "label=com.docker.compose.service=db")" ] \
  && pass "no db container exists in $PROJECT_A" || fail "a db container was created by the default start"
services=$(project_services "$PROJECT_A")
[ "$services" = "api web " ] && pass "the default start created only api and web" || fail "containers: $services"
[ ! -e "$WORK_A/pgdata" ] && pass "the default start created no pgdata dir" || fail "pgdata dir was created"

# Static: the app's database is still SQLite, and nothing reaches db.
cfg=$(compose "$PROJECT_A" "$WORK_A" --profile worker --profile postgres config --format json)
for svc in api worker; do
  url=$(jq -r --arg s "$svc" '.services[$s].environment.DATABASE_URL' <<< "$cfg")
  [ "$url" = "sqlite:////app/data/signal_sports.db" ] || fail "$svc DATABASE_URL is $url"
done
pass "x-backend still forces DATABASE_URL to the SQLite file (api and worker)"
[ "$(jq '.services.db.ports // [] | length' <<< "$cfg")" = "0" ] && pass "db declares no published port" || fail "db has ports"
[ "$(jq '[.services[] | (.depends_on // {}) | keys[]] | index("db")' <<< "$cfg")" = "null" ] \
  && pass "no service depends on db" || fail "a service depends on db"

cleanup_a
trap - EXIT
[ -z "$(project_services "$PROJECT_A")" ] && pass "phase A torn down" || fail "phase A left containers"

# ── Phase B: db alone, initialized from scratch ──────────────────────────────
WORK_B=$(mktemp -d)
cleanup_b() {
  compose "$PROJECT_B" "$WORK_B" --profile worker --profile postgres logs --no-color > "$WORK_B/compose.log" 2>&1 || true
  compose "$PROJECT_B" "$WORK_B" --profile worker --profile postgres down -v --remove-orphans > /dev/null 2>&1 || true
  [ "${KEEP_REHEARSAL_LOGS:-}" = "1" ] && cp "$WORK_B/compose.log" ./pg-rehearsal-db-compose.log 2> /dev/null || true
  sudo rm -rf "$WORK_B"
}
trap cleanup_b EXIT

pg() { compose "$PROJECT_B" "$WORK_B" --profile postgres "$@"; }
psql_db() { pg exec -T db psql -X -q -v ON_ERROR_STOP=1 -U signal -d signal "$@"; }
pg_tables() {
  psql_db -tA -c "SELECT table_name FROM information_schema.tables
                  WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
}

# The data dir exactly as docs/DEPLOYMENT.md prepares it.
mkdir -p "$WORK_B/pgdata"
sudo chown 70:70 "$WORK_B/pgdata"
sudo chmod 0700 "$WORK_B/pgdata"
(umask 077 && printf 'POSTGRES_DB=signal\nPOSTGRES_USER=signal\nPOSTGRES_PASSWORD=%s\n' \
  "$(openssl rand -hex 24)" > "$WORK_B/postgres.env")
# Only so the shared x-backend interpolates; api and worker are never started.
write_signal_env "$WORK_B"
[ -z "$(sudo ls -A "$WORK_B/pgdata")" ] || fail "pgdata is not empty"

pg up -d --wait --wait-timeout 180 db && pass "db initialized from scratch (uid 70, read-only root) and is healthy" || fail "db did not initialize"
cid=$(pg ps -q db)
sudo test -s "$WORK_B/pgdata/18/docker/PG_VERSION" && [ "$(sudo stat -c '%u:%g' "$WORK_B/pgdata/18/docker")" = "70:70" ] \
  && pass "PGDATA is 18/docker inside the mount, owned 70:70" || fail "PGDATA layout or owner"
[ "$(docker inspect -f '{{.Config.User}} {{.HostConfig.ReadonlyRootfs}}' "$cid")" = "70:70 true" ] \
  && pass "db runs as 70:70 with a read-only root filesystem" || fail "db user/read_only"
caps=$(docker inspect -f '{{json .HostConfig.CapDrop}} {{json .HostConfig.SecurityOpt}}' "$cid")
has "$caps" '"ALL"' && has "$caps" 'no-new-privileges' && pass "db drops all capabilities, no-new-privileges" || fail "db caps: $caps"
bindings=$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$cid")
[ -z "$(docker port "$cid")" ] && { [ "$bindings" = "{}" ] || [ "$bindings" = "null" ]; } \
  && pass "db publishes no port" || fail "db publishes a port: $bindings"
locale=$(psql_db -tA -c "SELECT pg_encoding_to_char(encoding) || ' ' || datcollate || ' ' || datctype
                         FROM pg_database WHERE datname = current_database()")
[ "$locale" = "UTF8 C C" ] && pass "database is UTF8 with C collation" || fail "encoding/collation: $locale"

orm_tables=$(docker run --rm --network none --read-only "$BACKEND_IMAGE" python -c \
  "from app.db.orm_models import Base; print('\n'.join(sorted(Base.metadata.tables)))")
[ -n "$orm_tables" ] || fail "no ORM tables found in the backend image"
orm_count=$(wc -l <<< "$orm_tables")
docker run --rm --network none --read-only "$BACKEND_IMAGE" python scripts/postgres_schema_ddl.py \
  | psql_db --single-transaction -f - \
  && pass "Postgres accepted the ORM's DDL (scripts/postgres_schema_ddl.py)" || fail "DDL rejected"
[ "$(pg_tables)" = "$orm_tables" ] && pass "Postgres has exactly the $orm_count ORM tables" \
  || fail "tables differ: $(diff <(echo "$orm_tables") <(pg_tables) || true)"

# A second start on the same dir: a new container, no re-init, data kept.
pg down
pg up -d --wait --wait-timeout 120 db && pass "db is healthy again after down/up on the same data dir" || fail "db did not come back"
has "$(pg logs --no-color db)" "Skipping initialization" && pass "the second start reused the existing database" \
  || fail "the second start did not reuse the data dir"
[ "$(pg_tables)" = "$orm_tables" ] && pass "all $orm_count tables survived the second start" || fail "tables lost"

services=$(project_services "$PROJECT_B")
[ "$services" = "db " ] && pass "the only container in $PROJECT_B is db (no api, web or worker)" || fail "containers: $services"
[ -z "$(docker port "$(pg ps -q db)")" ] && pass "db still publishes no port" || fail "db publishes a port"

echo "postgres rehearsal passed"
