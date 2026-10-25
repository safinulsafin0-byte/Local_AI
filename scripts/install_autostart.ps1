<#
.SYNOPSIS
    Installs JARVIS Backend as a Windows Task Scheduler task running at logon.
.DESCRIPTION
    Creates a Task Scheduler entry "JARVIS Backend" that executes at user logon
    in a hidden window, with working directory D:\personal-ai-full and the project venv python.
#>

[CmdletBinding()]
param(
    [string]$TaskName = "JARVIS Backend",
    [string]$WorkingDirectory = "D:\personal-ai-full",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  JARVIS Autostart Task Scheduler Installer" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$PythonExe = Join-Path $WorkingDirectory "venv\Scripts\python.exe"
$ServerPy = Join-Path $WorkingDirectory "server.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python executable not found at: $PythonExe"
    exit 1
}

if (-not (Test-Path $ServerPy)) {
    Write-Error "server.py not found at: $ServerPy"
    exit 1
}

# Ask before installing if -Force not supplied
if (-not $Force) {
    $title = "Install JARVIS Autostart Task"
    $message = "Do you want to create a Task Scheduler entry '$TaskName' to start JARVIS automatically on user logon?"
    $yes = New-Object System.Management.Automation.Host.ChoiceDescription "&Yes", "Install task"
    $no = New-Object System.Management.Automation.Host.ChoiceDescription "&No", "Do not install"
    $options = [System.Management.Automation.Host.ChoiceDescription[]]($yes, $no)
    $result = $host.ui.PromptForChoice($title, $message, $options, 1)

    if ($result -ne 0) {
        Write-Host "Installation cancelled by user." -ForegroundColor Yellow
        exit 0
    }
}

try {
    # Check if task already exists
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Host "Existing task '$TaskName' found. Replacing..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    $Action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "server.py" `
        -WorkingDirectory $WorkingDirectory

    $Trigger = New-ScheduledTaskTrigger -AtLogOn

    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)

    $Principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal | Out-Null

    Write-Host "[SUCCESS] Task '$TaskName' successfully registered!" -ForegroundColor Green
    Write-Host "  Trigger: At User Logon"
    Write-Host "  Executable: $PythonExe"
    Write-Host "  Directory: $WorkingDirectory"
} catch {
    Write-Error "Failed to register scheduled task: $_"
    exit 1
}

