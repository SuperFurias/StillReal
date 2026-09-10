@echo off
REM Setup portable env from scratch (no admin, no system Python). Run once after git clone.
REM Re-runnable: heals a half-initialized python-portable/ instead of skipping it.
setlocal
cd /d "%~dp0"
set PYTHONNOUSERSITE=1
set PIP_NO_WARN_SCRIPT_LOCATION=1

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

REM --- 4. Core deps (fail fast - nothing works without these) ------------------
echo Installing core requirements...
python-portable\python.exe -m pip install --no-warn-script-location -r requirements-portable.txt
if errorlevel 1 (
  echo.
  echo SETUP FAILED: pip install of requirements-portable.txt failed.
  echo Check your internet connection and re-run setup.bat.
  goto :fail
)

REM --- 5. Optional deps (warn and continue - app degrades gracefully) ----------
if exist requirements-optional.txt (
  echo Installing optional requirements ^(best effort^)...
  python-portable\python.exe -m pip install --no-warn-script-location -r requirements-optional.txt
  if errorlevel 1 (
    echo.
    echo WARNING: optional requirements failed ^(e.g. git missing for c2pacheck^). Continuing - C2PA library checks will be skipped at runtime.
  )
)

REM --- 6. Model weights (fail fast - detector needs these) ---------------------
python-portable\python.exe download_models.py
if errorlevel 1 (
  echo.
  echo SETUP FAILED: model download failed. Check your connection and re-run setup.bat.
  goto :fail
)

REM --- 7. Verify everything actually imports -----------------------------------
echo Verifying install...
python-portable\python.exe -c "import gradio, onnxruntime, PIL, numpy, cv2, pandas, requests; print('deps ok:', onnxruntime.__version__, '| providers:', onnxruntime.get_available_providers())"
if errorlevel 1 (
  echo.
  echo SETUP FAILED: verification import failed. Re-run setup.bat; if it persists, delete python-portable\ and start over.
  goto :fail
)
if not exist model\model.onnx goto :fail_model
if not exist model\sieve-v014.onnx goto :fail_model
if not exist model\model_int8.onnx goto :fail_model

echo.
echo Setup done. Run ui.bat or run.bat photo.jpg
pause
exit /b 0

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
