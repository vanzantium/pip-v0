@echo off
cd /d "%~dp0"
echo Starting Ollama server in the background...
start /b ollama serve >nul 2>&1
timeout /t 5 >nul

echo Starting Pip (logging to pip_startup.log)...
python pip_fairy_window.py > pip_startup.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo Pip failed to start. Check pip_startup.log for details.
    type pip_startup.log
    pause
)
