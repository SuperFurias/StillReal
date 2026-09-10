# Setup portable env from scratch (no admin, no system Python). Run once after git clone.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
if (-not (Test-Path "$here\python-portable\python.exe")) {
  Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip" -OutFile "$here\py-embed.zip"
  Expand-Archive -LiteralPath "$here\py-embed.zip" -DestinationPath "$here\python-portable" -Force
  Remove-Item "$here\py-embed.zip"
  (Get-Content "$here\python-portable\python312._pth") -replace "#import site", "import site" | Set-Content "$here\python-portable\python312._pth"
  Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$here\python-portable\get-pip.py"
  & "$here\python-portable\python.exe" "$here\python-portable\get-pip.py" --no-warn-script-location
  Remove-Item "$here\python-portable\get-pip.py"
}
$env:PYTHONNOUSERSITE = "1"
& "$here\python-portable\python.exe" -m pip install --no-warn-script-location -r "$here\requirements-portable.txt"
& "$here\python-portable\python.exe" "$here\download_models.py"
Write-Host "Setup done. Run ui.bat or run.bat photo.jpg"
