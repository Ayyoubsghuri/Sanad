# Starts Sanad: runs the first-time setup when needed, starts the local backend and opens the app in the browser.
# Keep this window open while you use Sanad; closing it stops the app.
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Sanad'
$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $env:LOCALAPPDATA 'Sanad'
$Py = Join-Path $Runtime 'venv\Scripts\python.exe'
$Url = 'http://127.0.0.1:8765'

function Test-Backend {
    try { return (Invoke-WebRequest "$Url/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { return $false }
}

if (Test-Backend) { Start-Process $Url; exit 0 }   # already running: just open the app

if (-not (Test-Path (Join-Path $Runtime 'setup-done.txt')) -or -not (Test-Path $Py)) {
    & (Join-Path $App 'Setup-Sanad.ps1')
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

$release = Get-Content (Join-Path $App 'backend\pack_release.json') -Raw | ConvertFrom-Json
$env:LEGALRAG_LAWPACK_PUBLIC_KEY_HEX = $release.public_key_hex   # only a pack signed by the publisher is accepted
$env:LEGALRAG_FRONTEND_DIR = Join-Path $App 'frontend'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'

Write-Host 'Starting Sanad (the first start loads the models and can take a minute)...'
$backend = Start-Process -FilePath $Py -ArgumentList '-m', 'legalrag.main' -WorkingDirectory $Runtime -NoNewWindow -PassThru
$opened = $false
for ($i = 0; $i -lt 300 -and -not $backend.HasExited; $i++) {
    if (Test-Backend) { Start-Process $Url; $opened = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $opened) {
    Write-Host 'Sanad did not start. Read the messages above, or run "Sanad - repair setup" from the Start menu.' -ForegroundColor Red
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    Read-Host 'Press Enter to close'
    exit 1
}
Write-Host "Sanad is running at $Url  (close this window to stop it)" -ForegroundColor Green
Wait-Process -Id $backend.Id
