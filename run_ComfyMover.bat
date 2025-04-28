@echo off
REM ===== ComfyMover Launcher =====
REM Version: 1.0
REM Contact: WeChat wangdefa4567

echo Starting ComfyMover 1.0...

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not detected.
    echo Please install Python 3.8 or higher.
    echo Visit https://www.python.org/downloads/ to download.
    pause
    exit /b 1
)

REM Set current directory to script location
cd /d "%~dp0"

REM Launch the startup script
python main.py

pause