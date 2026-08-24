@echo off
rem One-click build for LiveSubtitle.exe (single file, no console window).
rem IMPORTANT: keep this file pure ASCII (cmd.exe parses .bat with ANSI/OEM codepage).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [LiveSubtitle] venv not found. Run the following first:
  echo   python -m venv --without-pip .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)
if not exist "tmpbuild" mkdir tmpbuild
set "TMP=%CD%\tmpbuild"
set "TEMP=%TMP%"

echo [1/3] Installing PyInstaller ...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :fail

echo [2/3] Building exe ...
".venv\Scripts\pyinstaller" --noconfirm --clean --onefile --windowed --name LiveSubtitle --paths src --collect-all sherpa_onnx --collect-all sherpa_onnx_core --collect-all soundcard build_entry.py
if errorlevel 1 goto :fail

echo [3/3] Copying models next to exe ...
if not exist "dist\models" xcopy /E /I /Y models dist\models >nul

echo.
echo Done: dist\LiveSubtitle.exe
echo Usage: double-click it; model loaded from dist\models.
exit /b 0

:fail
echo Build failed.
exit /b 1
