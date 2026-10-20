# Plan v2 lab watchdog (Windows task "plan-v2-lab", every 15 min). Keeps the lab workers alive:
# w1-w4 on the CPU (ridge / GBM family, 3 threads each), g1 on the GPU (MLP family).
# Brake: research/plan_v2/lab/STOP. A worker is only (re)started while free RAM >= 3 GB.
$lab = Split-Path $MyInvocation.MyCommand.Path
$root = Split-Path (Split-Path (Split-Path $lab))
if (Test-Path (Join-Path $lab "STOP")) { exit 0 }
$env:PYTHONPATH = "$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
$env:OMP_NUM_THREADS = "3"
$py = "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe"
foreach ($w in @("w1", "w2", "w3", "w4", "g1", "g2")) {
    $pidFile = Join-Path $lab "run_$w.pid"
    if (Test-Path $pidFile) {
        $p = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { continue }
    }
    $os = Get-CimInstance Win32_OperatingSystem
    if (($os.FreePhysicalMemory / 1MB) -lt 3) { continue }
    Start-Process -FilePath $py -ArgumentList "-u", "research\plan_v2\lab_v2.py", "run", "--hours", "24", "--worker", $w `
        -WorkingDirectory $root -RedirectStandardOutput (Join-Path $lab "lab_$w.log") `
        -RedirectStandardError (Join-Path $lab "lab_$w.err") -WindowStyle Hidden
    Start-Sleep -Seconds 60
}
