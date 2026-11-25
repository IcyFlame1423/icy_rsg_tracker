@echo off
rem Builds dist\MCSR-Tracker.exe (needs Python 3.11+). PyInstaller goes into its own
rem folder (.build-venv), so your normal Python install isn't touched.
cd /d "%~dp0"
if not exist .build-venv (
  python -m venv .build-venv || goto :error
  .build-venv\Scripts\python -m pip install --quiet pyinstaller || goto :error
)
.build-venv\Scripts\pyinstaller --noconfirm --clean --onefile --name "MCSR-Tracker" ^
  --add-data "mcsr_tracker\app\static;mcsr_tracker\app\static" launcher.py || goto :error
echo.
echo Built: dist\MCSR-Tracker.exe
goto :eof
:error
echo Build failed.
exit /b 1
