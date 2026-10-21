# Windows task "system12-lab", every 5 min: System 12 lab controller (keeps the workers alive, merges the scoreboard).
$root = Split-Path (Split-Path (Split-Path $MyInvocation.MyCommand.Path))
Set-Location $root
$env:PYTHONPATH = "$root\research\system12;$root\research\plan_v2;$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
$env:OMP_NUM_THREADS = "2"
& "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe" research\system12\controller12.py *>> research\system12\lab\controller.log
