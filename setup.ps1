# Setup portable env from scratch (no admin, no system Python). Run once after git clone.
# Re-runnable: heals a half-initialized env instead of skipping it.
# Bundles portable git (MinGit) and the uv package manager; installs prefer uv, pip is the fallback.
# Run as:  powershell -ExecutionPolicy Bypass -File setup.ps1   (or .\setup.ps1 if policy allows)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$env:PYTHONNOUSERSITE = "1"
$env:PIP_NO_WARN_SCRIPT_LOCATION = "1"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$UV_VER = "0.12.12"
$MINGIT_TAG = "v2.53.0.windows.1"
$MINGIT_ASSET = "MinGit-2.53.0-64-bit.zip"
$ortWant = "1.24.4"  # keep in sync with requirements-portable.txt

$pyExe = "$here\python-portable\python.exe"
$uvExe = "$here\tools\uv.exe"
$gitExe = "$here\git-portable\cmd\git.exe"

function Fail($msg) { Write-Host ""; Write-Host "SETUP FAILED: $msg" -ForegroundColor Red; exit 1 }

# Install packages: uv when available, else pip. Returns the install exit code.
function DepInstall([string[]]$a) {
  if (Test-Path $uvExe) { & $uvExe pip install --python $pyExe @a }
  else { & $pyExe -m pip install --no-warn-script-location @a }
  return $LASTEXITCODE
}

# --- 1. Bootstrap embeddable Python if missing ---
if (-not (Test-Path $pyExe)) {
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
& $pyExe -m pip --version >$null 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "pip missing - reinstalling via get-pip..."
  try {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$here\python-portable\get-pip.py" -UseBasicParsing
  } catch { Fail "could not download get-pip.py: $($_.Exception.Message)" }
  & $pyExe "$here\python-portable\get-pip.py" --no-warn-script-location
  if ($LASTEXITCODE -ne 0) { Fail "could not bootstrap pip." }
  Remove-Item "$here\python-portable\get-pip.py" -ErrorAction SilentlyContinue
}

# --- 4. Portable git, best effort (only needed for git+https deps) ---
if (-not (Test-Path $gitExe)) {
  Write-Host "Downloading portable git..."
  try {
    Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/download/$MINGIT_TAG/$MINGIT_ASSET" -OutFile "$here\mingit.zip" -UseBasicParsing
    Expand-Archive -LiteralPath "$here\mingit.zip" -DestinationPath "$here\git-portable" -Force
    Remove-Item "$here\mingit.zip" -ErrorAction SilentlyContinue
  } catch {
    Write-Host "WARNING: portable git download/extract failed - git-based deps will be skipped." -ForegroundColor Yellow
  }
}
if (Test-Path $gitExe) { $env:PATH = "$here\git-portable\cmd;$env:PATH" }

# --- 5. uv package manager, best effort (falls back to pip) ---
if (-not (Test-Path $uvExe)) {
  Write-Host "Downloading uv package manager..."
  try {
    Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/download/$UV_VER/uv-x86_64-pc-windows-msvc.zip" -OutFile "$here\uv.zip" -UseBasicParsing
    Expand-Archive -LiteralPath "$here\uv.zip" -DestinationPath "$here\tools" -Force
    Remove-Item "$here\uv.zip" -ErrorAction SilentlyContinue
  } catch {
    Write-Host "WARNING: uv download/extract failed - falling back to pip (slower)." -ForegroundColor Yellow
  }
}
if (Test-Path $uvExe) { Write-Host "Using uv for package installs." }
else { Write-Host "Using pip for package installs." }

# --- 6. Core deps (fail fast - nothing works without these) ---
Write-Host "Installing core requirements..."
if ((DepInstall @("-r", "$here\requirements-portable.txt")) -ne 0) { Fail "install of requirements-portable.txt failed. Check your internet connection and re-run." }

# --- 7. Ensure the DirectML (GPU) onnxruntime build is the active one ---
# onnxruntime and onnxruntime-directml share the same files; if a stale
# stock build is shadowing the GPU build, DmlExecutionProvider is missing
# and everything silently runs CPU-only.
$ortVer = & $pyExe -c "import onnxruntime; print(onnxruntime.__version__)" 2>$null
if ($ortVer -ne $ortWant) {
  Write-Host "onnxruntime active build is $ortVer - restoring DirectML GPU build..."
  if (Test-Path $uvExe) {
    & $uvExe pip uninstall --python $pyExe onnxruntime
    & $uvExe pip install --python $pyExe --force-reinstall --no-deps onnxruntime-directml==1.24.4
  } else {
    & $pyExe -m pip uninstall -y onnxruntime
    & $pyExe -m pip install --force-reinstall --no-deps --no-warn-script-location onnxruntime-directml==1.24.4
  }
  if ($LASTEXITCODE -ne 0) { Fail "could not restore the DirectML GPU build." }
}

# --- 8. Optional deps (warn and continue - app degrades gracefully) ---
if (Test-Path "$here\requirements-optional.txt") {
  Write-Host "Installing optional requirements (best effort)..."
  if ((DepInstall @("-r", "$here\requirements-optional.txt")) -ne 0) {
    Write-Host ""
    Write-Host "WARNING: optional requirements failed. Continuing - C2PA library checks will be skipped at runtime." -ForegroundColor Yellow
  }
}

# --- 9. Model weights (fail fast - detector needs these) ---
& $pyExe "$here\download_models.py"
if ($LASTEXITCODE -ne 0) { Fail "model download failed. Check your connection and re-run." }

# --- 10. Verify everything actually imports ---
Write-Host "Verifying install..."
& $pyExe -c "import gradio, onnxruntime, PIL, numpy, cv2, pandas, requests; print('deps ok:', onnxruntime.__version__, '| providers:', onnxruntime.get_available_providers())"
if ($LASTEXITCODE -ne 0) { Fail "verification import failed. Re-run; if it persists, delete python-portable\ and start over." }
& $pyExe -c "import onnxruntime as o; p=o.get_available_providers(); print('GPU: ' + str([x for x in p if x != 'CPUExecutionProvider']) if len(p) > 1 else 'GPU: NONE detected - CPU will be used (needs a DirectX 12 GPU for DirectML)')"
if (Test-Path $uvExe) { & $uvExe --version }
if (Test-Path $gitExe) { & $gitExe --version }
foreach ($m in @("model\model.onnx", "model\sieve-v014.onnx", "model\model_int8.onnx")) {
  if (-not (Test-Path "$here\$m")) { Fail "model file missing after download: $m" }
}

Write-Host ""
Write-Host "Setup done. Run ui.bat or run.bat photo.jpg"
