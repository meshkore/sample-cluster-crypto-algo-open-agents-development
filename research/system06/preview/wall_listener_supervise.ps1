<#
    Keep the MeshKore Wall listener alive across log-ons, crashes and reboots.

    WHY THIS EXISTS

    The listener died on 2026-09-11 at 18:16 and nobody noticed until 2026-09-13 at 16:10.
    For two days this agent showed as connected to anyone who asked the cluster, and was
    not there. Presence that depends on a human noticing is not presence, and the operator
    should not be the supervisor of a daemon.

    It registers a Scheduled Task that starts at log-on and restarts the process if it
    stops. It does NOT bypass any execution policy, install a service, or run as SYSTEM:
    the listener reads a public tokenless cluster and writes files, and it should have
    exactly the privileges of the person who runs it.

    Install:    powershell -File wall_listener_supervise.ps1 -Install
    Status:     powershell -File wall_listener_supervise.ps1 -Status
    Remove:     powershell -File wall_listener_supervise.ps1 -Remove
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Status,
    [switch]$Remove
)

$TaskName = 'MeshKore-WallListener-win-opus-5'
$Repo     = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$Script   = Join-Path $PSScriptRoot 'wall_listener.py'

function Get-PythonPath {
    $p = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $p) { throw 'python not found on PATH' }
    return $p
}

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "removed $TaskName"
    return
}

if ($Status) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Write-Output "NOT INSTALLED: $TaskName"; return }
    $i = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Output "state=$($t.State) lastRun=$($i.LastRunTime) lastResult=$($i.LastTaskResult)"
    return
}

if ($Install) {
    if (-not (Test-Path $Script)) { throw "listener not found: $Script" }
    $python = Get-PythonPath

    # -u so the log is written as it happens rather than when a buffer happens to flush.
    # A supervised daemon whose output appears an hour late is a daemon nobody can debug.
    $action = New-ScheduledTaskAction -Execute $python `
        -Argument "-u `"$Script`"" -WorkingDirectory $Repo
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    # RestartCount/RestartInterval are the whole point: the listener reconnects on its own
    # with backoff, but it cannot recover from being killed, and that is how it died.
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Write-Output "installed $TaskName -> $python -u $Script (cwd $Repo)"
    return
}

Write-Output 'nothing to do; pass -Install, -Status or -Remove'
