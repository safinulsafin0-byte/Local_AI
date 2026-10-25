@echo off
:: ============================================================
:: start_jarvis.bat — One-click JARVIS launcher
:: ============================================================

chcp 65001 >nul
title JARVIS AI Launcher
color 0B

echo.
echo  ================================================
echo    JARVIS AI - Starting Up
echo  ================================================
echo.

:: ── Project root ───────────────────────────────────────────
set ROOT=%~dp0
cd /d "%ROOT%"

:: ── Activate venv ──────────────────────────────────────────
if exist "%ROOT%venv\Scripts\activate.bat" (
    call "%ROOT%venv\Scripts\activate.bat"
    echo [OK] Virtual environment activated.
) else (
    echo [WARN] venv not found. Using system Python.
)

:: ── Check Python ───────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ and rerun.
    pause
    exit /b 1
)

:: ── Start Ollama if not running ────────────────────────────
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if errorlevel 1 (
    echo [INFO] Starting Ollama...
    set OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe
    if exist "%OLLAMA_EXE%" (
        start "" /b "%OLLAMA_EXE%" serve
        timeout /t 3 /nobreak >nul
        echo [OK] Ollama started.
    ) else (
        echo [WARN] Ollama not found at %OLLAMA_EXE%.
        echo        Download from https://ollama.com
    )
) else (
    echo [OK] Ollama already running.
)

:: ── Check if model is pulled ───────────────────────────────
curl -s http://127.0.0.1:11434/api/tags | findstr /i "qwen2.5" >nul
if errorlevel 1 (
    echo [INFO] Model qwen2.5:7b not found. Pulling now...
    set OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe
    if exist "%OLLAMA_EXE%" (
        "%OLLAMA_EXE%" pull qwen2.5:7b
    ) else (
        ollama pull qwen2.5:7b
    )
)

:: ── Install missing packages ───────────────────────────────
echo [INFO] Checking Python packages...
python -c "import fastapi, uvicorn, flask, psutil, requests, watchdog, winotify" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing required packages...
    pip install -q -r requirements.txt
)

:: ── Start JARVIS server ────────────────────────────────────
echo.
echo [INFO] Starting JARVIS backend on http://127.0.0.1:8765 ...
echo.

:: Start the server in a new window, keep this window for logs
if exist "%ROOT%venv\Scripts\python.exe" (
    start "JARVIS Backend" cmd /c ""%ROOT%venv\Scripts\python.exe" server.py 2>&1"
) else (
    start "JARVIS Backend" cmd /c "python server.py 2>&1"
)

:: Wait for server to start
timeout /t 4 /nobreak >nul

:: ── Open the UI ────────────────────────────────────────────
echo [INFO] Opening JARVIS UI in browser...
start "" "http://127.0.0.1:8765/"

echo.
echo  ================================================
echo    JARVIS is running!
echo    UI:    http://127.0.0.1:8765/
echo    API:   http://127.0.0.1:8765/docs
echo    Logs:  logs\jarvis.log
echo  ================================================
echo.
echo  Press any key to close this launcher window.
pause >nul
