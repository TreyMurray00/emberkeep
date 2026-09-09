$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    & $pythonPath -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
}
& $pythonPath server/setup_local.py
docker compose up -d --wait
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and retry.' }
$nodePath = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $nodePath) {
    $nodePath = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
}
if (-not (Test-Path -LiteralPath $nodePath)) { throw 'Install Node.js 22 or newer.' }
$cli = Join-Path $projectRoot 'web/node_modules/vinext/dist/cli.js'
if (-not (Test-Path -LiteralPath $cli)) { throw 'Install web dependencies with pnpm 9.11.0 in the web folder first.' }
$logs = Join-Path $projectRoot '.logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
function Test-LocalEndpoint($url) {
    try { return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { return $false }
}
if (-not (Test-LocalEndpoint 'http://127.0.0.1:8000/api/health')) {
    Start-Process -FilePath $pythonPath -ArgumentList '-m uvicorn server.app:app --host 127.0.0.1 --port 8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'api.log') -RedirectStandardError (Join-Path $logs 'api-error.log')
}
if (-not (Test-LocalEndpoint 'http://127.0.0.1:5173/')) {
    Start-Process -FilePath $nodePath -ArgumentList ('"' + $cli + '" dev') -WorkingDirectory (Join-Path $projectRoot 'web') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'web.log') -RedirectStandardError (Join-Path $logs 'web-error.log')
}
Write-Host 'Game: http://127.0.0.1:5173/'
Write-Host 'Admin: http://127.0.0.1:5173/admin/ai'
Write-Host 'The admin password is ADMIN_PASSWORD in the local .env file. Logs are in .logs/.'
