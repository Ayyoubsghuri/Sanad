# First-time setup of Sanad, with its own progress window (no console).  Safe to run again: it continues where it stopped.
#   1. a private Python 3.12 and the backend's packages          -> %LOCALAPPDATA%\Sanad
#   2. the signed law pack (about 2.3 GB) from Hugging Face      -> %USERPROFILE%\.moroccan-legal-rag\lawpack
#   3. the local models: reranker and the pack's embedding model -> %USERPROFILE%\.moroccan-legal-rag\models
#      (skipped when the user chooses search by meaning through Cloudflare Workers AI instead; forced below 16 GB of memory)
# About 7 GB are downloaded in total with the local models, about 2.5 GB without.  Everything the steps print is kept in %LOCALAPPDATA%\Sanad\setup.log.
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

# ---- before anything is downloaded: local models or Cloudflare (search by meaning) -------------------------------------
# The local models need 16 GB of memory. Below that, Sanad uses Cloudflare Workers AI for search by meaning (the same bge-m3
# model as the law pack's vectors) and the models are not installed. At 16 GB or more the user chooses. The choice is kept in
# compute.json (read by the app) and can be changed later with "Sanad - repair setup".
$Choice = Join-Path $Runtime 'compute.json'
$ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$lowRam = $ramGb -lt 15   # a "16 GB" computer reports a little less than 16
$previous = $null
if (Test-Path $Choice) { try { $previous = (Get-Content $Choice -Raw | ConvertFrom-Json).embeddings } catch { } }

$ask = New-Object System.Windows.Forms.Form
$ask.Text = 'Sanad - setup'
$ask.ClientSize = New-Object System.Drawing.Size(560, 440)
$ask.StartPosition = 'CenterScreen'
$ask.FormBorderStyle = 'FixedDialog'
$ask.MaximizeBox = $false
$ask.MinimizeBox = $false
$ask.BackColor = [System.Drawing.Color]::FromArgb(244, 243, 240)
$ask.Font = New-Object System.Drawing.Font('Segoe UI', 9.5)
if (Test-Path (Join-Path $App 'app.ico')) { $ask.Icon = New-Object System.Drawing.Icon((Join-Path $App 'app.ico')) }
function Add-AskLabel($text, $x, $y, $w, $h, $font, $color) {
    $l = New-Object System.Windows.Forms.Label
    $l.Text = $text; $l.Location = New-Object System.Drawing.Point($x, $y); $l.Size = New-Object System.Drawing.Size($w, $h)
    if ($font) { $l.Font = $font }
    if ($color) { $l.ForeColor = $color }
    $ask.Controls.Add($l); return $l
}
$greyA = [System.Drawing.Color]::FromArgb(105, 105, 105)
$bold = New-Object System.Drawing.Font('Segoe UI Semibold', 10)
$null = Add-AskLabel 'How should Sanad search by meaning?' 24 18 512 30 (New-Object System.Drawing.Font('Segoe UI Semibold', 14)) $null
$ramText = if ($lowRam) { "This computer has $ramGb GB of memory. The local models need 16 GB, so Sanad will use Cloudflare." } else { "This computer has $ramGb GB of memory: both options work." }
$null = Add-AskLabel $ramText 24 52 512 22 $null $greyA

$api = New-Object System.Windows.Forms.RadioButton
$api.Text = 'Use the Cloudflare Workers AI API' + $(if ($lowRam) { '  (recommended)' } else { '' })
$api.Font = $bold; $api.Location = New-Object System.Drawing.Point(24, 86); $api.Size = New-Object System.Drawing.Size(512, 24)
$ask.Controls.Add($api)
$null = Add-AskLabel "No big models to install: about 2.5 GB to download instead of 7 GB, and light on memory. You need a free Cloudflare account: after the setup, enter its account ID and an API token in Sanad (API keys). The masked search text is sent to Cloudflare; in Offline mode Sanad searches by keywords only." 44 112 492 72 $null $greyA
$small = New-Object System.Windows.Forms.CheckBox
$small.Text = 'Also install a small model that sorts the results by meaning (about 1 GB, works offline)'
$small.Location = New-Object System.Drawing.Point(44, 186); $small.Size = New-Object System.Drawing.Size(492, 22)
$small.Checked = $true
$ask.Controls.Add($small)

$local = New-Object System.Windows.Forms.RadioButton
$local.Text = 'Install the models on this computer' + $(if ($lowRam) { "  (needs 16 GB of memory)" } else { '' })
$local.Font = $bold; $local.Location = New-Object System.Drawing.Point(24, 226); $local.Size = New-Object System.Drawing.Size(512, 24)
$local.Enabled = -not $lowRam
$ask.Controls.Add($local)
$null = Add-AskLabel "Everything runs on this computer, also in Offline mode, and no account is needed. About 7 GB to download; uses a lot of memory while searching." 44 252 492 44 $null $greyA

if ($lowRam -or $previous -eq 'cloudflare') { $api.Checked = $true } else { $local.Checked = $true }
$small.Enabled = $api.Checked
$api.Add_CheckedChanged({ $small.Enabled = $api.Checked })

$ok = New-Object System.Windows.Forms.Button
$ok.Text = 'Continue'; $ok.Location = New-Object System.Drawing.Point(436, 388); $ok.Size = New-Object System.Drawing.Size(100, 32)
$ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
$ask.Controls.Add($ok); $ask.AcceptButton = $ok
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'; $cancel.Location = New-Object System.Drawing.Point(326, 388); $cancel.Size = New-Object System.Drawing.Size(100, 32)
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$ask.Controls.Add($cancel); $ask.CancelButton = $cancel
$answer = $ask.ShowDialog()
$ask.Dispose()
if ($answer -ne [System.Windows.Forms.DialogResult]::OK) { exit 1 }
$UseApi = $lowRam -or $api.Checked
$SmallReranker = $UseApi -and $small.Checked
$embeddings = if ($UseApi) { 'cloudflare' } else { 'local' }
@{ embeddings = $embeddings; small_reranker = [bool]$SmallReranker; ram_gb = $ramGb; chosen_at = (Get-Date -Format s) } | ConvertTo-Json | Set-Content -Path $Choice -Encoding UTF8
Add-Content -Path $Log -Value "memory $ramGb GB; search by meaning: $embeddings"
$extras = if ($UseApi -and -not $SmallReranker) { 'desktop' } else { 'local-models,desktop' }
$downloadText = if ($UseApi -and $SmallReranker) { 'The application, the law pack and a small model are downloaded once (about 3.5 GB). This can take from 15 minutes to a few hours. You can keep using your computer.' } elseif ($UseApi) { 'The application and the law pack are downloaded once (about 2.5 GB). This can take from 10 minutes to an hour. You can keep using your computer.' } else { 'The law pack and the local models are downloaded once (about 7 GB). This can take from 15 minutes to a few hours. You can keep using your computer.' }

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
$null = New-Label $downloadText 60 54 $null $grey
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
Invoke-Step 1 'Python and the application packages' $Uv "pip install --python `"$Py`" `"$Backend[$extras]`"" $Runtime
Invoke-Step 2 'the law pack (signed, checked before it is installed)' $Py 'tools\install_pack.py --release pack_release.json' $Backend
if (-not $UseApi) {
    Invoke-Step 3 'the local models (reranker and embedding model)' $Py '-m legalrag.fetch_models --pack-embedder' $Runtime
} elseif ($SmallReranker) {
    Invoke-Step 3 'the small model that sorts the results' $Py '-m legalrag.fetch_models --small-reranker' $Runtime
}

Set-Content -Path $Done -Value (Get-Date -Format s)
$form.Dispose()
exit 0
