@echo off
REM Boots the default WSL distro if it's down. No-op when already running.
REM Installed by infra/euroleague-proxy/install.sh and run every 5 minutes
REM by the WslWatchdog scheduled task.
REM
REM Once WSL is up, tinyproxy (enabled, with Restart=on-failure) and
REM claude-mobile.service (enabled + linger=yes) come up automatically.
wsl -e true
exit /b %ERRORLEVEL%
