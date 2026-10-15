# Rocket watchdog (Windows task "rocket-watchdog", every 15 min). Separate from System 10's watchdog.
$repo = "C:\Users\Workstation\Documents\Prj\asimovia\meshkore-crypto-cluster"
$root = Join-Path $repo "research\rocket"
if (Test-Path (Join-Path $root "STOP")) { exit 0 }
$env:PYTHONPATH = "$repo\trading-system;$repo\trading-system\systems;$repo\research\system10\tools;$repo\backtester;$repo\live-trading"
$cache = Join-Path $root "cache"
New-Item -ItemType Directory -Force $cache | Out-Null
function Alive($file) {
    if (Test-Path $file) { $p = (Get-Content $file -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { return $true } }
    return $false
}
if (-not (Alive (Join-Path $cache "run.pid"))) {
    $pr = Start-Process -FilePath "python" -ArgumentList @("research\rocket\rocket.py","run","--hours","24") -WorkingDirectory $repo `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root "rocket.log") -RedirectStandardError (Join-Path $root "rocket.err") -PassThru
    Set-Content (Join-Path $cache "run.pid") $pr.Id
}
if (-not (Test-Path (Join-Path $cache "pit_34.npz")) -and -not (Alive (Join-Path $cache "dump.pid"))) {
    $pd = Start-Process -FilePath "python" -ArgumentList @("research\rocket\rocket.py","pit-dump") -WorkingDirectory $repo `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root "pit_dump.log") -RedirectStandardError (Join-Path $root "pit_dump.err") -PassThru
    Set-Content (Join-Path $cache "dump.pid") $pd.Id
}
