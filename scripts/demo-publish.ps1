# Signal Sports - publish the public read-only demo (#458) (Windows PowerShell 5.1).
#
#   powershell -File scripts\demo-publish.ps1              # export + deploy
#   powershell -File scripts\demo-publish.ps1 -Build       # rebuild the demo bundle first
#   powershell -File scripts\demo-publish.ps1 -NoDeploy    # export only (check the files)
#   powershell -File scripts\demo-publish.ps1 -Db <path>   # read another SQLite file
#
# Run from the main checkout (the one the live worker uses). Steps:
#   1. build frontend\dist-demo when it is missing or -Build is given;
#   2. export the live feed of profile "guy" into frontend\dist-demo\demo-data
#      (backend\scripts\export_demo_snapshot.py; reads the DB read-only);
#   3. deploy to Firebase Hosting (project signal-sports-demo) only if the export
#      succeeded. An empty feed (exit 3: the worker stopped and nothing is left in
#      the freshness window) is not deployed either, so the site keeps its last real
#      snapshot, whose banner shows how old it is.
# Everything is logged to backend\data\demo-publish.log (gitignored).
# Exit codes: 0 published (or exported with -NoDeploy); 1 failed; 3 empty feed, skipped.
# scripts\demo-schedule.ps1 registers this script as an hourly scheduled task.
param(
    [switch]$Build,
    [switch]$NoDeploy,
    [string]$Db = "",
    [string]$Project = "signal-sports-demo"
)

$ErrorActionPreference = "Stop"
$root     = Split-Path -Parent $PSScriptRoot
$backend  = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python   = Join-Path $backend ".venv\Scripts\python.exe"
$exporter = Join-Path $backend "scripts\export_demo_snapshot.py"
$dist     = Join-Path $frontend "dist-demo"
$dataDir  = Join-Path $dist "demo-data"
$logDir   = Join-Path $backend "data"
$log      = Join-Path $logDir "demo-publish.log"

function Write-Log([string]$message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Add-Content -Path $log -Value $line -Encoding utf8
    # Write-Host, not Write-Output: Invoke-Logged returns an exit code, and
    # pipeline output inside it would be returned along with that code.
    Write-Host $line
}

# Any unexpected terminating error (Start-Process failing, a locked file, ...)
# still leaves a log line before the non-zero exit. If the log itself cannot be
# written, the message goes to the console so the task history has it.
trap {
    $failure = "FAILED: unexpected error: $($_.Exception.Message) (line $($_.InvocationInfo.ScriptLineNumber))"
    try { Write-Log $failure } catch { Write-Host $failure }
    exit 1
}

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
# Keep one previous log once this one passes 1 MB.
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 1MB)) {
    Move-Item $log "$log.1" -Force
}

# Run a native command, append its stdout/stderr to the log, return its exit code.
# Start-Process with redirection, because in PowerShell 5.1 "2>&1" on a native
# command turns stderr lines into errors and stops the script.
function Invoke-Logged([string]$file, [string[]]$arguments, [string]$workDir) {
    $out = [System.IO.Path]::GetTempFileName()
    $err = [System.IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $workDir `
            -NoNewWindow -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
        foreach ($f in @($out, $err)) {
            Get-Content $f -Encoding utf8 | Where-Object { $_ -ne "" } | ForEach-Object { Write-Log "  $_" }
        }
        return $p.ExitCode
    } finally {
        Remove-Item $out, $err -Force -ErrorAction SilentlyContinue
    }
}

function Resolve-Cmd([string]$name) {
    $cmd = Get-Command "$name.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { $cmd = Get-Command $name -ErrorAction SilentlyContinue }
    if ($null -eq $cmd) { return $null }
    return $cmd.Source
}

function Quote([string]$value) { return '"' + $value + '"' }

# The exporter prints paths and messages; keep its redirected output UTF-8.
$env:PYTHONIOENCODING = "utf-8"

Write-Log "demo publish started (build=$Build, deploy=$(-not $NoDeploy))"
if (-not (Test-Path $python)) { Write-Log "FAILED: backend venv not found: $python"; exit 1 }

# 1. Build the demo bundle.
if ($Build -or -not (Test-Path (Join-Path $dist "demo.html"))) {
    $npm = Resolve-Cmd "npm"
    if ($null -eq $npm) { Write-Log "FAILED: npm not found on PATH"; exit 1 }
    Write-Log "building the demo bundle"
    $code = Invoke-Logged $npm @("run", "build:demo") $frontend
    if ($code -ne 0) { Write-Log "FAILED: demo build exited $code; nothing deployed"; exit 1 }
}

# 2. Export the snapshot. Nothing is written on failure, and nothing is deployed.
$exportArgs = @((Quote $exporter), "--out", (Quote $dataDir))
if ($Db -ne "") { $exportArgs += @("--db", (Quote $Db)) }
$code = Invoke-Logged $python $exportArgs $backend
if ($code -eq 3) { Write-Log "SKIPPED: the feed is empty; the published demo keeps its last snapshot"; exit 3 }
if ($code -ne 0) { Write-Log "FAILED: export exited $code; nothing deployed"; exit 1 }

if ($NoDeploy) { Write-Log "export done; deploy skipped (-NoDeploy)"; exit 0 }

# 3. Deploy the static site.
$firebase = Resolve-Cmd "firebase"
if ($null -eq $firebase) { Write-Log "FAILED: firebase CLI not found on PATH"; exit 1 }
$code = Invoke-Logged $firebase @("deploy", "--only", "hosting", "--project", $Project, "--non-interactive") $root
if ($code -ne 0) { Write-Log "FAILED: firebase deploy exited $code"; exit 1 }
Write-Log "published to https://$Project.web.app"
exit 0
