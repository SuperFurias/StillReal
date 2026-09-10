@echo off
REM Setup portable env from scratch (no admin, no system Python). Run once after git clone.
setlocal
cd /d "%~dp0"
if not exist python-portable\python.exe (
  echo Downloading Python 3.12.10 embeddable...
  powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile 'py-embed.zip'"
  powershell -Command "Expand-Archive -LiteralPath 'py-embed.zip' -DestinationPath 'python-portable' -Force"
  del py-embed.zip
  powershell -Command "(Get-Content python-portable\python312._pth) -replace '#import site','import site' | Set-Content python-portable\python312._pth"
  powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'python-portable\get-pip.py'"
  python-portable\python.exe python-portable\get-pip.py --no-warn-script-location
  del python-portable\get-pip.py
)
set PYTHONNOUSERSITE=1
python-portable\python.exe -m pip install --no-warn-script-location -r requirements-portable.txt
python-portable\python.exe download_models.py
echo Setup done. Run ui.bat or run.bat photo.jpg
pause
