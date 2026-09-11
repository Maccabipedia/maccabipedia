#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# sysstat is what makes a future memory freeze diagnosable -- without it the
# guard below silently skips on a fresh host and we learn nothing, again.
apt-get install -y tinyproxy sysstat

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

# Memory telemetry. sysstat is installed here but records nothing, for two
# independent reasons: /etc/default/sysstat ships ENABLED="false", and on a
# systemd host the /etc/cron.d/sysstat entry is inert by design -- debian-sa1
# exits immediately when /run/systemd/system exists, because periodic sampling
# is sysstat-collect.timer's job, and that timer ships disabled too. The result
# is that after a guest-memory freeze there is no history of which process grew,
# only the freeze itself. Turn both on so the next incident is diagnosable
# (`sar -r -f /var/log/sysstat/sa<DD>`) instead of guesswork.
if [ -f /etc/default/sysstat ]; then
    sed -i 's/^ENABLED=.*/ENABLED="true"/' /etc/default/sysstat
    systemctl enable --now sysstat.service sysstat-collect.timer sysstat-summary.timer \
        || echo "WARN: could not enable sysstat collection"
fi

# Cap the always-on Claude session's memory, so a runaway there is a service
# restart instead of a VM-wide wedge. Guarded: hosts that don't run the mobile
# session have no such unit.
CLAUDE_MOBILE_UNIT="$REAL_HOME/.config/systemd/user/claude-mobile.service"
if [ -f "$CLAUDE_MOBILE_UNIT" ]; then
    DROPIN_DIR="$REAL_HOME/.config/systemd/user/claude-mobile.service.d"
    mkdir -p "$DROPIN_DIR"
    cp "$SCRIPT_DIR/claude-mobile-memory.conf" "$DROPIN_DIR/memory.conf"
    chown -R "${SUDO_USER:-$USER}:" "$DROPIN_DIR"
    # daemon-reload alone pushes the new limits into the live cgroup (verified
    # against memory.max), so the always-on session does not have to be
    # restarted to pick them up. Root can't drive the user bus, hence the echo.
    echo "Installed claude-mobile memory ceiling — apply as your own user with:"
    echo "  systemctl --user daemon-reload"
fi

# Install the Windows-side WSL watchdog: scheduled task that health-checks WSL
# every 5 minutes. When WSL is up this is a no-op; when WSL has crashed it
# boots the distro, and tinyproxy + claude-mobile.service then come up on
# their own. Closes the at-logon-only gap of WslEuroleagueProxy.
#
# The task runs wsl-watchdog-hidden.vbs (no console flash), which runs
# wsl-watchdog.bat, which runs wsl-watchdog.ps1 — the last of those holds the
# real logic, including forcing `wsl --shutdown` when the VM is wedged rather
# than down. All three files are deployed together.
#
# Two-phase install: schtasks /create handles the trigger (the bit its CLI can
# express), then PowerShell Set-ScheduledTask sets the VBS action plus the
# battery and timeout settings that the CLI can't. Doing it as one XML import
# would require admin elevation; this path runs as the current user.
if command -v wslpath >/dev/null 2>&1 && [ -x /mnt/c/Windows/System32/cmd.exe ]; then
    WIN_USERPROFILE=$(/mnt/c/Windows/System32/cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r\n')
    if [ -z "$WIN_USERPROFILE" ] || [[ "$WIN_USERPROFILE" == *system32* ]]; then
        echo "ERROR: %USERPROFILE% resolved to '$WIN_USERPROFILE' — refusing to install."
        exit 1
    fi
    WIN_PROFILE_WSL=$(wslpath "$WIN_USERPROFILE")

    # CRLF endings so cmd.exe and wscript parse multi-line constructs
    # correctly even if future edits add `if errorlevel` blocks.
    for f in wsl-watchdog.bat wsl-watchdog.ps1 wsl-watchdog-hidden.vbs; do
        sed 's/$/\r/' "$SCRIPT_DIR/$f" > "$WIN_PROFILE_WSL/$f"
    done

    BAT_PATH_WIN="${WIN_USERPROFILE}\\wsl-watchdog.bat"
    VBS_PATH_WIN="${WIN_USERPROFILE}\\wsl-watchdog-hidden.vbs"
    /mnt/c/Windows/System32/schtasks.exe /create \
        /tn "WslWatchdog" \
        /tr "$BAT_PATH_WIN" \
        /sc MINUTE /mo 5 /it /f
    # ExecutionTimeLimit must clear the script's own worst case, which is the
    # full failed-recovery path: 90s probe + 60s shutdown + 5s settle + 120s
    # boot probe + 60s ensure-mobile-tab = 335s. 8 minutes leaves headroom;
    # at the original 2 minutes Windows would kill the recovery midway through
    # the restart it was there to perform.
    #
    # -ErrorAction Stop + explicit exit: without it a failure here is
    # non-terminating and the script still prints "=== Done ===" while the task
    # is left half-configured, pointing at the .bat with default settings.
    /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command "
        \$ErrorActionPreference = 'Stop';
        \$a = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument '\"$VBS_PATH_WIN\"';
        \$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 8);
        Set-ScheduledTask -TaskName 'WslWatchdog' -Action \$a -Settings \$s | Out-Null
    " || { echo "ERROR: failed to configure the WslWatchdog task action/settings"; exit 1; }
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
