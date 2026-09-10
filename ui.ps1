# StillReal portable UI - no system Python needed
$env:PYTHONNOUSERSITE = "1"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$here\python-portable\python.exe" "$here\app.py" @args
