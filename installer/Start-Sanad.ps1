# Starts Sanad: runs the first-time setup when needed, starts the local backend and opens the app in the browser.
# Sanad opens in its own window (Edge or Chrome in app mode: title bar, no tabs, no address bar). Closing that window stops the app.
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Sanad'
$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $env:LOCALAPPDATA 'Sanad'
$Py = Join-Path $Runtime 'venv\Scripts\python.exe'
$Url = 'http://127.0.0.1:8765'

function Test-Backend {
    try { return (Invoke-WebRequest "$Url/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { return $false }
}

function Find-AppBrowser {
    $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA) | Where-Object { $_ }
    foreach ($rel in 'Microsoft\Edge\Application\msedge.exe', 'Google\Chrome\Application\chrome.exe') {
        foreach ($root in $roots) {
            $exe = Join-Path $root $rel
            if (Test-Path $exe) { return $exe }
        }
    }
    return $null
}

# Opens the app window and returns its process (or $null when only the default browser is available).
function Open-AppWindow {
    $browser = Find-AppBrowser
    if (-not $browser) { Start-Process $Url; return $null }
    $profileDir = Join-Path $Runtime 'window'   # its own profile: the window is a separate process we can wait for
    return Start-Process -FilePath $browser -PassThru -ArgumentList "--app=$Url", "--user-data-dir=`"$profileDir`"", '--no-first-run', '--no-default-browser-check', '--window-size=1360,860'
}

function Hide-Console {
    try {
        Add-Type -Namespace Sanad -Name Win -MemberDefinition '[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow(); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);'
        [Sanad.Win]::ShowWindow([Sanad.Win]::GetConsoleWindow(), 0) | Out-Null
    } catch { }
}

if (Test-Backend) { Open-AppWindow | Out-Null; exit 0 }   # already running: just open another window

if (-not (Test-Path (Join-Path $Runtime 'setup-done.txt')) -or -not (Test-Path $Py)) {
    & (Join-Path $App 'Setup-Sanad.ps1')
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

$release = Get-Content (Join-Path $App 'backend\pack_release.json') -Raw | ConvertFrom-Json
$env:LEGALRAG_LAWPACK_PUBLIC_KEY_HEX = $release.public_key_hex   # only a pack signed by the publisher is accepted
$env:LEGALRAG_FRONTEND_DIR = Join-Path $App 'frontend'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$Log = Join-Path $Runtime 'sanad.log'
$LogErr = Join-Path $Runtime 'sanad.err.log'

Write-Host 'Starting Sanad (the first start loads the models and can take a minute)...'
$backend = Start-Process -FilePath $Py -ArgumentList '-m', 'legalrag.main' -WorkingDirectory $Runtime -WindowStyle Hidden -PassThru -RedirectStandardOutput $Log -RedirectStandardError $LogErr
$up = $false
for ($i = 0; $i -lt 300 -and -not $backend.HasExited; $i++) {
    if (Test-Backend) { $up = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $up) {
    Write-Host 'Sanad did not start. Last messages:' -ForegroundColor Red
    Get-Content $LogErr -Tail 25 -ErrorAction SilentlyContinue
    Write-Host "Full log: $LogErr. You can also run 'Sanad - repair setup' from the Start menu."
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    Read-Host 'Press Enter to close'
    exit 1
}

$window = Open-AppWindow
if ($window) {
    Hide-Console
    Wait-Process -Id $window.Id            # the user closes the Sanad window ...
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }   # ... and the backend stops with it
} else {
    Write-Host "Sanad is running at $Url in your browser (close this window to stop it)" -ForegroundColor Green
    try { Wait-Process -Id $backend.Id } finally { if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force } }
}
