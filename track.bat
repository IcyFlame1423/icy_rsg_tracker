@echo off
rem Double-click to track runs and open the dashboard in your browser.
rem Close this window (or press Ctrl+C) to stop.
title MCSR Tracker
cd /d "%~dp0"
where python >nul 2>nul || goto :nopython
python -c "import sys; sys.exit(sys.version_info < (3, 11))" || goto :nopython
python -m mcsr_tracker app
pause
goto :eof
:nopython
echo This needs Python 3.11 or newer: https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" when installing). Or download MCSR Tracker.exe
echo from the project's Releases page instead, which needs nothing else.
pause
