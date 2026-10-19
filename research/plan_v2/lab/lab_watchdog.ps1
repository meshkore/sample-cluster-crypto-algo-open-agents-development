# Plan v2 lab watchdog (Windows task "plan-v2-lab", every 15 min): relaunches lab_v2.py run when it is not running.
# Brake: research/plan_v2/lab/STOP. Waits while free RAM < 3 GB.
$lab = Split-Path $MyInvocation.MyCommand.Path
$root = Split-Path (Split-Path (Split-Path $lab))
if (Test-Path (Join-Path $lab "STOP")) { exit 0 }
$pidFile = Join-Path $lab "run.pid"
if (Test-Path $pidFile) {
    $p = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($p -and (Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue)) { exit 0 }
}
$os = Get-CimInstance Win32_OperatingSystem
if (($os.FreePhysicalMemory / 1MB) -lt 3) { exit 0 }
$env:PYTHONPATH = "$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
$py = "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe"
Start-Process -FilePath $py -ArgumentList "-u", "research\plan_v2\lab_v2.py", "run", "--hours", "24" -WorkingDirectory $root `
    -RedirectStandardOutput (Join-Path $lab "lab.log") -RedirectStandardError (Join-Path $lab "lab.err") -WindowStyle Hidden
