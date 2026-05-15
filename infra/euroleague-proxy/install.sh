#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

apt-get install -y tinyproxy

if ! command -v tailscale >/dev/null 2>&1; then
    echo "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "gh CLI not found — install it and run 'gh auth login' before continuing"
    exit 1
fi

if [ ! -f /etc/tinyproxy/maccabipedia.conf ]; then
    read -rp "Enter proxy username: " proxy_user
    read -rsp "Enter proxy password: " proxy_pass
    echo ""
    cat "$SCRIPT_DIR/tinyproxy.conf" > /etc/tinyproxy/maccabipedia.conf
    echo "BasicAuth $proxy_user $proxy_pass" >> /etc/tinyproxy/maccabipedia.conf
    chmod 600 /etc/tinyproxy/maccabipedia.conf
fi

cp "$SCRIPT_DIR/maccabipedia.filter" /etc/tinyproxy/maccabipedia.filter
REAL_HOME=$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)
sed "s|REAL_USER_HOME|$REAL_HOME|" "$SCRIPT_DIR/notify-failure@.service" > /etc/systemd/system/notify-failure@.service

mkdir -p /etc/systemd/system/tinyproxy.service.d
echo '[Unit]' > /etc/systemd/system/tinyproxy.service.d/notify.conf
echo 'OnFailure=notify-failure@%n.service' >> /etc/systemd/system/tinyproxy.service.d/notify.conf
echo '[Service]' > /etc/systemd/system/tinyproxy.service.d/config.conf
echo 'ExecStart=' >> /etc/systemd/system/tinyproxy.service.d/config.conf
echo 'ExecStart=/usr/bin/tinyproxy -d -c /etc/tinyproxy/maccabipedia.conf' >> /etc/systemd/system/tinyproxy.service.d/config.conf

# Auto-restart tinyproxy if it crashes while WSL stays up. Without this the
# only recovery path is a full WSL reboot, since tinyproxy ships with no
# Restart= directive.
echo '[Service]' > /etc/systemd/system/tinyproxy.service.d/restart.conf
echo 'Restart=on-failure' >> /etc/systemd/system/tinyproxy.service.d/restart.conf
echo 'RestartSec=5s' >> /etc/systemd/system/tinyproxy.service.d/restart.conf

mkdir -p /etc/systemd/system/tailscaled.service.d
echo '[Unit]' > /etc/systemd/system/tailscaled.service.d/notify.conf
echo 'OnFailure=notify-failure@%n.service' >> /etc/systemd/system/tailscaled.service.d/notify.conf

systemctl daemon-reload
systemctl enable --now tinyproxy tailscaled

# Install the Windows-side WSL watchdog: a 5-minute scheduled task that runs
# `wsl -d Ubuntu -e true`. When WSL is up this is a no-op; when WSL has
# crashed it boots the distro, and tinyproxy + claude-mobile.service then
# come up on their own. Closes the at-logon-only gap of WslEuroleagueProxy.
if command -v wslpath >/dev/null 2>&1 && [ -x /mnt/c/Windows/System32/cmd.exe ]; then
    WIN_USERPROFILE=$(/mnt/c/Windows/System32/cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r\n')
    WIN_PROFILE_WSL=$(wslpath "$WIN_USERPROFILE")
    cp "$SCRIPT_DIR/wsl-watchdog.bat" "$WIN_PROFILE_WSL/wsl-watchdog.bat"
    /mnt/c/Windows/System32/schtasks.exe /create \
        /tn "WslWatchdog" \
        /tr "$WIN_USERPROFILE\\wsl-watchdog.bat" \
        /sc MINUTE /mo 5 /it /f
else
    echo "Skipping WslWatchdog install — not running inside WSL on a Windows host."
fi

echo ""
echo "=== Done ==="
echo "Next: run 'tailscale up' to authenticate (one-time, browser will open)."
echo "Then get your stable Tailscale IP: tailscale ip -4"
echo "Set GitHub secrets:"
echo "  TAILSCALE_AUTHKEY — create at https://login.tailscale.com/admin/settings/keys (ephemeral, reusable)"
echo "  EUROLEAGUE_HTTPS_PROXY — http://<proxy-user>:<proxy-pass>@<tailscale-ip>:8787"
