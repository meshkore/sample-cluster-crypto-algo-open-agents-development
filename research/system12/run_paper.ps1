# Windows task "system12-paper", every 4 h: System 12 shadow paper book (research/system12/paper12.py).
$root = Split-Path (Split-Path (Split-Path $MyInvocation.MyCommand.Path))
Set-Location $root
$env:PYTHONPATH = "$root\research\system12;$root\research\plan_v2;$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
$env:OMP_NUM_THREADS = "2"
& "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe" research\system12\paper12.py *>> research\system12\paper\paper.log
