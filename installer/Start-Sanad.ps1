# Run hidden by Sanad.exe when the first-time setup is needed (or for "Sanad - repair setup"): shows the setup window,
# then starts the application.  Once the setup is done, Sanad.exe starts the application directly and this script is not used.
param([switch]$Repair)
$ErrorActionPreference = 'Stop'
$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $env:LOCALAPPDATA 'Sanad'
$Pyw = Join-Path $Runtime 'venv\Scripts\pythonw.exe'

if ($Repair -or -not (Test-Path (Join-Path $Runtime 'setup-done.txt')) -or -not (Test-Path $Pyw)) {
    & (Join-Path $App 'Setup-Sanad.ps1')
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
Start-Process -FilePath $Pyw -ArgumentList "-m legalrag.desktop --app-dir `"$App`"" -WorkingDirectory $Runtime
exit 0
