@echo off
rem Builds dist\icy_rsg_tracker.exe (needs Python 3.11+). PyInstaller goes into its own
rem folder (.build-venv), so your normal Python install isn't touched.
cd /d "%~dp0"
if not exist .build-venv (
  python -m venv .build-venv || goto :error
  .build-venv\Scripts\python -m pip install --quiet pyinstaller || goto :error
)
.build-venv\Scripts\pyinstaller --noconfirm --clean --onefile --noconsole --name "icy_rsg_tracker" ^
  --add-data "icy_rsg_tracker\app\static;icy_rsg_tracker\app\static" launcher.py || goto :error
echo.
echo Built: dist\icy_rsg_tracker.exe
goto :eof
:error
echo Build failed.
exit /b 1
