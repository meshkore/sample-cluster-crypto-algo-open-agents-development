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
# The systems moved under trading-system/systems/ on 2026-09-16, so that folder has to
# be on the path for `-m system006_oracle_net_15m.autoloop` to resolve in a fresh process.
$env:PYTHONPATH = "$repo\backtester;$repo\trading-system;$repo\trading-system\systems;$repo\orchestrator-manager;$repo\live-trading"
$log  = Join-Path $s6 "watchdog.log"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Log($m) { Add-Content -Path $log -Value "$stamp  $m" -Encoding utf8 }

# --- autoloop ---
$loop = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*system006_oracle_net_15m.autoloop*' }
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
        -ArgumentList "-m","system006_oracle_net_15m.autoloop","--hours","168","--seed","$seed","--skip-prepare" `
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

# --- numerical optimization workers (operator, 2026-09-04: "24 hours at full") ---
# The TPE search over the whole decision tree is a MULTI-DAY job on this machine
# (~5 min a trial, 2000 trials, six workers sharing one SQLite study). Six processes
# launched by hand die with the session, with a reboot, or one at a time without
# anyone noticing that throughput quietly fell by a sixth. So the run belongs to the
# watchdog, not to a person: OPTIMIZE.json says how many workers and until when, and
# this block tops the fleet back up every beat until the deadline passes.
# The trial budget is GLOBAL (MaxTrialsCallback over the shared study), so relaunching
# a dead worker resumes the search - it never restarts or duplicates the budget.
$optCfgPath = Join-Path $s6 "OPTIMIZE.json"
if ((Test-Path $optCfgPath) -and -not $stop) {
    $optCfg = Get-Content $optCfgPath -Raw | ConvertFrom-Json
    $until  = [datetime]::Parse($optCfg.until).ToUniversalTime()
    $now    = (Get-Date).ToUniversalTime()
    $want   = [int]$optCfg.workers
    # Which search script the fleet runs is now DATA, not a constant. The v3 threshold
    # study closed on 2026-09-07 and v4 replaced it the same day; hard-coding the
    # script name meant the watchdog would have kept resurrecting the finished study
    # while the live one ran unsupervised. Old control files without the field keep
    # working, so nothing that was already deployed breaks.
    $optScript = if ($optCfg.script) { $optCfg.script } else { "research\system06\tools\numerical_optimization.py" }
    $optLeaf   = Split-Path $optScript -Leaf
    $optLogPfx = if ($optCfg.log_prefix) { $optCfg.log_prefix } else { "opt_w" }
    $have   = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
                Where-Object { $_.CommandLine -like "*$optLeaf*" })
    if ($now -lt $until) {
        for ($i = $have.Count; $i -lt $want; $i++) {
            # No --seed is passed: the script derives one from its own pid. Passing $i
            # here looked tidier and was wrong - $i counts from the number ALIVE, so when
            # a middle worker dies the replacement is launched under an index another
            # live worker already holds, and the two would share a seed again. The pid is
            # the only identifier guaranteed distinct among live processes, which is
            # exactly the property the sampler needs. (This comment sits ABOVE the call:
            # a comment line after a backtick continuation is a PARSE ERROR, and a
            # watchdog that does not parse silently stops relaunching EVERY daemon.)
            Start-Process -FilePath "python" `
                -ArgumentList $optScript,
                              "--trials","$($optCfg.trials)","--startup","30","--seeds","64" `
                -WorkingDirectory $repo `
                -RedirectStandardOutput (Join-Path $s6 "$optLogPfx$i.log") `
                -RedirectStandardError  (Join-Path $s6 "$optLogPfx$i.err") `
                -WindowStyle Hidden
            Log "optimizer worker was MISSING ($($have.Count)/$want) -> launched #$i"
            Start-Sleep -Seconds 3   # stagger: six simultaneous SQLite creations race
        }
    } elseif ($have.Count -gt 0) {
        Log "optimizer deadline passed ($($optCfg.until)); leaving $($have.Count) worker(s) to finish their trial"
    }
}

# --- live trader (the execution layer; paper broker) ---------------------------------
# From 2026-09-17 09:00 UTC this is the only process in the fleet whose output is a
# position rather than a number. It respects its own brake, live-trading/state/STOP, so
# the operator can stand the book down without touching research, and it is NOT stopped
# by the research STOP file: an open position still has to be managed while the lab is
# paused. The loop is idempotent per bar and the book is on disk, so a relaunch after a
# crash resumes with the same positions rather than a fresh account.
$liveRoot = Join-Path $repo "live-trading"
$liveStop = Test-Path (Join-Path $liveRoot "state\STOP")
$trader = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
          Where-Object { $_.CommandLine -like '*quantlab_live.trader*' }
# A process that EXISTS is not a process that is WORKING. On 2026-09-19 the box slept
# with the trader running; it woke eight days later into a DNS failure, stopped logging,
# and kept its pid - so this block saw a live trader every five minutes for eight days
# while the book sat unmanaged. Liveness is therefore measured by the OUTPUT, not by the
# pid: bars close every fifteen minutes and each one writes a line, so a log untouched
# for 75 minutes means the loop is not turning, whatever the process table says. The
# threshold is deliberately loose - a cold start re-exports every signal before the first
# bar line - and the kill is safe because the book is on disk and the loop is idempotent
# per bar, which is the same property that makes a crash-relaunch safe.
$traderLog = Join-Path $liveRoot "state	rader.out"
if ($trader -and -not $liveStop -and (Test-Path $traderLog)) {
    $quietFor = (Get-Date) - (Get-Item $traderLog).LastWriteTime
    $aliveFor = (Get-Date) - $trader.CreationDate
    if ($quietFor.TotalMinutes -gt 75 -and $aliveFor.TotalMinutes -gt 75) {
        Log ("live trader STALLED: silent for {0:N0} min (pid {1}, up {2:N0} min) -> killing it" -f `
             $quietFor.TotalMinutes, $trader.ProcessId, $aliveFor.TotalMinutes)
        Stop-Process -Id $trader.ProcessId -Force -Confirm:$false
        Start-Sleep -Seconds 2
        $trader = $null
    }
}
if (-not $trader -and -not $liveStop) {
    # Start-Process TRUNCATES its redirect targets, so relaunching a crashed trader
    # destroyed the only record of WHY it crashed - which is how the 2026-09-27 restart
    # loop was diagnosable only as "was DOWN". Roll the previous pair aside first: one
    # generation is enough to read a stack trace, and it costs a rename.
    foreach ($leaf in @("trader.out", "trader.err")) {
        $live = Join-Path $liveRoot "state\$leaf"
        if (Test-Path $live) {
            Move-Item -Path $live -Destination (Join-Path $liveRoot "state\$leaf.1") -Force -Confirm:$false
        }
    }
    Start-Process -FilePath "python" -ArgumentList "-m","quantlab_live.trader" -WorkingDirectory $repo -RedirectStandardOutput (Join-Path $liveRoot "state\trader.out") -RedirectStandardError (Join-Path $liveRoot "state\trader.err") -WindowStyle Hidden
    Log "live trader was DOWN -> relaunched (paper)"
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

# --- system 10: isolated trainers + a release evaluator (operator, 2026-10-01) ---
# Two trainer workers search condition sets without pause on research bars only (<= 2025)
# and publish a numbered release whenever the champion improves; a separate evaluator
# backtests the newest release on 2026 every hour and on each release. None waits for
# another. Four search workers fit on the GPU (2026-10-10, the operator: "the machine is
# totally dedicated to this job"); system 06's research loops are stopped by their STOP files.
# The GPU is otherwise free: the full-trader PPO (56 h) and the position manager
# (5 releases, 2026-10-10) both lost to the rules out of sample; the next RL job is the
# signal-strength trader, once its deterministic version proves the strength informative.
# (The manager job, 2026-10-09, replaced the full-trader rl job,
# stuck for 56 h) owns the GPU and resumes from its checkpoint, so its
# weights accumulate across restarts; the search workers run on CPU.
# Brake: research/system10/STOP_S10.
$s10 = Join-Path $repo "research\system10"
$stopS10 = $stop -or (Test-Path (Join-Path $s10 "STOP_S10"))
if (-not $stopS10) {
    $jobs = @(
        @{ tag = "w1";        args = @("-m","system010_conditioned_rl.search","--hours","24","--worker","w1","--device","cuda","--threads","2") },
        @{ tag = "w2";        args = @("-m","system010_conditioned_rl.search","--hours","24","--worker","w2","--device","cuda","--threads","2") },
        @{ tag = "w3";        args = @("-m","system010_conditioned_rl.search","--hours","24","--worker","w3","--device","cpu","--threads","4") },
        @{ tag = "w4";        args = @("-m","system010_conditioned_rl.search","--hours","24","--worker","w4","--device","cpu","--threads","4") },
        @{ tag = "status";    args = @("-m","system010_conditioned_rl.status") },
        @{ tag = "forecaster"; args = @("-m","system010_conditioned_rl.forecaster","--hours","24") },
        @{ tag = "evaluator"; args = @("-m","system010_conditioned_rl.evaluator","--hours","6") }
    )
    foreach ($job in $jobs) {
        $pattern = if ($job.tag -eq "evaluator") { "*system010_conditioned_rl.evaluator*" } elseif ($job.tag -eq "status") { "*system010_conditioned_rl.status*" } elseif ($job.tag -eq "forecaster") { "*system010_conditioned_rl.forecaster*" } elseif ($job.tag -eq "manager") { "*system010_conditioned_rl.manager*" } else { "*system010_conditioned_rl.search*--worker $($job.tag)*" }
        $running = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like $pattern }
        if (-not $running) {
            $out = Join-Path $s10 "s10_$($job.tag).log"
            if (Test-Path $out) { Move-Item -Path $out -Destination "$out.1" -Force -Confirm:$false }
            $err = Join-Path $s10 "s10_$($job.tag).err"
            if (Test-Path $err) { Move-Item -Path $err -Destination "$err.1" -Force -Confirm:$false }
            Start-Process -FilePath "python" -ArgumentList $job.args -WorkingDirectory $repo `
                -RedirectStandardOutput $out -RedirectStandardError $err `
                -WindowStyle Hidden
            Log "system10 $($job.tag) was DOWN -> relaunched"
            Start-Sleep -Seconds 30
        }
    }
}

# --- system 10: health every 15 minutes, the full review every 8 hours (operator, 2026-10-08: "evaluate every eight hours
# on a schedule and make the corrections automatically"). It reads files only, stops
# a hung job (relaunched above on the next pass) and tunes the RL through rl_control.json.
$reviewStamp = Join-Path $s10 "rnd\last_review.txt"
if (-not $stopS10 -and (-not (Test-Path $reviewStamp) -or ((Get-Date) - (Get-Item $reviewStamp).LastWriteTime).TotalHours -ge 8 -or (Get-Date).Minute % 15 -lt 5)) {
    Start-Process -FilePath "python" -ArgumentList @("-m","system010_conditioned_rl.review") -WorkingDirectory $repo `
        -RedirectStandardOutput (Join-Path $s10 "s10_review.log") -RedirectStandardError (Join-Path $s10 "s10_review.err") `
        -WindowStyle Hidden
    Log "system10 review launched"
}
