# Registers Supra Tracker to start (hidden) at user logon. Run once:
#   powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
$root = Split-Path -Parent $PSScriptRoot
$cmd = Join-Path $root 'start.cmd'
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$cmd`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName 'SupraTracker' -Action $action -Trigger $trigger `
  -Settings $settings -Description 'A70 Supra listing tracker dashboard' -Force
Write-Host 'Installed. Tracker starts at next logon. Start it now with:'
Write-Host '  Start-ScheduledTask -TaskName SupraTracker'
