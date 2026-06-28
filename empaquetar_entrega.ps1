# Empaqueta Tablero de Oleaje para entregar a un cliente (zip limpio).
# Uso: doble clic en empaquetar_entrega.bat  o  powershell -File empaquetar_entrega.ps1

$ErrorActionPreference = "Stop"

$proyecto = Split-Path -Parent $MyInvocation.MyCommand.Path
$fecha = Get-Date -Format "yyyy-MM-dd"
$nombreCarpeta = "Tablero Oleaje"
$nombreZip = "Tablero_Oleaje_entrega_$fecha.zip"
$dist = Join-Path $proyecto "dist"
$staging = Join-Path $dist "_staging_$fecha"
$zipPath = Join-Path $dist $nombreZip

if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
New-Item -ItemType Directory -Path $staging -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $staging $nombreCarpeta) -Force | Out-Null

$destino = Join-Path $staging $nombreCarpeta

Write-Host ""
Write-Host "Tablero de Oleaje - empaquetado para entrega"
Write-Host "============================================="
Write-Host "Origen:  $proyecto"
Write-Host "Salida:  $zipPath"
Write-Host ""

$carpetasIncluir = @(
  "ui",
  "assets",
  "scripts",
  "GUIAS DE USO"
)

foreach ($c in $carpetasIncluir) {
  $origen = Join-Path $proyecto $c
  if (-not (Test-Path $origen)) {
    Write-Warning "No se encontro la carpeta '$c'; se omite."
    continue
  }
  Write-Host "  + carpeta $c"
  robocopy $origen (Join-Path $destino $c) /E /NFL /NDL /NJH /NJS /NC /NS /NP `
    /XD "__pycache__" ".pytest_cache" | Out-Null
}

$archivosIncluir = @(
  "LEEME PRIMERO.txt",
  "requirements.txt",
  "iniciar_windows.bat",
  "iniciar_mac.command",
  "Crear Tablero.bat",
  "crear_acceso_directo.ps1",
  "app_web.py",
  "api_web.py",
  "motor_web.py",
  "sistema.py",
  "config.py",
  "rutas.py",
  "seguridad.py",
  "tablero_oleaje.py",
  "tablero_swan.py",
  "video_swan.py",
  "previews.py",
  "productos.py",
  "productos_swan.py",
  "productos_particion.py",
  "particion_espectral.py",
  "validacion.py",
  "io_oleaje.py",
  "io_era5.py",
  "io_swan.py",
  "io_swan_nonst.py",
  "io_batimetria.py",
  "geo_malla.py",
  "borde_oleaje.py",
  "swan_builder.py",
  "swan_runner.py",
  "prioridad.py",
  "app_tablero.py",
  "asistente.py",
  "estilo.py",
  "gui_swan.py",
  "pasos_analizar.py",
  "pasos_modelar.py",
  "pasos_ver.py"
)

foreach ($f in $archivosIncluir) {
  $origen = Join-Path $proyecto $f
  if (-not (Test-Path $origen)) {
    Write-Warning "No se encontro '$f'; se omite."
    continue
  }
  Copy-Item $origen (Join-Path $destino $f) -Force
}

Write-Host ""
Write-Host "Excluido a proposito:"
Write-Host "  .venv, salidas, __pycache__, tests, docs, .git, .cursor,"
Write-Host "  config.json, *.log, *.nc, accesos directos (.lnk), bitacora dev"
Write-Host ""

Write-Host "Comprimiendo..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
[System.IO.Compression.ZipFile]::CreateFromDirectory($staging, $zipPath)

Remove-Item $staging -Recurse -Force

$tamanoMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "Listo."
Write-Host "  Archivo: $zipPath"
Write-Host "  Tamano:  $tamanoMB MB"
Write-Host ""
Write-Host "Envia ese .zip al cliente. Dentro debe abrir LEEME PRIMERO.txt."
Write-Host ""

Start-Process explorer.exe (Split-Path $zipPath)
