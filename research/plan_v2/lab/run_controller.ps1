# Windows task "plan-v2-controller", every 5 min: the loop controller (research/plan_v2/controller.py).
$lab = Split-Path $MyInvocation.MyCommand.Path
$root = Split-Path (Split-Path (Split-Path $lab))
Set-Location $root
$env:PYTHONPATH = "$root\trading-system;$root\trading-system\systems;$root\research\system10\tools;$root\backtester;$root\live-trading"
& "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe" research\plan_v2\controller.py *>> (Join-Path $lab "controller.log")
