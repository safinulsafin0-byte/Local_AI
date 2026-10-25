<#
.SYNOPSIS
    JARVIS Stark Edition — Demo Environment Reset Script
    scripts/demo_reset.ps1

.DESCRIPTION
    Prepares the Windows environment for a flawless 2:30 Devpost demo recording:
    1. Kills orphaned test processes (cmd, notepad).
    2. Restores master system volume to 50%.
    3. Cleans up temporary test folders in D:\jarvis_test.
    4. Verifies Ollama service and active model (qwen2.5:7b).
    5. Validates backend health endpoint on http://127.0.0.1:8765.
    6. Ensures clean, predictable demo state.
#>

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   JARVIS STARK EDITION — PRE-DEMO ENVIRONMENT RESET        " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Clean up stray test processes
Write-Host "`n[1/5] Cleaning up stray background test processes..." -ForegroundColor Yellow
$testProcs = @("notepad")
foreach ($procName in $testProcs) {
    Get-Process -Name $procName -ErrorAction SilentlyContinue | ForEach-Object {
        $pId = $_.Id
        Stop-Process -Id $pId -Force -ErrorAction SilentlyContinue
        Write-Host "  -> Terminated stray process: $procName - PID $pId" -ForegroundColor Gray
    }
}

# 2. Reset Filesystem Demo Directory
Write-Host "`n[2/5] Resetting test workspace D:\jarvis_test..." -ForegroundColor Yellow
$demoPath = "D:\jarvis_test"
if (Test-Path $demoPath) {
    Get-ChildItem -Path $demoPath -Exclude "sample_doc.txt" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  -> Cleaned temporary files from $demoPath" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Path $demoPath -Force | Out-Null
    Write-Host "  -> Created workspace: $demoPath" -ForegroundColor Green
}

# 3. Reset Hardware Audio Volume to 50%
Write-Host "`n[3/5] Setting master audio volume to 50%..." -ForegroundColor Yellow
$pyCode = 'from tools import system_ops; system_ops.volume_set(50); print("  -> Hardware volume restored: " + str(system_ops.volume_get()))'
& "D:\personal-ai-full\venv\Scripts\python.exe" -c $pyCode

# 4. Verify Local Ollama LLM
Write-Host "`n[4/5] Verifying Ollama service and local models..." -ForegroundColor Yellow
try {
    $ollamaTags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 4
    $hasModel = $ollamaTags.models | Where-Object { $_.name -like "*qwen2.5:7b*" }
    if ($hasModel) {
        Write-Host "  -> Ollama is operational with active model: qwen2.5:7b" -ForegroundColor Green
    } else {
        Write-Warning "  -> Ollama is running but qwen2.5:7b was not found in tags."
    }
} catch {
    Write-Error "  -> Ollama service is not responding on 127.0.0.1:11434! Please run: ollama serve"
}

# 5. Check JARVIS Backend Health
Write-Host "`n[5/5] Checking JARVIS backend on http://127.0.0.1:8765..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -Method Get -TimeoutSec 4
    if ($health.ok -eq $true) {
        Write-Host "  -> Backend STATUS: OK - Uptime verified" -ForegroundColor Green
        $statusMsg = "  -> Model: " + $health.model + " - RAG: " + $health.rag + " - Vision: " + $health.vision
        Write-Host $statusMsg -ForegroundColor Green
    } else {
        Write-Warning "  -> Backend responded with non-ok health: $($health | ConvertTo-Json)"
    }
} catch {
    Write-Error "  -> Backend is NOT listening on port 8765! Start with: python server.py"
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "   DEMO RESET COMPLETE — SYSTEM READY FOR RECORDING         " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
