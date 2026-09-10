@echo off
REM StillReal portable UI - no system Python needed
setlocal
set PYTHONNOUSERSITE=1
set PYTHONPATH=%~dp0python-portable\Lib\site-packages
set GRADIO_SERVER_NAME=127.0.0.1
set GRADIO_SERVER_PORT=7860
"%~dp0python-portable\python.exe" "%~dp0app.py" %*
pause
