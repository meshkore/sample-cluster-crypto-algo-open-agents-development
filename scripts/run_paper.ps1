# Windows task "system12-paper", every 4 h: recompute the System 12 paper book, then rebuild and publish the page.
$root = Split-Path (Split-Path $MyInvocation.MyCommand.Path)
Set-Location $root
$env:PYTHONWARNINGS = "ignore"
$py = "C:\Users\Workstation\AppData\Local\Programs\Python\Python311\python.exe"
$log = Join-Path (Split-Path $root) "meshkore-crypto-data\paper\run.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
& $py -m system12.paper *>> $log
& $py -m system12.publish --deploy *>> $log
