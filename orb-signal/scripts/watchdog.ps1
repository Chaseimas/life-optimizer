# Engine watchdog — runs every 30 min via Task Scheduler.
# Starts any engine that isn't running. Survives: closed windows, crashes,
# failed scheduled starts, logon after reboot.
$base = "C:\Users\kasek\Claude Code\orb-signal"

function Test-Engine([string]$pattern) {
  $procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like "*$pattern*" }
  return @($procs).Count -gt 0
}

$log = Join-Path $base "data\scheduler.log"
$stamp = Get-Date -Format "ddd MM/dd/yyyy HH:mm:ss"

# Restarts go through wscript so the relaunch is windowless too (no flash on revive).
if (-not (Test-Engine "engine-stocks")) {
  Start-Process -FilePath "wscript.exe" -ArgumentList "C:\orb\scripts\restart-stocks.vbs"
  Add-Content $log "[$stamp] WATCHDOG: stocks engine was DOWN - restarted"
}

if (-not (Test-Engine "src/engine/index.ts")) {
  Start-Process -FilePath "wscript.exe" -ArgumentList "C:\orb\scripts\restart-crypto.vbs"
  Add-Content $log "[$stamp] WATCHDOG: crypto engine was DOWN - restarted"
}
