# Signal Sports - start / stop / check the scheduler worker (Windows PowerShell 5.1).
#
#   powershell -File scripts\worker.ps1            # start (Ollama too, if it is down)
#   powershell -File scripts\worker.ps1 -Status    # is it running? last log lines
#   powershell -File scripts\worker.ps1 -Stop      # stop the worker (Ollama is left running)
#
# The worker is the ONLY automatic ingestion (the API process runs no scheduler); it
# runs only while this machine is on, and nothing restarts it after a reboot - that is
# how ingestion silently stopped for two weeks in September 2026. Run -Status first.
# It reads backend/.env: SCHEDULER_ENABLED and TELEGRAM_NOTIFICATIONS_ENABLED there
# decide what a started worker actually does.
param([switch]$Stop, [switch]$Status)

$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
$python  = Join-Path $backend ".venv\Scripts\python.exe"
$log     = Join-Path $backend "data\worker.log.err"

function Get-Worker {
    @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.worker' })
}

if ($Status) {
    $w = Get-Worker
    if ($w.Count -gt 0) { "worker RUNNING (pids: $(($w | ForEach-Object ProcessId) -join ', '))" } else { "worker NOT running" }
    if (Test-Path $log) { Get-Content $log -Tail 3 }
    exit 0
}

if ($Stop) {
    $w = Get-Worker
    $w | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
    "stopped $($w.Count) worker process(es)"
    exit 0
}

if ((Get-Worker).Count -gt 0) { "worker already running - use -Status, or -Stop first"; exit 0 }
if (-not (Test-Path $python)) { throw "backend venv not found: $python" }

# Ollama: the LLM classifier. Without it the worker still ingests (rules fallback).
try {
    Invoke-RestMethod -Uri http://localhost:11434/api/tags -TimeoutSec 3 | Out-Null
    "ollama already up"
} catch {
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $ollama) {
        Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 4
        "ollama started"
    } else {
        "ollama not installed - the worker will use the rules fallback"
    }
}

# Keep the previous log instead of overwriting it.
if (Test-Path $log) {
    Move-Item $log ("$log." + (Get-Date -Format "yyyyMMdd-HHmmss")) -Force
}

$p = Start-Process -FilePath $python -ArgumentList "-m", "app.worker" -WorkingDirectory $backend `
    -WindowStyle Hidden -RedirectStandardOutput (Join-Path $backend "data\worker.log") `
    -RedirectStandardError $log -PassThru
Start-Sleep -Seconds 6
"worker started (pid $($p.Id)); log: $log"
Get-Content $log -Tail 3
