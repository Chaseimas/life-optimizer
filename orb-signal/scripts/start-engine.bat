@echo off
REM Crypto ORB engine launcher — delegates to the windowless VBS (no console window).
REM Kept for manual use; scheduled task + watchdog call restart-crypto.vbs directly.
wscript.exe "%~dp0restart-crypto.vbs"
