@echo off
setlocal
rem IMPORTANT: keep this file pure ASCII (cmd.exe parses .bat with the
rem ANSI/OEM codepage; UTF-8 Chinese text corrupts the commands).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [LiveSubtitle] venv not found. Run the following first:
  echo   python -m venv --without-pip .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)
set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m livesub.main %*
