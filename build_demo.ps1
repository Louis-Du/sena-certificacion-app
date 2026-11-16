param(
    [string]$Version = "",
    [switch]$RequireInstaller
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

# Seleccionar un interprete Python 3.12 (compatible con las ruedas compiladas).
function Get-Python312 {
    foreach ($candidate in @("py -3.12", "python3.12", "python")) {
        try {
            $version = & cmd /c "$candidate --version 2>&1"
            if ($version -match "Python 3\.12") { return $candidate }
        } catch { }
    }
    return $null
}

$PythonLauncher = Get-Python312
if (-not $PythonLauncher) {
    throw "No se encontro Python 3.12. Instale Python 3.12 (https://www.python.org/downloads/) y vuelva a intentar."
}

# Recrear el entorno virtual si no existe o no es 3.12.
$needVenv = $true
if (Test-Path $VenvPython) {
    $venvVersion = & $VenvPython --version 2>&1
    if ($venvVersion -match "Python 3\.12") { $needVenv = $false }
}
if ($needVenv) {
    Write-Host "Creando entorno virtual con Python 3.12..."
    if (Test-Path (Join-Path $Root ".venv")) { Remove-Item -Recurse -Force (Join-Path $Root ".venv") }
    & cmd /c "$PythonLauncher -m venv `"$Root\.venv`""
    if ($LASTEXITCODE -ne 0) { throw "No fue posible crear el entorno virtual." }
}

$Python = $VenvPython

$ErrorActionPreference = "Continue"
& $Python -c "import PyInstaller, pystray" 2>$null | Out-Null
$depsMissing = ($LASTEXITCODE -ne 0)
$ErrorActionPreference = "Stop"
if ($depsMissing) {
    Write-Host "Instalando dependencias..."
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "La instalacion de dependencias fallo." }
}

if (-not $Version) {
    $Version = (& $Python -c "from app.version import APP_VERSION; print(APP_VERSION)").Trim()
}
if (-not $Version) { throw "No se pudo determinar la version de la aplicacion." }
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version invalida: '$Version'. Se espera el formato X.Y.Z."
}

# Cerrar instancias en ejecucion que bloquean archivos.
Get-Process -Name "SENACertificacion" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# Limpieza de builds anteriores.
foreach ($relative in @("build\SENACertificacion", "dist\SENACertificacion")) {
    $path = Join-Path $Root $relative
    if (Test-Path $path) {
        try { Remove-Item -Recurse -Force $path } catch { }
    }
}

$Spec = Get-ChildItem -Path $Root -Filter "*.spec" -File | Select-Object -First 1
if (-not $Spec) { throw "No se encontro el archivo .spec del proyecto." }

Write-Host "Compilando $Version con $($Spec.Name) ..."
& $Python -m PyInstaller --clean --noconfirm $Spec.FullName
if ($LASTEXITCODE -ne 0) { throw "La compilacion con PyInstaller fallo." }

$DistDir = Join-Path $Root "dist\SENACertificacion"
$Exe = Join-Path $DistDir "SENACertificacion.exe"
if (-not (Test-Path $Exe)) { throw "No se genero el ejecutable esperado: $Exe" }

Set-Content -Path (Join-Path $DistDir "version.txt") -Value $Version -Encoding UTF8

# Prueba de arranque (sin abrir la ventana).
$SmokeData = Join-Path $env:TEMP "sena-certificacion-smoke-data"
if (Test-Path $SmokeData) { Remove-Item -Recurse -Force $SmokeData }
$env:SENA_SMOKE_TEST = "1"
$env:SENA_DATA_DIR = $SmokeData
try {
    $proc = Start-Process -FilePath $Exe -PassThru
    if (-not $proc.WaitForExit(120000)) {
        try { $proc.Kill(); $proc.WaitForExit(10000) | Out-Null } catch { }
        throw "La prueba de arranque del .exe excedio 120 segundos."
    }
    if ($proc.ExitCode -ne 0) { throw "La prueba de arranque del .exe fallo (codigo $($proc.ExitCode))." }
} finally {
    Remove-Item Env:SENA_SMOKE_TEST -ErrorAction SilentlyContinue
    Remove-Item Env:SENA_DATA_DIR -ErrorAction SilentlyContinue
    if (Test-Path $SmokeData) { Remove-Item -Recurse -Force $SmokeData }
}

# Generar instalador si Inno Setup esta disponible.
$iscc = $null
$cmd = Get-Command iscc -ErrorAction SilentlyContinue
if ($cmd) { $iscc = $cmd.Source }
if (-not $iscc) {
    foreach ($p in @("C:\Program Files (x86)\Inno Setup 6\ISCC.exe", "C:\Program Files\Inno Setup 6\ISCC.exe", "C:\Program Files (x86)\Inno Setup 7\ISCC.exe", "C:\Program Files\Inno Setup 7\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $p) { $iscc = $p; break }
    }
}
if ($iscc) {
    Get-Process -Name "SENACertificacion" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    Write-Host "Generando instalador con Inno Setup..."
    & $iscc "/DMyAppVersion=$Version" (Join-Path $Root "installer\SENACertificacion.iss")
    if ($LASTEXITCODE -ne 0) { throw "La generacion del instalador fallo." }
    $Installer = Join-Path $Root "dist\installer\SENACertificacion-Setup-$Version.exe"
    if (-not (Test-Path $Installer)) { throw "No se genero el instalador esperado: $Installer" }
    Write-Host "  Instalador: $Installer"
} else {
    Write-Host "Inno Setup no encontrado. El script .iss esta en installer\SENACertificacion.iss."
    Write-Host "  Descargue Inno Setup 6 (https://jrsoftware.org/isdl.php) para generar el instalador."
    if ($RequireInstaller) { throw "Inno Setup no encontrado y se requiere generar el instalador." }
}

Write-Host ""
Write-Host "Build completado:"
Write-Host "  Ejecutable: $Exe"
Write-Host "  Version:    $Version"
Write-Host "  Datos:      se crean en <carpeta del .exe>\data al ejecutarlo."