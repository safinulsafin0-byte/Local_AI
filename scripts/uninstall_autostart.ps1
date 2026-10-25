<#
.SYNOPSIS
    Uninstalls the JARVIS Backend Task Scheduler task.
#>

[CmdletBinding()]
param(
    [string]$TaskName = "JARVIS Backend"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  JARVIS Autostart Task Scheduler Uninstaller" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

try {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[SUCCESS] Task '$TaskName' removed from Task Scheduler." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Task '$TaskName' does not exist." -ForegroundColor Yellow
    }
} catch {
    Write-Error "Failed to unregister scheduled task: $_"
    exit 1
}

