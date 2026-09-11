# WSL health watchdog. Run every 5 minutes by the WslWatchdog scheduled task.
#
# Handles TWO failure modes; the original `wsl -e true` one-liner only handled
# the first:
#
#   1. WSL is DOWN  -- `wsl -e true` boots the distro. tinyproxy and
#      claude-mobile.service are enabled (+ linger), so they follow on their own.
#   2. WSL is WEDGED -- the VM is alive but unresponsive (guest memory
#      exhaustion; the kernel can wedge before the OOM killer is ever
#      scheduled, so nothing is reclaimed and nothing recovers). Here
#      `wsl -e true` blocks forever instead of failing, so the old watchdog
#      spun uselessly every 5 minutes and the box needed a human at the
#      keyboard to type `wsl --shutdown`. That is the case this script exists
#      for: after $MaxConsecutiveFailures probe timeouts it issues the
#      shutdown itself and boots the distro back up.
#
# Every probe is bounded by a timeout, so this script can never itself become
# the thing that hangs.
#
# KEEP THIS FILE PURE ASCII. Windows PowerShell 5.1 decodes a BOM-less .ps1 as
# Windows-1252, so a UTF-8 em-dash arrives as three bytes -- one of them 0x94,
# a curly quote that PowerShell honours as a real string delimiter. The result
# is a parse error reported far from the character that caused it. Check with:
#   grep -nP '[^\x00-\x7F]' wsl-watchdog.ps1

$ErrorActionPreference = 'Stop'

# A cold boot of the distro finishes well inside 90s, so a probe that exceeds
# it is genuinely pathological rather than merely slow. At a 5-minute task
# interval, 3 consecutive failures means ~11 minutes of confirmed
# unresponsiveness before we force a restart -- deliberately conservative,
# because `wsl --shutdown` kills whatever the VM was doing. Lower it for
# faster recovery at the cost of more false positives.
$ProbeTimeoutSec         = 90
$ShutdownTimeoutSec      = 60
$BootTimeoutSec          = 120
$MobileTabTimeoutSec     = 60
$MaxConsecutiveFailures  = 3
$MaxLogBytes             = 512KB

# "Consecutive" has to mean consecutive in TIME, not just three entries in a
# file. The task doesn't tick while the machine is asleep or off, so without
# decay a stall last week plus two today would look like a live wedge and force
# a restart. Any failure older than this is stale and the count restarts.
$FailureDecayMin         = 30

# Hard ceiling on how often a shutdown may be issued, whatever the failure
# count says. `wsl --shutdown` is global -- it takes down every distro and any
# Docker running on WSL2 -- so an unbounded retry is far worse than staying
# down: it would also repeatedly kill a human mid-repair. This guarantees at
# most one shutdown per window and leaves a usable gap to work in.
$RecoveryCooldownMin     = 30

$StateDir  = Join-Path $env:LOCALAPPDATA 'wsl-watchdog'
$LogFile   = Join-Path $StateDir 'watchdog.log'
$StateFile = Join-Path $StateDir 'state.json'
$LockFile  = Join-Path $StateDir 'watchdog.lock'
$WslExe    = Join-Path $env:SystemRoot 'System32\wsl.exe'

if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    try {
        if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt $MaxLogBytes)) {
            Move-Item $LogFile "$LogFile.1" -Force
        }
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch { }
}

# Runs wsl.exe under a hard timeout. On timeout the whole process tree is
# killed -- a wedged `wsl.exe` spawns children that outlive a bare Kill() and
# would otherwise pile up once per tick for the length of the outage.
function Invoke-Wsl {
    param([string]$Arguments, [int]$TimeoutSec)

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $WslExe
    $psi.Arguments              = $Arguments
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true

    $proc = [System.Diagnostics.Process]::Start($psi)
    # Drain both pipes asynchronously: a synchronous ReadToEnd would deadlock
    # against WaitForExit if the child ever filled a pipe buffer.
    $null = $proc.StandardOutput.ReadToEndAsync()
    $null = $proc.StandardError.ReadToEndAsync()

    if ($proc.WaitForExit($TimeoutSec * 1000)) {
        return [pscustomobject]@{ TimedOut = $false; ExitCode = $proc.ExitCode }
    }

    try {
        & "$env:SystemRoot\System32\taskkill.exe" /PID $proc.Id /T /F 2>&1 | Out-Null
    } catch { }
    return [pscustomobject]@{ TimedOut = $true; ExitCode = $null }
}

# The claude-mobile tmux server dies with WSL, taking its Windows Terminal tab
# with it, and the Startup-folder VBS only reopens that tab at logon -- so a
# mid-session WSL restart leaves the service healed but headless.
# ensure-mobile-tab reopens it once per tmux generation.
#
# Best-effort: a failure here must not fail the watchdog, but it must not
# vanish either. The `if` form (rather than `&&`) keeps the exit code 0 on
# hosts that don't run the mobile session at all, so their logs stay quiet
# while a genuine failure on this host still gets recorded.
function Invoke-MobileTab {
    $result = Invoke-Wsl -TimeoutSec $MobileTabTimeoutSec `
        -Arguments '-e bash -lc "if command -v ensure-mobile-tab >/dev/null; then ensure-mobile-tab; fi"'
    if ($result.TimedOut) {
        Write-Log 'WARN ensure-mobile-tab timed out'
    } elseif ($result.ExitCode -ne 0) {
        Write-Log ("WARN ensure-mobile-tab exited {0}" -f $result.ExitCode)
    }
}

# State carries timestamps, not just a tally, so the two guards above can be
# enforced. A missing or corrupt file reads as pristine -- the watchdog must
# still function on a fresh host, and a bad parse must not wedge it.
function Get-State {
    $blank = [pscustomobject]@{ Failures = 0; LastFailureUtc = $null; LastRecoveryUtc = $null }
    if (-not (Test-Path $StateFile)) { return $blank }
    try {
        $s = Get-Content $StateFile -Raw -ErrorAction Stop | ConvertFrom-Json
        return [pscustomobject]@{
            Failures        = [int]$s.Failures
            LastFailureUtc  = $s.LastFailureUtc
            LastRecoveryUtc = $s.LastRecoveryUtc
        }
    } catch {
        Write-Log 'WARN state file unreadable -- treating as a clean slate'
        return $blank
    }
}

function Set-State {
    param([int]$Failures, $LastFailureUtc, $LastRecoveryUtc)
    [pscustomobject]@{
        Failures        = $Failures
        LastFailureUtc  = $LastFailureUtc
        LastRecoveryUtc = $LastRecoveryUtc
    } | ConvertTo-Json | Set-Content -Path $StateFile -Encoding ASCII
}

# Minutes since an ISO-8601 UTC stamp. Returns $null when never set or
# unparseable, which every caller treats as "long ago".
#
# RoundtripKind is load-bearing. A bare [datetime]::Parse silently converts the
# trailing Z to LOCAL time, so subtracting it from a UTC "now" yields the
# elapsed time minus the UTC offset -- negative for any positive offset. The
# cooldown then reads as "-179 minutes ago" and never expires on schedule.
function Get-MinutesSince {
    param($Utc)
    if (-not $Utc) { return $null }
    try {
        $parsed = [datetime]::Parse($Utc, [Globalization.CultureInfo]::InvariantCulture,
                                    [Globalization.DateTimeStyles]::RoundtripKind)
        return ((Get-Date).ToUniversalTime() - $parsed.ToUniversalTime()).TotalMinutes
    }
    catch { return $null }
}

# The scheduled task is configured MultipleInstances=IgnoreNew, but that only
# guards overlap when the action actually blocks -- keep a lock of our own so a
# stuck run can never be lapped by the next tick.
$lockStream = $null
try {
    $lockStream = [System.IO.File]::Open($LockFile, 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
    Write-Log 'SKIP previous run still in progress'
    exit 0
}

try {
    $state = Get-State
    $probe = Invoke-Wsl -Arguments '-e true' -TimeoutSec $ProbeTimeoutSec

    if (-not $probe.TimedOut -and $probe.ExitCode -eq 0) {
        if ($state.Failures -gt 0) {
            Write-Log 'OK wsl responsive again -- clearing failure count'
            Set-State -Failures 0 -LastFailureUtc $null -LastRecoveryUtc $state.LastRecoveryUtc
        }
        Invoke-MobileTab
        exit 0
    }

    if ($probe.TimedOut) {
        # Only failures close together in time count as consecutive; an old one
        # restarts the tally rather than topping it up.
        $sinceFailure = Get-MinutesSince $state.LastFailureUtc
        $failures = if ($null -eq $sinceFailure -or $sinceFailure -gt $FailureDecayMin) { 1 }
                    else { $state.Failures + 1 }
        $nowUtc = (Get-Date).ToUniversalTime().ToString('o')
        Set-State -Failures $failures -LastFailureUtc $nowUtc -LastRecoveryUtc $state.LastRecoveryUtc
        Write-Log ("HANG probe timed out after ${ProbeTimeoutSec}s ({0}/{1})" -f $failures, $MaxConsecutiveFailures)

        if ($failures -lt $MaxConsecutiveFailures) { exit 1 }

        $sinceRecovery = Get-MinutesSince $state.LastRecoveryUtc
        if ($null -ne $sinceRecovery -and $sinceRecovery -lt $RecoveryCooldownMin) {
            Write-Log ("SUPPRESSED threshold reached, but a shutdown was issued {0:N0}m ago -- backing off" -f $sinceRecovery)
            exit 1
        }

        # Stamp the attempt and clear the count BEFORE acting, not after. If the
        # recovery fails -- or this process is killed partway through by the
        # task's ExecutionTimeLimit -- the cooldown is already on disk, so the
        # next tick backs off instead of firing another shutdown. Recording it
        # only on success is what turned one failed recovery into a global
        # `wsl --shutdown` every 5 minutes, forever.
        Set-State -Failures 0 -LastFailureUtc $nowUtc -LastRecoveryUtc $nowUtc

        # Confirmed wedge. `wsl --shutdown` tears the VM down at the hypervisor
        # level, which is the only thing that clears this state -- and until
        # now the only thing nobody could do remotely.
        Write-Log 'RECOVER threshold reached -- issuing wsl --shutdown'
        $shutdown = Invoke-Wsl -Arguments '--shutdown' -TimeoutSec $ShutdownTimeoutSec
        if ($shutdown.TimedOut) {
            Write-Log 'ERROR wsl --shutdown itself timed out -- next attempt gated by cooldown'
            exit 1
        }

        Start-Sleep -Seconds 5
        $boot = Invoke-Wsl -Arguments '-e true' -TimeoutSec $BootTimeoutSec
        if ($boot.TimedOut -or $boot.ExitCode -ne 0) {
            Write-Log 'ERROR distro did not come back after shutdown -- next attempt gated by cooldown'
            exit 1
        }

        Write-Log 'RECOVER distro is back up'
        Invoke-MobileTab
        exit 0
    }

    # Probe returned promptly but non-zero. WSL is reachable and answering, so
    # this is not the wedge case -- don't let it accumulate toward a restart.
    Write-Log ("WARN probe exited {0} -- not a hang, not counting toward restart" -f $probe.ExitCode)
    exit $probe.ExitCode
}
finally {
    if ($lockStream) { $lockStream.Close() }
}
