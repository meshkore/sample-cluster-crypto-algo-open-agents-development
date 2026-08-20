# system06 watchdog — keeps the autonomous loop and the monitor server alive.
# Runs from a scheduled task (at logon + every few minutes). If the autoloop or
# the preview server is not running, it relaunches it detached. Respects a STOP
# file: if research/system06/STOP exists, the loop is left stopped on purpose.
$ErrorActionPreference = "SilentlyContinue"
$repo = "c:\Users\Workstation\Documents\Prj\asimovia\meshkore-crypto-cluster"
$s6   = Join-Path $repo "research\system06"
$log  = Join-Path $s6 "watchdog.log"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Log($m) { Add-Content -Path $log -Value "$stamp  $m" -Encoding utf8 }

# --- autoloop ---
$loop = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*quantlab_system06.autoloop*' }
$stop = Test-Path (Join-Path $s6 "STOP")
if (-not $loop -and -not $stop) {
    $seed = Get-Random -Minimum 1 -Maximum 100000
    Start-Process -FilePath "python" `
        -ArgumentList "-m","quantlab_system06.autoloop","--hours","168","--seed","$seed","--skip-prepare" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s6 "autoloop.log") `
        -RedirectStandardError  (Join-Path $s6 "autoloop.err") `
        -WindowStyle Hidden
    Log "autoloop was DOWN -> relaunched (seed $seed, 168h, skip-prepare)"
} elseif ($stop -and $loop) {
    Log "STOP present but autoloop running (pid $($loop.ProcessId)); leaving it (will exit on its own STOP check)"
} elseif ($loop) {
    # alive; no log spam
}

# --- monitor preview server (port 8799) ---
$srv = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
       Where-Object { $_.CommandLine -like '*preview\mock_server.py*' }
if (-not $srv) {
    Start-Process -FilePath "python" `
        -ArgumentList "research\system06\preview\mock_server.py","8799" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s6 "preview\server.log") `
        -RedirectStandardError  (Join-Path $s6 "preview\server.err") `
        -WindowStyle Hidden
    Log "preview server was DOWN -> relaunched on 8799"
}
