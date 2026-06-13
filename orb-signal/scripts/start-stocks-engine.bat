@echo off
REM Stock ORB engine launcher — delegates to the windowless VBS (no console window).
REM Kept for manual use; scheduled task + watchdog call restart-stocks.vbs directly.
wscript.exe "%~dp0restart-stocks.vbs"
