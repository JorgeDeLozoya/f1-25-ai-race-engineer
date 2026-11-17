@echo off
cd /d "%~dp0"

:: Solicitar cierre limpio de cualquier instancia previa
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m engineer --stop 2>nul
) else (
    python -m engineer --stop 2>nul
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m engineer --gui %*
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" -m engineer --gui %*
) else (
    start "" pythonw -m engineer --gui %*
)
