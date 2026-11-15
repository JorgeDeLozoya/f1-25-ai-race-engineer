@echo off
title F1 25/26 AI Race Engineer - Radio de Pista
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m engineer --gui %*
) else (
    python -m engineer --gui %*
)
