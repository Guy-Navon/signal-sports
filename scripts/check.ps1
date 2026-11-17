<#
.SYNOPSIS
  Runs the CI checks (.github/workflows/checks.yml) locally: backend tests and
  every frontend step, including the public-demo build and bundle guard. The
  requirements.lock drift check (uv pip compile) runs in CI only.
.PARAMETER Backend
  Run only the backend tests.
.PARAMETER Frontend
  Run only the frontend checks.
#>
param([switch]$Backend, [switch]$Frontend)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
# Vitest loads itself twice ("failed to find the runner") when the working
# directory's drive letter is lowercase (c:\ from VS Code terminals).
if ($root -cmatch '^[a-z]:') { $root = $root.Substring(0, 1).ToUpper() + $root.Substring(1) }
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
    Invoke-Step 'demo build' 'frontend' { npm run build:demo }
    Invoke-Step 'demo bundle guard' 'frontend' { npm run check:demo-bundle }
}
Write-Host 'All checks passed.' -ForegroundColor Green
