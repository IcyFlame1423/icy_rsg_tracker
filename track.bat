@echo off
rem Double-click to track runs and open the dashboard in your browser. It runs without a
rem window: press Stop tracking on the dashboard (or close its tab) to stop.
title Icy RSG Tracker
cd /d "%~dp0"
where python >nul 2>nul || goto :nopython
python -c "import sys; sys.exit(sys.version_info < (3, 11))" || goto :nopython
start "" pythonw -m icy_rsg_tracker app
goto :eof
:nopython
echo This needs Python 3.11 or newer: https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" when installing). Or download icy_rsg_tracker.exe
echo from the project's Releases page instead, which needs nothing else.
pause
