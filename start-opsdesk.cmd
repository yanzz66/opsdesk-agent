
@echo off
setlocal

cd /d "%~dp0"

echo ======================================
echo        OpsDesk Agent Launcher
echo ======================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found.
    echo Expected: .venv\Scripts\python.exe
    pause
    exit /b 1
)

if not exist "scripts\start_opsdesk.py" (
    echo [ERROR] Startup Python script not found.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "scripts\start_opsdesk.py"

if errorlevel 1 (
    echo.
    echo [FAILED] Please check the error above.
) else (
    echo.
    echo [OK] Startup checks completed.
)

echo.
pause
endlocal