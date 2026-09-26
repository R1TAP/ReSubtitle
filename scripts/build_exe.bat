@echo off
rem One-click build for LiveSubtitle.exe (single file, no console window).
rem IMPORTANT: keep this file pure ASCII (cmd.exe parses .bat with ANSI/OEM codepage).
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo [ReSubtitle] venv not found. Run the following first:
  echo   python -m venv .venv
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
".venv\Scripts\pyinstaller" --noconfirm --clean --onefile --windowed --name ReSubtitle --icon src\assets\icon.ico --paths src --collect-all sherpa_onnx --collect-all sherpa_onnx_core --collect-all soundcard --add-data "src\assets;assets" scripts\build_entry.py
if errorlevel 1 goto :fail

echo [3/3] Copying models and assets to dist ...
if not exist "dist\models" xcopy /E /I /Y models dist\models >nul
if exist "src\assets\icon.png" copy /Y src\assets\icon.png dist\ >nul
if exist "src\assets\icon.ico" copy /Y src\assets\icon.ico dist\ >nul

echo.
echo Done: dist\ReSubtitle.exe
echo Usage: double-click it; model loaded from dist\models.
exit /b 0

:fail
echo Build failed.
exit /b 1
