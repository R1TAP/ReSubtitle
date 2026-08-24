# LiveSubtitle 启动脚本
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[LiveSubtitle] 缺少虚拟环境，请先执行:"
    Write-Host "  python -m venv --without-pip .venv"
    Write-Host "  .venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}
$env:PYTHONPATH = Join-Path $PWD "src"
& ".venv\Scripts\python.exe" -m livesub.main @args
exit $LASTEXITCODE
