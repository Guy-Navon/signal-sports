# Signal Sports - hourly publishing of the public demo (#458) (Windows PowerShell 5.1).
#
#   powershell -File scripts\demo-schedule.ps1              # register (or replace) the task
#   powershell -File scripts\demo-schedule.ps1 -Status      # show the task and its last run
#   powershell -File scripts\demo-schedule.ps1 -Unregister  # remove the task
#
# Registers a scheduled task for the CURRENT user that runs scripts\demo-publish.ps1
# every hour in a hidden window. It runs only while that user is logged on, so no
# password is stored. A run that is still going when the next one is due is not
# started twice. Run it from the main checkout: the task points at this checkout's
# copy of demo-publish.ps1. Output goes to backend\data\demo-publish.log.
param([switch]$Unregister, [switch]$Status, [string]$TaskName = "SignalSportsDemoPublish")

$ErrorActionPreference = "Stop"
$publish = Join-Path $PSScriptRoot "demo-publish.ps1"

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) { "task $TaskName is not registered"; exit 0 }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    "task $TaskName : $($task.State); last run $($info.LastRunTime) (result $($info.LastTaskResult)); next run $($info.NextRunTime)"
    exit 0
}

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        "task $TaskName removed"
    } else {
        "task $TaskName is not registered"
    }
    exit 0
}

if (-not (Test-Path $publish)) { throw "publish script not found: $publish" }

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$publish`"" `
    -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
# Start a few minutes from now, then repeat every hour indefinitely.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description "Signal Sports: export guy's live feed and deploy the public demo (#458)" | Out-Null
"task $TaskName registered for ${user}: runs $publish every hour (first run in about 2 minutes)"
