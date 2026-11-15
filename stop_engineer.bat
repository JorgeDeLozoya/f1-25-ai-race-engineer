@echo off
title AI Race Engineer - Parar Proceso
echo ========================================================
echo   Deteniendo AI Race Engineer en segundo plano...
echo ========================================================

:: 1. Detener el daemon de Swofty Launcher
taskkill /F /IM engineer-helper.exe /T 2>nul

:: 2. Detener procesos de python/pythonw que esten ejecutando el ingeniero
powershell -Command "Get-Process | Where-Object { $_.ProcessName -match 'engineer-helper' } | Stop-Process -Force -ErrorAction SilentlyContinue" 2>nul
powershell -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*engineer*' -and ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul

echo.
echo [OK] Todos los procesos de AI Race Engineer han sido detenidos.
echo.
timeout /t 3 >nul
