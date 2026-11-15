@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m engineer --gui %*
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" -m engineer --gui %*
) else (
    start "" pythonw -m engineer --gui %*
)
