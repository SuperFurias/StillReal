@echo off
REM Setup portable env from scratch (no admin, no system Python). Run once after git clone.
REM Re-runnable: heals a half-initialized env instead of skipping it.
REM Bundles portable git (MinGit) and the uv package manager; installs prefer uv, pip is the fallback.
setlocal
cd /d "%~dp0"
set PYTHONNOUSERSITE=1
set PIP_NO_WARN_SCRIPT_LOCATION=1
set UV_VER=0.12.12
set MINGIT_TAG=v2.53.0.windows.1
set MINGIT_ASSET=MinGit-2.53.0-64-bit.zip
set ORT_DML_VER=1.24.4

REM --- 1. Bootstrap embeddable Python if missing -------------------------------
if not exist python-portable\python.exe (
  echo Downloading Python 3.12.10 embeddable...
  powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile 'py-embed.zip' -UseBasicParsing"
  if errorlevel 1 goto :fail_dl
  powershell -NoProfile -Command "Expand-Archive -LiteralPath 'py-embed.zip' -DestinationPath 'python-portable' -Force"
  if errorlevel 1 goto :fail_dl
  del py-embed.zip
)

REM --- 2. Always ensure site-packages are importable (idempotent) ---------------
powershell -NoProfile -Command "(Get-Content python-portable\python312._pth) -replace '#import site','import site' | Set-Content python-portable\python312._pth"
if errorlevel 1 goto :fail_pth

REM --- 3. Heal pip if the env was interrupted mid-bootstrap --------------------
python-portable\python.exe -m pip --version >nul 2>&1
if errorlevel 1 (
  echo pip missing - reinstalling via get-pip...
  powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'python-portable\get-pip.py' -UseBasicParsing"
  if errorlevel 1 goto :fail_pip
  python-portable\python.exe python-portable\get-pip.py --no-warn-script-location
  if errorlevel 1 goto :fail_pip
  del python-portable\get-pip.py
)

REM --- 4. Portable git, best effort (only needed for git+https deps) -----------
if not exist git-portable\cmd\git.exe (
  echo Downloading portable git...
  powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/%MINGIT_TAG%/%MINGIT_ASSET%' -OutFile 'mingit.zip' -UseBasicParsing"
  if errorlevel 1 (
    echo WARNING: portable git download failed - git-based deps will be skipped.
  ) else (
    powershell -NoProfile -Command "Expand-Archive -LiteralPath 'mingit.zip' -DestinationPath 'git-portable' -Force"
    if errorlevel 1 (
      echo WARNING: portable git extract failed - git-based deps will be skipped.
    )
    del mingit.zip >nul 2>&1
  )
)
if exist git-portable\cmd\git.exe set PATH=%~dp0git-portable\cmd;%PATH%

REM --- 5. uv package manager, best effort (falls back to pip) ------------------
if not exist tools\uv.exe (
  echo Downloading uv package manager...
  powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/download/%UV_VER%/uv-x86_64-pc-windows-msvc.zip' -OutFile 'uv.zip' -UseBasicParsing"
  if errorlevel 1 (
    echo WARNING: uv download failed - falling back to pip ^(slower^).
  ) else (
    powershell -NoProfile -Command "Expand-Archive -LiteralPath 'uv.zip' -DestinationPath 'tools' -Force"
    if errorlevel 1 (
      echo WARNING: uv extract failed - falling back to pip ^(slower^).
    )
    del uv.zip >nul 2>&1
  )
)
if exist tools\uv.exe (
  echo Using uv for package installs.
) else (
  echo Using pip for package installs.
)

REM --- 6. Core deps (fail fast - nothing works without these) ------------------
echo Installing core requirements...
call :dep_install -r requirements-portable.txt
if errorlevel 1 (
  echo.
  echo SETUP FAILED: install of requirements-portable.txt failed.
  echo Check your internet connection and re-run setup.bat.
  goto :fail
)

REM --- 7. Ensure the DirectML (GPU) onnxruntime build is the active one -------
REM onnxruntime and onnxruntime-directml share the same files; if a stale
REM stock build is shadowing the GPU build, DmlExecutionProvider is missing
REM and everything silently runs CPU-only. Keep in sync with requirements.
set ORTVER=missing
for /f "delims=" %%v in ('python-portable\python.exe -c "import onnxruntime; print(onnxruntime.__version__)" 2^>nul') do set ORTVER=%%v
if "%ORTVER%"=="%ORT_DML_VER%" goto :ort_ok
echo onnxruntime active build is %ORTVER% - restoring DirectML GPU build...
if exist tools\uv.exe (
  tools\uv.exe pip uninstall --python "%~dp0python-portable\python.exe" onnxruntime
  tools\uv.exe pip install --python "%~dp0python-portable\python.exe" --force-reinstall --no-deps onnxruntime-directml==1.24.4
) else (
  python-portable\python.exe -m pip uninstall -y onnxruntime
  python-portable\python.exe -m pip install --force-reinstall --no-deps --no-warn-script-location onnxruntime-directml==1.24.4
)
if errorlevel 1 goto :fail
:ort_ok

REM --- 8. Optional deps (warn and continue - app degrades gracefully) ----------
if exist requirements-optional.txt (
  echo Installing optional requirements ^(best effort^)...
  call :dep_install -r requirements-optional.txt
  if errorlevel 1 (
    echo.
    echo WARNING: optional requirements failed. Continuing - C2PA library checks will be skipped at runtime.
  )
)

REM --- 9. Model weights (fail fast - detector needs these) ---------------------
python-portable\python.exe download_models.py
if errorlevel 1 (
  echo.
  echo SETUP FAILED: model download failed. Check your connection and re-run setup.bat.
  goto :fail
)

REM --- 10. Verify everything actually imports ----------------------------------
echo Verifying install...
python-portable\python.exe -c "import gradio, onnxruntime, PIL, numpy, cv2, pandas, requests; print('deps ok:', onnxruntime.__version__, '| providers:', onnxruntime.get_available_providers())"
if errorlevel 1 (
  echo.
  echo SETUP FAILED: verification import failed. Re-run setup.bat; if it persists, delete python-portable\ and start over.
  goto :fail
)
python-portable\python.exe -c "import onnxruntime as o; p=o.get_available_providers(); print('GPU: ' + str([x for x in p if x != 'CPUExecutionProvider']) if len(p) > 1 else 'GPU: NONE detected - CPU will be used (needs a DirectX 12 GPU for DirectML)')"
if exist tools\uv.exe tools\uv.exe --version
if exist git-portable\cmd\git.exe git --version
if not exist model\model.onnx goto :fail_model
if not exist model\sieve-v014.onnx goto :fail_model
if not exist model\model_int8.onnx goto :fail_model

echo.
echo Setup done. Run ui.bat or run.bat photo.jpg
pause
exit /b 0

REM Install packages: uv when available, else pip. Usage: call :dep_install <args>
:dep_install
if exist tools\uv.exe (
  tools\uv.exe pip install --python "%~dp0python-portable\python.exe" %*
  exit /b %ERRORLEVEL%
)
python-portable\python.exe -m pip install --no-warn-script-location %*
exit /b %ERRORLEVEL%

:fail_dl
echo.
echo SETUP FAILED: could not download/extract embeddable Python. Check connection and re-run setup.bat.
pause
exit /b 1

:fail_pth
echo.
echo SETUP FAILED: could not patch python312._pth.
pause
exit /b 1

:fail_pip
echo.
echo SETUP FAILED: could not bootstrap pip. Check connection and re-run setup.bat.
pause
exit /b 1

:fail_model
echo.
echo SETUP FAILED: a model file is missing from model\ even though download reported success.
pause
exit /b 1

:fail
pause
exit /b 1
