@echo off
REM ORB Stock Paper-Trading Engine - Auto-start script
REM Scheduled task "ORB Stocks Engine" runs this daily at 5:45 AM (and it can be run manually)

cd /d "C:\Users\kasek\Claude Code\orb-signal"

REM Kill any existing stocks engine (by command line, not window title)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\kill-engine.ps1" -Pattern "engine-stocks" >nul 2>&1

REM Start the engine in a named window
start "ORB Stocks Engine" /MIN cmd /c "npx tsx --env-file=.env.local src/engine-stocks/index.ts > data\stocks-engine.log 2>&1"

echo [%date% %time%] Stocks engine started >> data\scheduler.log
