' Launches wsl-watchdog.bat with no visible console window, so the 5-minute
' WslWatchdog tick doesn't flash a window over whatever is on screen.
'
' bWaitOnReturn MUST stay True. With False, wscript returns the instant it
' spawns the .bat, so the scheduled task reported success immediately and
' detached: ExecutionTimeLimit never applied to the real work, the
' MultipleInstances=IgnoreNew guard never engaged, and "Last Result: 0" was
' meaningless. During a WSL hang that spawned a fresh orphaned watchdog every
' 5 minutes, none of which could be reaped. Waiting makes the task's timeout,
' overlap guard, and exit code mean what they claim to.
Option Explicit
Dim fso, shell, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
' Resolve the .bat next to this script rather than hardcoding a user profile
' path, so the pair can be dropped into any %USERPROFILE%.
batPath = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "wsl-watchdog.bat")
WScript.Quit shell.Run("""" & batPath & """", 0, True)
