# Windows task "system12-hyp", every 10 min: keeps the System 12 hypothesis loop alive (research/system12/hyp12.py --loop).
# It exits at once if a loop is already running. Brake: research/system12/hyp/STOP.
$root = Split-Path (Split-Path (Split-Path $MyInvocation.MyCommand.Path))
Set-Location $root
$env:PYTHONPATH = "$root\research\system12;$root\research\plan_v2;$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
$env:OMP_NUM_THREADS = "2"
$env:PYTHONWARNINGS = "ignore"
& "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe" research\system12\hyp12.py --loop *>> research\system12\hyp\hyp.log
