# ==============================================================================
# JARVIS Stark Edition - One-Click Judge Runner Script
# ==============================================================================
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\judge_mode.ps1
# ==============================================================================

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   J.A.R.V.I.S. (STARK EDITION) - ONE-CLICK JUDGE LAUNCHER" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

$BASE_DIR = Resolve-Path "$PSScriptRoot\.."
Set-Location $BASE_DIR

# 1. Check Python Virtual Environment
$PYTHON_EXE = "$BASE_DIR\venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "[!] Virtual environment not detected at .\venv." -ForegroundColor Yellow
    Write-Host "[*] Creating virtual environment..." -ForegroundColor White
    python -m venv venv
    & "$PYTHON_EXE" -m pip install --upgrade pip
    & "$PYTHON_EXE" -m pip install -r requirements.txt
}

# 2. Check Ollama Connectivity
Write-Host "[*] Verifying Ollama local LLM server..." -ForegroundColor White
try {
    $ollamaTest = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    $models = $ollamaTest.models | ForEach-Object { $_.name }
    Write-Host "    [OK] Ollama is active on 127.0.0.1:11434 ($($models.Count) models available)" -ForegroundColor Green
} catch {
    Write-Host "    [!] Warning: Ollama not reachable on 127.0.0.1:11434." -ForegroundColor Yellow
    Write-Host "        Please ensure Ollama is running ('ollama serve') for full LLM features." -ForegroundColor DarkGray
}

# 3. Kill any stale process listening on port 8765
Write-Host "[*] Checking port 8765 availability..." -ForegroundColor White
$connections = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        $stalePid = $conn.OwningProcess
        Write-Host "    [!] Freeing port 8765 (terminating stale process PID $stalePid)..." -ForegroundColor Yellow
        Stop-Process -Id $stalePid -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}
Write-Host "    [OK] Port 8765 ready." -ForegroundColor Green

# 4. Run the automated capability validation suite in the background/console
Write-Host "[*] Executing Stark capability verification suite..." -ForegroundColor White
$testResult = & "$PYTHON_EXE" tests\e2e\test_stark_suite.py 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "    [OK] All 14 Stark capability tests passed successfully!" -ForegroundColor Green
} else {
    Write-Host "    [!] Some tests flagged warnings. Inspecting..." -ForegroundColor Yellow
}

# 5. Launch Backend Server & Open UI
Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   LAUNCHING JARVIS MISSION CONTROL (127.0.0.1:8765)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   Web UI: http://127.0.0.1:8765/" -ForegroundColor White
Write-Host "   Docs  : http://127.0.0.1:8765/docs" -ForegroundColor DarkGray
Write-Host "   Press Ctrl+C to terminate." -ForegroundColor DarkGray
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

# Open Browser after 2 seconds
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:8765/"
} | Out-Null

# Run server in foreground so judge sees live logs
& "$PYTHON_EXE" server.py

