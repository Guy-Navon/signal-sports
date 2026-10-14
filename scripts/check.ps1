<#
.SYNOPSIS
  Runs the same checks as CI (.github/workflows/checks.yml) locally.
.PARAMETER Backend
  Run only the backend tests.
.PARAMETER Frontend
  Run only the frontend checks.
#>
param([switch]$Backend, [switch]$Frontend)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runAll = -not ($Backend -or $Frontend)

function Invoke-Step($name, $dir, $block) {
    Write-Host "==> $name" -ForegroundColor Cyan
    Push-Location (Join-Path $root $dir)
    try {
        & $block
        if ($LASTEXITCODE -ne 0) { throw "$name failed (exit $LASTEXITCODE)" }
    } finally { Pop-Location }
}

if ($runAll -or $Backend) {
    Invoke-Step 'backend tests' 'backend' { & .venv\Scripts\python -m pytest tests -q }
}
if ($runAll -or $Frontend) {
    Invoke-Step 'frontend lint' 'frontend' { npm run lint }
    Invoke-Step 'frontend typecheck' 'frontend' { npm run typecheck }
    Invoke-Step 'frontend tests' 'frontend' { npm run test }
    Invoke-Step 'frontend build' 'frontend' { npm run build }
}
Write-Host 'All checks passed.' -ForegroundColor Green
