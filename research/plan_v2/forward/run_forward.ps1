# Windows task "plan-v2-forward-ic", every 4 h: runs the forward IC tracker (research/plan_v2/forward_ic.py).
$root = Split-Path (Split-Path (Split-Path (Split-Path $MyInvocation.MyCommand.Path)))
Set-Location $root
$env:PYTHONPATH = "$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
$py = "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe"
& $py research\plan_v2\forward_ic.py *> research\plan_v2\forward\forward.log
& $py research\plan_v2\paper_v2.py *> research\plan_v2\paper_v2\paper.log
