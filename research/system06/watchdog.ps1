# system06 watchdog — keeps the autonomous loop and the PUBLIC-cloud daemons alive.
# Runs from a scheduled task (at logon + every few minutes). Relaunches, detached,
# any of the three required daemons if down: the autoloop, the Cloudflare pusher
# (cf_pusher) and the cluster Wall listener (wall_listener). Respects a STOP file:
# if research/system06/STOP exists, the loop is left stopped on purpose.
# NOTE (2026-08-20): the local mock_server (:8799) is intentionally NOT managed here
# anymore — the operator wants it OFF; the public site (system06-lab.rjj.workers.dev)
# is fed by cf_pusher, which reads the loop's files directly and needs no local server.
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
# Per-daemon brakes (2026-09-02). Both the autoloop and the runner train on the same
# 8GB card, and two trainings on it do not run at half speed - they spill past the
# VRAM and an epoch goes from thirty seconds to half an hour. The single STOP file
# could only silence both, so a focused job meant stopping all research. These flags
# hand the machine to one job while the rest of the circuit keeps publishing.
$stopLoop = $stop -or (Test-Path (Join-Path $s6 "STOP_AUTOLOOP"))
$stopAuto = $stop -or (Test-Path (Join-Path $s6 "STOP_AUTOTEST"))
if (-not $loop -and -not $stopLoop) {
    $seed = Get-Random -Minimum 1 -Maximum 100000
    Start-Process -FilePath "python" `
        -ArgumentList "-m","quantlab_system06.autoloop","--hours","168","--seed","$seed","--skip-prepare" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s6 "autoloop.log") `
        -RedirectStandardError  (Join-Path $s6 "autoloop.err") `
        -WindowStyle Hidden
    Log "autoloop was DOWN -> relaunched (seed $seed, 168h, skip-prepare)"
} elseif ($stopLoop -and $loop) {
    Log "STOP present but autoloop running (pid $($loop.ProcessId)); leaving it (will exit on its own STOP check)"
} elseif ($loop) {
    # alive; no log spam
}

# --- autotest: the autonomous EXPERIMENT runner (paired tests + mechanical review) ---
# The autoloop searches genomes; this one runs the queued experiments in rnd/program.jsonl
# as paired tests on the champion genome and writes a state-of-the-search review. Together
# they are the whole research cycle running unattended: train, backtest, test ideas, judge.
$auto = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*system06\autotest.py*' -or $_.CommandLine -like '*system06/autotest.py*' }
if (-not $auto -and -not $stopAuto) {
    Start-Process -FilePath "python" `
        -ArgumentList "research\system06\autotest.py" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s6 "autotest.log") `
        -RedirectStandardError  (Join-Path $s6 "autotest.err") `
        -WindowStyle Hidden
    Log "autotest was DOWN -> relaunched"
}

# --- hourly pulse (the MACHINE's own trace; operator requirement 2026-08-29) ---
$pulse = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
         Where-Object { $_.CommandLine -like '*system06\pulse.py*' -or $_.CommandLine -like '*system06/pulse.py*' }
if (-not $pulse -and -not $stop) {
    Start-Process -FilePath "python" `
        -ArgumentList "research\system06\pulse.py" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s6 "pulse.log") `
        -RedirectStandardError  (Join-Path $s6 "pulse.err") `
        -WindowStyle Hidden
    Log "pulse was DOWN -> relaunched"
}

# --- Cloudflare pusher (feeds the PUBLIC dashboard) ---
$push = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*preview\cf_pusher.py*' }
if (-not $push) {
    Start-Process -FilePath "python" `
        -ArgumentList "research\system06\preview\cf_pusher.py" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s6 "preview\cf_pusher.log") `
        -RedirectStandardError  (Join-Path $s6 "preview\cf_pusher.err") `
        -WindowStyle Hidden
    Log "cf_pusher was DOWN -> relaunched"
}

# --- cluster Wall listener (receives peer ideas into wall_inbox.jsonl) ---
$wall = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*preview\wall_listener.py*' }
if (-not $wall) {
    Start-Process -FilePath "python" `
        -ArgumentList "research\system06\preview\wall_listener.py" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s6 "preview\wall_listener.out") `
        -RedirectStandardError  (Join-Path $s6 "preview\wall_listener.err") `
        -WindowStyle Hidden
    Log "wall_listener was DOWN -> relaunched"
}

# --- local mock_server (:8799): intentionally OFF. If something else started it, kill it. ---
$srv = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
       Where-Object { $_.CommandLine -like '*preview\mock_server.py*' }
if ($srv) {
    $srv | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Log "mock_server (:8799) was running -> killed (operator wants it off)"
}
