@echo off
cd /d "%~dp0"
title AI Race Engineer - Parar Proceso
echo ========================================================
echo   Deteniendo AI Race Engineer en segundo plano...
echo ========================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m engineer --stop 2>nul
) else (
    python -m engineer --stop 2>nul
)

echo.
echo [OK] Todos los procesos de AI Race Engineer han sido detenidos.
echo.
timeout /t 2 >nul
