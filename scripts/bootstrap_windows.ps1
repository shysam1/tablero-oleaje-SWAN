<# Prepara un entorno local; reintenta instalaciones incompletas y no usa la red si esta listo. #>
$ErrorActionPreference = "Stop"
$proyecto = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $proyecto
$salidas = Join-Path $proyecto "salidas"
try { New-Item -ItemType Directory -Path $salidas -Force | Out-Null } catch {
    throw "Extrae o mueve la aplicacion a una carpeta con permiso de escritura del usuario. $($_.Exception.Message)"
}
$logFile = Join-Path $salidas "install.log"
function Log([string]$mensaje) {
    $linea = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $mensaje"
    Write-Host $linea
    Add-Content -LiteralPath $logFile -Value $linea -Encoding UTF8
}
function Fallar([string]$mensaje) { Log "ERROR: $mensaje"; exit 1 }
$venvPython = Join-Path $proyecto ".venv\Scripts\python.exe"
$estado = Join-Path $PSScriptRoot "estado_entorno.py"
$requisitos = Join-Path $proyecto "requirements.txt"
$marcador = Join-Path $proyecto ".venv\.tablero-listo.json"
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython $estado comprobar $requisitos $marcador
    if ($LASTEXITCODE -eq 0) { exit 0 }
}
Log "===== Preparando entorno de Tablero de Oleaje ====="
$validarPython = "import sys, struct; sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $pyCmd = $null
    $pyArgs = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -c $validarPython 2>$null
        if ($LASTEXITCODE -eq 0) { $pyCmd = "py"; $pyArgs = @("-3") }
    }
    if (-not $pyCmd -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c $validarPython 2>$null
        if ($LASTEXITCODE -eq 0) { $pyCmd = "python" }
    }
    if (-not $pyCmd) { Fallar "Instala Python 3.11 o superior de 64 bits desde python.org y agrega Python al PATH." }
    Log "Creando .venv con $pyCmd $($pyArgs -join ' ')"
    & $pyCmd @pyArgs -m venv (Join-Path $proyecto ".venv")
    if ($LASTEXITCODE -ne 0) { Fallar "No se pudo crear .venv. Mueve la aplicacion a una carpeta escribible." }
}
& $venvPython -c $validarPython
if ($LASTEXITCODE -ne 0) { Fallar "El .venv existente no funciona o usa Python incompatible. Renombra .venv y vuelve a abrir la aplicacion." }
Log "Instalando/verificando requirements.txt. La primera vez requiere internet."
$restricciones = Join-Path $proyecto "requirements-windows-py313.lock"
$argsPip = @("-m", "pip", "install", "--disable-pip-version-check", "-r", $requisitos)
$versionPython = & $venvPython -c "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))"
if ($versionPython -eq "3.13" -and (Test-Path -LiteralPath $restricciones)) {
    $argsPip += @("-c", $restricciones)
    Log "Usando versiones verificadas para Windows / Python 3.13."
}
# Windows PowerShell 5 convierte stderr nativo en registros de error; se evalua el codigo real de pip.
$ErrorActionPreference = "Continue"
& $venvPython @argsPip 2>&1 | ForEach-Object { Add-Content -LiteralPath $logFile -Value $_ -Encoding UTF8 }
$codigoPip = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($codigoPip -ne 0) { Fallar "Fallo pip. Revisa salidas\install.log; el proximo inicio reintentara la instalacion." }
& $venvPython $estado registrar $requisitos $marcador
if ($LASTEXITCODE -ne 0) { Fallar "Las dependencias se instalaron pero no se pudieron cargar. Revisa el mensaje anterior." }
Log "Entorno listo."
exit 0
