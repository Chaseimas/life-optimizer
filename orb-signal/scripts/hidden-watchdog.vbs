' Runs the watchdog with NO visible window (fixes the every-30-min console flash).
CreateObject("WScript.Shell").Run "powershell -NoProfile -ExecutionPolicy Bypass -File C:\orb\scripts\watchdog.ps1", 0, False
