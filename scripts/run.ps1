# ReSubtitle 启动脚本
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[ReSubtitle] 缺少虚拟环境，请先执行:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}
$env:PYTHONPATH = Join-Path $PWD "src"
& ".venv\Scripts\python.exe" -m resubtitle.main @args
exit $LASTEXITCODE
