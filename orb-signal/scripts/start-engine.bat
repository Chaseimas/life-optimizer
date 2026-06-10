@echo off
REM ORB Signal Engine (crypto) - Auto-start script
REM Scheduled task "ORB Signal Engine Daily" runs this daily at 5:45 AM (and it can be run manually)

cd /d "C:\Users\kasek\Claude Code\orb-signal"

REM Kill any existing crypto engine (by command line, not window title)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\kill-engine.ps1" -Pattern "src/engine/index.ts" >nul 2>&1

REM Start the engine in a named window
start "ORB Engine" /MIN cmd /c "npx tsx --env-file=.env.local src/engine/index.ts > data\engine.log 2>&1"

echo [%date% %time%] Engine started >> data\scheduler.log
