<#
=============================================================================
 Tablero de Oleaje - bootstrap (Windows)
=============================================================================
 Logica unica de preparacion del entorno. Lo usan tanto el instalador
 (primer arranque desde Archivos de programa) como el lanzador clasico.

 Responsabilidades:
   1. Situarse en la raiz del proyecto (carpeta padre de \scripts).
   2. Localizar Python 3.11+ (py -3, luego python).
   3. Crear .venv si no existe.
   4. Instalar/actualizar dependencias de requirements.txt.
   5. Registrar todo en salidas\install.log.

 Devuelve codigo 0 si el entorno quedo listo; distinto de 0 si fallo.
=============================================================================
#>

$ErrorActionPreference = "Stop"

# --- Raiz del proyecto: carpeta padre de este script ---
$proyecto = Split-Path -Parent $PSScriptRoot
Set-Location $proyecto

# --- Preparar log ---
function Test-Escribible {
    param([string]$dir)
    try {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $probe = Join-Path $dir ".test_escritura"
        [System.IO.File]::WriteAllText($probe, "")
        Remove-Item $probe -Force
        return $true
    } catch {
        return $false
    }
}

if (Test-Escribible $proyecto) {
    $salidas = Join-Path $proyecto "salidas"
    if (-not (Test-Path $salidas)) {
        New-Item -ItemType Directory -Path $salidas -Force | Out-Null
    }
    $logFile = Join-Path $salidas "install.log"
} else {
    $datos = Join-Path $env:LOCALAPPDATA "Tablero de Oleaje"
    if (-not (Test-Path $datos)) {
        New-Item -ItemType Directory -Path $datos -Force | Out-Null
    }
    $logFile = Join-Path $datos "install.log"
}

function Log {
    param([string]$msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $linea = "[$ts] $msg"
    Write-Host $linea
    Add-Content -Path $logFile -Value $linea -Encoding UTF8
}

function Fallar {
    param([string]$msg)
    Log "ERROR: $msg"
    exit 1
}

Log "===== Preparando entorno de Tablero de Oleaje ====="
Log "Proyecto: $proyecto"

# --- Localizar Python 3.11+ ---
$pyCmd = $null
$pyArgs = @()

$tienePy = Get-Command py -ErrorAction SilentlyContinue
if ($tienePy) {
    $ver = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ver) {
        $pyCmd = "py"
        $pyArgs = @("-3")
    }
}

if (-not $pyCmd) {
    $tienePython = Get-Command python -ErrorAction SilentlyContinue
    if ($tienePython) {
        $pyCmd = "python"
        $pyArgs = @()
    }
}

if (-not $pyCmd) {
    Log "No se encontro Python 3."
    Log "Instala Python 3.11 o superior desde https://www.python.org/downloads/"
    Log "En el instalador marca 'Add python.exe to PATH'."
    Fallar "Python no disponible en PATH."
}

# --- Verificar version minima (3.11) ---
$major = & $pyCmd @pyArgs -c "import sys; print(sys.version_info.major)" 2>$null
$minor = & $pyCmd @pyArgs -c "import sys; print(sys.version_info.minor)" 2>$null
$verCompleta = & $pyCmd @pyArgs --version 2>$null
Log "Python detectado: $verCompleta (via '$pyCmd $($pyArgs -join ' ')')"

if (-not $major) { Fallar "No se pudo determinar la version de Python." }
if ([int]$major -lt 3 -or ([int]$major -eq 3 -and [int]$minor -lt 11)) {
    Fallar "Se requiere Python 3.11 o superior (detectado: $verCompleta)."
}

# --- Crear entorno virtual si no existe ---
$venvPython = Join-Path $proyecto ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Log "Creando entorno virtual en .venv ..."
    & $pyCmd @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Fallar "No se pudo crear el entorno virtual (.venv)."
    }
} else {
    Log "Entorno virtual ya existe (.venv)."
}

# --- Instalar dependencias ---
Log "Actualizando pip..."
& $venvPython -m pip install --upgrade pip -q 2>&1 | ForEach-Object { Add-Content -Path $logFile -Value $_ -Encoding UTF8 }

Log "Instalando dependencias (requirements.txt). Puede tardar la primera vez..."
& $venvPython -m pip install -r requirements.txt 2>&1 | ForEach-Object { Add-Content -Path $logFile -Value $_ -Encoding UTF8 }
if ($LASTEXITCODE -ne 0) {
    Log "Fallo la instalacion de dependencias."
    Log "Consulta 'GUIAS DE USO\GUIA INSTALACION WINDOWS.txt' (seccion Problemas)."
    Fallar "pip install -r requirements.txt termino con error."
}

Log "Entorno listo."
exit 0
