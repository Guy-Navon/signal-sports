#!/usr/bin/env bash
# Signal Sports — one-time setup of a new codespace or devcontainer.
# Runs as postCreateCommand (again after every rebuild); safe to re-run by hand.
#
# Installs the exact locked dependencies, creates an EMPTY dev database
# directory and a dev-only backend/.env. It starts nothing: no API, no worker,
# no Telegram, no LLM call. It never downloads a production backup and never
# writes a production credential.
#
#   SIGNAL_SKIP_CLAUDE_CODE=1   skip installing the Claude Code CLI (CI uses this)
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)

echo "== Python (must match CI: 3.13)"
PY=$(command -v python3.13 || command -v python3)
"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version' \
  || { echo "Python 3.13 is required (found $("$PY" --version))" >&2; exit 1; }

echo "== Backend dependencies (hash-locked)"
cd "$ROOT/backend"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --disable-pip-version-check --require-hashes -r requirements.lock
mkdir -p data/dev data/snapshots
chmod 0700 data data/dev data/snapshots

echo "== Dev-only backend/.env"
if [ ! -e .env ]; then
  umask 077
  password=$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(18))')
  cat > .env <<EOF
# DEV ONLY — written by .devcontainer/post-create.sh. Untracked (.gitignore).
# Never copy production values here: DEPLOY_ENV=dev refuses Telegram secrets
# and any production database path.
AUTH_ADMIN_EMAIL=dev-admin@example.invalid
AUTH_ADMIN_PASSWORD=${password}
EOF
  echo "   created; the dev admin login is in backend/.env"
else
  echo "   exists; left unchanged"
fi

echo "== Frontend dependencies (npm ci, from package-lock.json)"
cd "$ROOT/frontend"
npm ci --no-audit --no-fund --loglevel=error

if [ "${SIGNAL_SKIP_CLAUDE_CODE:-}" != "1" ]; then
  echo "== Claude Code CLI"
  # Its config (login, settings, memory) lives in CLAUDE_CONFIG_DIR under
  # /workspaces, which survives a rebuild (see .devcontainer/README.md).
  mkdir -p "${CLAUDE_CONFIG_DIR:-/workspaces/.persist/claude}"
  chmod 0700 "${CLAUDE_CONFIG_DIR:-/workspaces/.persist/claude}"
  npm install -g --no-audit --no-fund --loglevel=error @anthropic-ai/claude-code \
    || echo "   Claude Code install failed; the rest of the environment is ready" >&2
fi

echo
echo "Ready. Nothing is running. Start what you need:"
echo "  scripts/dev.sh api     # API on 127.0.0.1:8000, empty dev DB"
echo "  scripts/dev.sh web     # Vite on 127.0.0.1:5173 (open the forwarded port)"
echo "  scripts/dev.sh test    # backend suite;  scripts/dev.sh check = everything CI runs"
