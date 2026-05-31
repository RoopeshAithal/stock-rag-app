<#
.SYNOPSIS
    Register the Hybrid Stock-RAG daily pipeline as a Windows Scheduled Task.

.DESCRIPTION
    Creates a task named "StockRAG-Daily" that runs scripts\run_daily.bat at
    the chosen time on weekdays (Mon-Fri) — markets are closed on weekends,
    so a daily-weekday cadence is enough.

    Re-running this script updates the task in place.

.PARAMETER At
    Time of day, "HH:mm" 24h format. Default 18:30 (after US market close).

.PARAMETER TaskName
    Scheduled Task name. Default "StockRAG-Daily".

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1 -At "21:00"
#>

param(
    [string]$At = "18:30",
    [string]$TaskName = "StockRAG-Daily"
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot
$batPath = Join-Path $projectDir "scripts\run_daily.bat"

if (-not (Test-Path $batPath)) {
    Write-Error "Cannot find $batPath"
    exit 1
}

Write-Host "Project dir : $projectDir"
Write-Host "Batch file  : $batPath"
Write-Host "Run at      : $At  (Mon-Fri)"
Write-Host "Task name   : $TaskName"

$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Run as the interactive user, only when logged on (no stored password needed).
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Updating existing task..."
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
} else {
    Write-Host "Registering new task..."
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Hybrid Stock-RAG: daily price fetch, embeddings rebuild, and prediction batch." | Out-Null
}

Write-Host ""
Write-Host "Done. Manage with:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'   # run now"
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false  # remove"
