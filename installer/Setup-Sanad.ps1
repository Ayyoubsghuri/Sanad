# First-time setup of Sanad (run automatically on the first start; safe to run again, it continues where it stopped).
#   1. a private Python 3.12 and the backend's packages          -> %LOCALAPPDATA%\Sanad
#   2. the signed law pack (about 2.3 GB) from Hugging Face      -> %USERPROFILE%\.moroccan-legal-rag\lawpack
#   3. the local models: reranker and the pack's embedding model -> %USERPROFILE%\.moroccan-legal-rag\models
# About 7 GB are downloaded in total. Nothing is sent anywhere.
$ErrorActionPreference = 'Stop'
$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $env:LOCALAPPDATA 'Sanad'
$Venv = Join-Path $Runtime 'venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
$Uv = Join-Path $App 'bin\uv.exe'
$Done = Join-Path $Runtime 'setup-done.txt'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Runtime 'python'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'

function Fail($message) {
    Write-Host ''
    Write-Host "SETUP STOPPED: $message" -ForegroundColor Red
    Write-Host 'Check the internet connection and start Sanad again: the setup continues where it stopped.'
    Read-Host 'Press Enter to close'
    exit 1
}

function Step($n, $title) { Write-Host ''; Write-Host "[$n/3] $title" -ForegroundColor Cyan }

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
Remove-Item $Done -ErrorAction SilentlyContinue
Write-Host 'Sanad - first-time setup. About 7 GB will be downloaded (Python packages, the law pack, the models).'
Write-Host 'This can take from 15 minutes to a few hours depending on the connection. Leave this window open.'

Step 1 'Python and the backend packages'
& $Uv venv --python 3.12 --allow-existing $Venv
if ($LASTEXITCODE -ne 0) { Fail 'could not create the Python environment' }
& $Uv pip install --python $Py "$(Join-Path $App 'backend')[local-models]"
if ($LASTEXITCODE -ne 0) { Fail 'could not install the Python packages' }

Step 2 'The law pack (signed; checked before it is installed)'
Push-Location (Join-Path $App 'backend')
try { & $Py 'tools\install_pack.py' --release 'pack_release.json' } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { Fail 'the law pack was not installed' }

Step 3 'The local models (reranker and embedding model)'
& $Py -m legalrag.fetch_models --pack-embedder
if ($LASTEXITCODE -ne 0) { Fail 'the models were not downloaded' }

Set-Content -Path $Done -Value (Get-Date -Format s)
Write-Host ''
Write-Host 'Setup finished.' -ForegroundColor Green
exit 0
