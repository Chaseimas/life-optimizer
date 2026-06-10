# Kills all node processes whose command line matches the given pattern.
# Used by the start-*.bat scripts so restarts never stack duplicate engines.
# (taskkill by window title is unreliable — cmd retitles windows.)
param([Parameter(Mandatory = $true)][string]$Pattern)

$procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -like "*$Pattern*" }

foreach ($p in $procs) {
  try {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    Write-Host "killed node $($p.ProcessId) ($Pattern)"
  } catch {}
}
