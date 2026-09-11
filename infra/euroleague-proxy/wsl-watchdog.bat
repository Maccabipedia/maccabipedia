@echo off
REM Thin launcher for wsl-watchdog.ps1, which holds the actual health logic
REM (probe under a hard timeout, and force `wsl --shutdown` when the VM is
REM wedged rather than merely down). Installed alongside the .ps1 in
REM %USERPROFILE% by infra/euroleague-proxy/install.sh and run every 5 minutes
REM by the WslWatchdog scheduled task.
REM
REM Kept as a .bat because both the scheduled task and the hidden-window VBS
REM wrapper address it by that name.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0wsl-watchdog.ps1"
exit /b %ERRORLEVEL%
