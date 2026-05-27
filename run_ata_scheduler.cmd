@echo off
REM Run ATA scheduler.main by double-clicking this file.
REM Usage:
REM   1. Double click run_ata_scheduler.cmd, or
REM   2. From terminal: run_ata_scheduler.cmd
REM Stop scheduler with Ctrl+C, then answer Y if Windows asks to terminate batch job.

setlocal
REM Avoid inherited Python runtime variables from Git Bash/Hermes/etc. They can
REM break the project virtualenv with errors like "SRE module mismatch".
set "PYTHONHOME="
set "PYTHONPATH="
set "UV_INTERNAL__PYTHONHOME="

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if exist "%PROJECT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"
) else if exist "%PROJECT_DIR%venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Using Python: %PYTHON_EXE%
echo Project: %PROJECT_DIR%
echo Starting ATA scheduler.main ...
echo.

"%PYTHON_EXE%" "%PROJECT_DIR%scripts\run_scheduler_main.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ATA scheduler exited with error code %EXIT_CODE%.
    echo Press any key to close this window.
    pause >nul
)

exit /b %EXIT_CODE%
