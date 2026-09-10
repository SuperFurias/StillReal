@echo off
REM StillReal - no system Python needed. Just double-click or: run.bat photo.jpg
setlocal
set PYTHONNOUSERSITE=1
set PYTHONPATH=%~dp0python-portable\Lib\site-packages
"%~dp0python-portable\python.exe" "%~dp0detect.py" %*
