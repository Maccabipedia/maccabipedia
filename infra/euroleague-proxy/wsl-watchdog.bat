@echo off
REM Boots the Ubuntu WSL distro if it's down. No-op when already running.
REM Installed by infra/euroleague-proxy/install.sh and run every 5 min
REM by the WslWatchdog scheduled task.
REM
REM Once WSL is up, tinyproxy (enabled, with Restart=on-failure) and
REM claude-mobile.service (enabled + linger=yes) come up automatically.
wsl -d Ubuntu -e true
