@echo off
REM One-click build (delegates to scripts\build.py for Unicode-safe EXE names)
cd /d "%~dp0.."
py -3 scripts\build.py
pause
