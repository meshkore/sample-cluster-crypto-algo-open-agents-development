# Scheduled every 4h (Windows task "system12-paper"): update the paper book, rebuild and publish the pages, and keep
# the local page server on http://localhost:8799 running. Set SYSTEM12_PYTHON to use a specific interpreter.
$root = Split-Path $PSScriptRoot
Set-Location $root
$env:PYTHONWARNINGS = "ignore"
$py = if ($env:SYSTEM12_PYTHON) { $env:SYSTEM12_PYTHON } else { (Get-Command python -ErrorAction Stop).Source }
$data = if ($env:SYSTEM12_DATA) { $env:SYSTEM12_DATA } else { Join-Path (Split-Path $root) "meshkore-crypto-data" }
$log = Join-Path $data "paper\run.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

& $py -m system12.paper *>> $log
& $py -m system12.web --deploy *>> $log

if (-not (Get-NetTCPConnection -LocalPort 8799 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process $py -ArgumentList "-m", "system12.web.serve", "8799" -WorkingDirectory $root -WindowStyle Hidden
}
