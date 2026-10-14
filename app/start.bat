@echo off
rem Startet den lokalen Server und oeffnet den Browser.
rem Python-Auswahl (erstes, das wirklich laeuft): 1) Umgebungsvariable PYTHON  2) conda-Env claude-code-env, falls vorhanden
rem 3) python aus dem PATH  4) py-Launcher. Der Microsoft-Store-Platzhalter "python" wird so automatisch uebersprungen.
cd /d "%~dp0"
set "PY="
if defined PYTHON call :try "%PYTHON%"
if not defined PY if exist "%USERPROFILE%\.conda\envs\claude-code-env\python.exe" call :try "%USERPROFILE%\.conda\envs\claude-code-env\python.exe"
if not defined PY call :try python
if not defined PY call :try py
if not defined PY (
  echo Kein funktionierendes Python gefunden.
  echo Bitte Python 3 installieren oder die Variable PYTHON auf eine python.exe setzen.
  pause
  exit /b 1
)
echo Verwende: %PY%
"%PY%" serve.py 8080
pause
exit /b

:try
"%~1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)" >nul 2>nul && set "PY=%~1"
exit /b
