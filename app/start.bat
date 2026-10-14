@echo off
rem Startet den lokalen Server. Optional eigenes Python per Umgebungsvariable PYTHON setzen.
cd /d "%~dp0"
if defined PYTHON (set "PY=%PYTHON%") else (set "PY=python")
"%PY%" serve.py 8080
pause
