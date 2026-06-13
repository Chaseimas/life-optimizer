@echo off
REM Manually stop both engines (kills by command line — windows are now hidden,
REM so the old window-title taskkill no longer applies).
REM NOTE: the watchdog will revive them within 30 min. To stop for real, also
REM disable the "ORB Watchdog" / "ORB Stocks Engine" scheduled tasks.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill-engine.ps1" -Pattern engine-stocks
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill-engine.ps1" -Pattern src/engine/index.ts
echo Engines stopped.
