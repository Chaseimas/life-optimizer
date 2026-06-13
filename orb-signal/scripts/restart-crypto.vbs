' Restart the crypto ORB engine with NO visible window.
' Used by the 5:45 AM scheduled task and the watchdog.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -File C:\orb\scripts\kill-engine.ps1 -Pattern src/engine/index.ts", 0, True
sh.Run "cmd /c cd /d C:\orb && npx tsx --env-file=.env.local src/engine/index.ts >> data\engine.log 2>&1", 0, False
