<#
.SYNOPSIS
  Run a branch (a git worktree) next to the live stack, on a COPY of the corpus.

.DESCRIPTION
  Starts the worktree's API and web app on their own ports so a proposed change can be
  tried in a browser without touching the live API, the live worker or the live corpus:

  - the corpus is copied with backend/scripts/backup_db.py (WAL-safe, verified) into
    <worktree>/backend/data/preview/preview.db, which is gitignored;
  - DEPLOY_ENV=dev: Telegram is refused, the canonical corpus file is refused, and the
    session cookie is signal_dev_session, so the live login is not overwritten;
  - no scheduler, no LLM, no results sync; email is printed to the API window;
  - the web app runs in backend data mode and proxies /api to the preview API.

  Accounts are the copy's accounts: log in as on the live app. Anything done in the
  preview (feedback, preference changes) stays in the copy.

  Python and node_modules come from the main checkout (a worktree has neither); a
  branch that changes dependencies needs its own install first.

.EXAMPLE
  powershell -File scripts\preview.ps1 -Worktree C:\path\to\worktree
  # open http://localhost:5180
.EXAMPLE
  powershell -File scripts\preview.ps1 -Worktree C:\path\to\worktree -Stop
#>
param(
    [string]$Worktree = (Split-Path -Parent $PSScriptRoot),
    [int]$ApiPort = 8010,
    [int]$WebPort = 5180,
    [switch]$KeepCopy,   # reuse an existing preview.db instead of a fresh copy
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$wt = (Resolve-Path $Worktree).Path
$previewDir = Join-Path $wt 'backend\data\preview'
$pidFile = Join-Path $previewDir 'pids.txt'

if ($Stop) {
    if (Test-Path $pidFile) {
        Get-Content $pidFile | ForEach-Object {
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$_" -ErrorAction SilentlyContinue |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $pidFile
        "preview stopped"
    } else { "no preview running for $wt" }
    exit 0
}

# The main checkout owns the venv, node_modules and the live corpus.
$commonDir = (& git -C $wt rev-parse --path-format=absolute --git-common-dir).Trim()
$main = Split-Path -Parent $commonDir
$python = Join-Path $main 'backend\.venv\Scripts\python.exe'
$liveDb = Join-Path $main 'backend\data\signal_sports.db'
foreach ($p in @($python, $liveDb, (Join-Path $main 'frontend\node_modules'))) {
    if (-not (Test-Path $p)) { throw "missing: $p" }
}
foreach ($port in @($ApiPort, $WebPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "port $port is already in use (another preview? use -Stop, or pick -ApiPort/-WebPort)"
    }
}

New-Item -ItemType Directory -Force $previewDir | Out-Null
$copy = Join-Path $previewDir 'preview.db'
if (-not ($KeepCopy -and (Test-Path $copy))) {
    Push-Location (Join-Path $wt 'backend')
    try {
        & $python scripts\backup_db.py $copy --src $liveDb
        if ($LASTEXITCODE -ne 0) { throw "corpus copy failed (backup_db.py exit $LASTEXITCODE)" }
    } finally { Pop-Location }
}

$nm = Join-Path $wt 'frontend\node_modules'
if (-not (Test-Path $nm)) {
    New-Item -ItemType Junction -Path $nm -Target (Join-Path $main 'frontend\node_modules') | Out-Null
}

# Child processes inherit these; the live stack's own windows are unaffected.
$env:DATABASE_URL = 'sqlite:///' + ($copy -replace '\\', '/')
$env:DEPLOY_ENV = 'dev'
$env:SCHEDULER_ENABLED = 'false'
$env:CLASSIFICATION_PROVIDER = 'disabled'
$env:TELEGRAM_NOTIFICATIONS_ENABLED = 'false'
$env:RESULTS_SYNC_ENABLED = 'false'
$env:MAIL_BACKEND = 'console'
$env:CSRF_ALLOWED_ORIGINS = "http://localhost:$WebPort,http://127.0.0.1:$WebPort"
$env:SIGNAL_API_PROXY = "http://127.0.0.1:$ApiPort"
$env:VITE_DATA_MODE = 'backend'

$api = Start-Process -FilePath $python -WorkingDirectory (Join-Path $wt 'backend') -PassThru `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$ApiPort"
$web = Start-Process -FilePath 'cmd.exe' -WorkingDirectory (Join-Path $wt 'frontend') -PassThru `
    -ArgumentList '/c', 'npx', 'vite', '--port', "$WebPort", '--strictPort'
Set-Content $pidFile @($api.Id, $web.Id)

$branch = (& git -C $wt rev-parse --abbrev-ref HEAD).Trim()
$sha = (& git -C $wt rev-parse --short HEAD).Trim()
"preview of $branch @ $sha"
"  web: http://localhost:$WebPort   api: http://127.0.0.1:$ApiPort/health"
"  corpus copy: $copy"
"  stop: powershell -File scripts\preview.ps1 -Worktree `"$wt`" -Stop"
