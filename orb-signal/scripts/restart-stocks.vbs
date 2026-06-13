' Restart the stock ORB engine with NO visible window.
' Used by the 5:45 AM scheduled task and the watchdog. wscript runs this
' windowlessly; window-style 0 hides the kill + launch consoles too.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -File C:\orb\scripts\kill-engine.ps1 -Pattern engine-stocks", 0, True
sh.Run "cmd /c cd /d C:\orb && npx tsx --env-file=.env.local src/engine-stocks/index.ts >> data\stocks-engine.log 2>&1", 0, False
