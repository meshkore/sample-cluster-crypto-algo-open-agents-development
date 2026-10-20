# Windows task "plan-v2-history", every 6 h: the full-history walk-forward of the paper candidate and the
# lab's top specs (research/plan_v2/history_v2.py) for the Live view. Display only.
$lab = Split-Path $MyInvocation.MyCommand.Path
$root = Split-Path (Split-Path (Split-Path $lab))
Set-Location $root
$env:PYTHONPATH = "$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
$env:OMP_NUM_THREADS = "3"
& "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe" research\plan_v2\history_v2.py *>> (Join-Path $lab "history.log")
