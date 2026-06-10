@echo off
REM ORB Signal Engine - Auto-stop script
REM Called by Windows Task Scheduler at 4:05 PM ET on weekdays

taskkill /F /FI "WINDOWTITLE eq ORB Engine" >nul 2>&1

echo [%date% %time%] Engine stopped >> "C:\Users\kasek\Claude Code\orb-signal\data\scheduler.log"
