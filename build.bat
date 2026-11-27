@echo off
rem Builds dist\icy_rsg_tracker\ (the app: icy_rsg_tracker.exe and its _internal folder) and
rem dist\icy_rsg_tracker.zip (that folder's contents, for a release). Needs Python 3.11+.
rem PyInstaller goes into its own folder (.build-venv), so your normal Python install isn't touched.
rem A folder build (not one self-extracting .exe) with version details is far less often
rem mistaken for malware by antivirus.
cd /d "%~dp0"
if not exist .build-venv (
  python -m venv .build-venv || goto :error
  .build-venv\Scripts\python -m pip install --quiet pyinstaller || goto :error
)
.build-venv\Scripts\python make_version_info.py || goto :error
.build-venv\Scripts\pyinstaller --noconfirm --clean --onedir --noconsole --name "icy_rsg_tracker" ^
  --version-file build\version_info.txt ^
  --add-data "icy_rsg_tracker\app\static;icy_rsg_tracker\app\static" launcher.py || goto :error
powershell -NoProfile -Command "Compress-Archive -Path 'dist\icy_rsg_tracker\*' -DestinationPath 'dist\icy_rsg_tracker.zip' -Force" || goto :error
echo.
echo Built: dist\icy_rsg_tracker\icy_rsg_tracker.exe and dist\icy_rsg_tracker.zip
goto :eof
:error
echo Build failed.
exit /b 1
