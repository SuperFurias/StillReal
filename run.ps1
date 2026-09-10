# StillReal - no system Python needed
# Usage: .\run.ps1 photo.jpg  |  .\run.ps1 .\photos\
$env:PYTHONNOUSERSITE = "1"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$here\python-portable\python.exe" "$here\detect.py" @args
