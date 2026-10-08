$ErrorActionPreference = "Stop"

& "$PSScriptRoot\.venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm SenaCertificacionDemo.spec
Write-Host "Demo creada en dist\SenaCertificacionDemo\SenaCertificacionDemo.exe"
