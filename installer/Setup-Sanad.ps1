# First-time setup of Sanad, with its own progress window (no console).  Safe to run again: it continues where it stopped.
#   1. a private Python 3.12 and the backend's packages          -> %LOCALAPPDATA%\Sanad
#   2. the signed law pack (about 2.3 GB) from Hugging Face      -> %USERPROFILE%\.moroccan-legal-rag\lawpack
#   3. the local models: reranker and the pack's embedding model -> %USERPROFILE%\.moroccan-legal-rag\models
# About 7 GB are downloaded in total.  Everything the steps print is kept in %LOCALAPPDATA%\Sanad\setup.log.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $env:LOCALAPPDATA 'Sanad'
$Venv = Join-Path $Runtime 'venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
$Uv = Join-Path $App 'bin\uv.exe'
$Backend = Join-Path $App 'backend'
$Done = Join-Path $Runtime 'setup-done.txt'
$Log = Join-Path $Runtime 'setup.log'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Runtime 'python'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'
$env:HF_HUB_DISABLE_PROGRESS_BARS = '1'

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
Remove-Item $Done -ErrorAction SilentlyContinue
Set-Content -Path $Log -Value "Sanad setup $(Get-Date -Format s)"

# ---- the window ------------------------------------------------------------------------------------------------------
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Sanad - setup'
$form.ClientSize = New-Object System.Drawing.Size(520, 250)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(244, 243, 240)
$form.Font = New-Object System.Drawing.Font('Segoe UI', 9.5)
$ico = Join-Path $App 'app.ico'
if (Test-Path $ico) { $form.Icon = New-Object System.Drawing.Icon($ico) }

function New-Label($text, $y, $height, $font, $color) {
    $l = New-Object System.Windows.Forms.Label
    $l.Text = $text
    $l.Location = New-Object System.Drawing.Point(28, $y)
    $l.Size = New-Object System.Drawing.Size(464, $height)
    if ($font) { $l.Font = $font }
    if ($color) { $l.ForeColor = $color }
    $form.Controls.Add($l)
    return $l
}
$grey = [System.Drawing.Color]::FromArgb(105, 105, 105)
$null = New-Label 'Setting up Sanad' 22 34 (New-Object System.Drawing.Font('Segoe UI Semibold', 15)) $null
$null = New-Label 'The law pack and the local models are downloaded once (about 7 GB). This can take from 15 minutes to a few hours. You can keep using your computer.' 60 54 $null $grey
$stepLabel = New-Label 'Preparing...' 124 22 (New-Object System.Drawing.Font('Segoe UI Semibold', 9.5)) $null
$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(28, 150)
$bar.Size = New-Object System.Drawing.Size(464, 14)
$bar.Style = 'Marquee'
$bar.MarqueeAnimationSpeed = 30
$form.Controls.Add($bar)
$detail = New-Label '' 172 40 (New-Object System.Drawing.Font('Segoe UI', 8.5)) $grey
$script:cancelled = $false
$script:child = $null
$form.Add_FormClosing({ $script:cancelled = $true })
$form.Show()
[System.Windows.Forms.Application]::DoEvents()

function Stop-Child {
    if ($script:child -and -not $script:child.HasExited) {
        Start-Process -FilePath "$env:WINDIR\System32\taskkill.exe" -ArgumentList "/PID $($script:child.Id) /T /F" -WindowStyle Hidden -Wait
    }
}

function Fail($message) {
    Stop-Child
    if (-not $script:cancelled) {
        [System.Windows.Forms.MessageBox]::Show($form, "$message`n`nCheck the internet connection and start Sanad again: the setup continues where it stopped.`n`nDetails: $Log", 'Sanad - setup', 'OK', 'Error') | Out-Null
    }
    $form.Dispose()
    exit 1
}

function Get-LastLine($path) {
    try {
        $tail = Get-Content -Path $path -Tail 1 -ErrorAction Stop
        if (-not $tail) { return '' }
        $parts = ([string]$tail) -split "`r" | Where-Object { $_.Trim() }
        $line = if ($parts) { ([string]@($parts)[-1]).Trim() } else { '' }
        if ($line.Length -gt 150) { $line = $line.Substring(0, 150) + '...' }
        return $line
    } catch { return '' }
}

# Runs one command without any window; its output goes to its own log, the last line is shown under the progress bar.
function Invoke-Step($number, $title, $exe, $arguments, $workdir) {
    $stepLabel.Text = "Step $number of 3: $title"
    $detail.Text = ''
    $stepLog = Join-Path $Runtime "setup-step$number.log"
    Set-Content -Path $stepLog -Value ''
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "$env:WINDIR\System32\cmd.exe"
    $psi.Arguments = "/d /s /c `"`"$exe`" $arguments > `"$stepLog`" 2>&1`""
    $psi.WorkingDirectory = $workdir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $script:child = [System.Diagnostics.Process]::Start($psi)
    $ticks = 0
    while (-not $script:child.HasExited) {
        [System.Windows.Forms.Application]::DoEvents()
        if ($script:cancelled) { Fail 'cancelled' }
        Start-Sleep -Milliseconds 100
        $ticks++
        if ($ticks % 10 -eq 0) { $detail.Text = Get-LastLine $stepLog }
    }
    $code = $script:child.ExitCode
    Add-Content -Path $Log -Value "`n===== step $number : $title (exit $code)"
    Get-Content -Path $stepLog -ErrorAction SilentlyContinue | Add-Content -Path $Log
    Remove-Item $stepLog -ErrorAction SilentlyContinue
    if ($code -ne 0) { Fail "Step $number did not finish: $title." }
}

Invoke-Step 1 'Python and the application packages' $Uv "venv --python 3.12 --allow-existing `"$Venv`"" $Runtime
Invoke-Step 1 'Python and the application packages' $Uv "pip install --python `"$Py`" `"$Backend[local-models,desktop]`"" $Runtime
Invoke-Step 2 'the law pack (signed, checked before it is installed)' $Py 'tools\install_pack.py --release pack_release.json' $Backend
Invoke-Step 3 'the local models (reranker and embedding model)' $Py '-m legalrag.fetch_models --pack-embedder' $Runtime

Set-Content -Path $Done -Value (Get-Date -Format s)
$form.Dispose()
exit 0
