@echo off
REM Runs the build-log watcher in a minimised window. Close it to stop.
cd /d "%~dp0"
start "build-log watcher" /min cmd /k python watcher.py
