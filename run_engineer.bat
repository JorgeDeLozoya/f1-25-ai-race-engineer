@echo off
cd /d "%~dp0"

:: Cerrar cualquier proceso residual en segundo plano antes de arrancar
taskkill /F /IM engineer-helper.exe /T 2>nul
powershell -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*engineer*' -and ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m engineer --gui %*
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" -m engineer --gui %*
) else (
    start "" pythonw -m engineer --gui %*
)
