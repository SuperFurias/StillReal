# Setup portable env from scratch (no admin, no system Python). Run once after git clone.
# Re-runnable: heals a half-initialized python-portable/ instead of skipping it.
# Run as:  powershell -ExecutionPolicy Bypass -File setup.ps1   (or .\setup.ps1 if policy allows)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$env:PYTHONNOUSERSITE = "1"
$env:PIP_NO_WARN_SCRIPT_LOCATION = "1"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

function Fail($msg) { Write-Host ""; Write-Host "SETUP FAILED: $msg" -ForegroundColor Red; exit 1 }

# --- 1. Bootstrap embeddable Python if missing ---
if (-not (Test-Path "$here\python-portable\python.exe")) {
  Write-Host "Downloading Python 3.12.10 embeddable..."
  try {
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip" -OutFile "$here\py-embed.zip" -UseBasicParsing
    Expand-Archive -LiteralPath "$here\py-embed.zip" -DestinationPath "$here\python-portable" -Force
    Remove-Item "$here\py-embed.zip"
  } catch { Fail "could not download/extract embeddable Python: $($_.Exception.Message)" }
}

# --- 2. Always ensure site-packages are importable (idempotent) ---
try {
  (Get-Content "$here\python-portable\python312._pth") -replace "#import site", "import site" | Set-Content "$here\python-portable\python312._pth"
} catch { Fail "could not patch python312._pth: $($_.Exception.Message)" }

# --- 3. Heal pip if the env was interrupted mid-bootstrap ---
& "$here\python-portable\python.exe" -m pip --version >$null 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "pip missing - reinstalling via get-pip..."
  try {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$here\python-portable\get-pip.py" -UseBasicParsing
  } catch { Fail "could not download get-pip.py: $($_.Exception.Message)" }
  & "$here\python-portable\python.exe" "$here\python-portable\get-pip.py" --no-warn-script-location
  if ($LASTEXITCODE -ne 0) { Fail "could not bootstrap pip." }
  Remove-Item "$here\python-portable\get-pip.py" -ErrorAction SilentlyContinue
}

# --- 4. Core deps (fail fast - nothing works without these) ---
Write-Host "Installing core requirements..."
& "$here\python-portable\python.exe" -m pip install --no-warn-script-location -r "$here\requirements-portable.txt"
if ($LASTEXITCODE -ne 0) { Fail "pip install of requirements-portable.txt failed. Check your internet connection and re-run." }

# --- 5. Optional deps (warn and continue - app degrades gracefully) ---
if (Test-Path "$here\requirements-optional.txt") {
  Write-Host "Installing optional requirements (best effort)..."
  & "$here\python-portable\python.exe" -m pip install --no-warn-script-location -r "$here\requirements-optional.txt"
  if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "WARNING: optional requirements failed (e.g. git missing for c2pacheck). Continuing - C2PA library checks will be skipped at runtime." -ForegroundColor Yellow
  }
}

# --- 6. Model weights (fail fast - detector needs these) ---
& "$here\python-portable\python.exe" "$here\download_models.py"
if ($LASTEXITCODE -ne 0) { Fail "model download failed. Check your connection and re-run." }

# --- 7. Verify everything actually imports ---
Write-Host "Verifying install..."
& "$here\python-portable\python.exe" -c "import gradio, onnxruntime, PIL, numpy, cv2, pandas, requests; print('deps ok:', onnxruntime.__version__, '| providers:', onnxruntime.get_available_providers())"
if ($LASTEXITCODE -ne 0) { Fail "verification import failed. Re-run; if it persists, delete python-portable\ and start over." }
foreach ($m in @("model\model.onnx", "model\sieve-v014.onnx", "model\model_int8.onnx")) {
  if (-not (Test-Path "$here\$m")) { Fail "model file missing after download: $m" }
}

Write-Host ""
Write-Host "Setup done. Run ui.bat or run.bat photo.jpg"
