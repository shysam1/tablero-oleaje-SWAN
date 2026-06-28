# Crea/reemplaza el acceso directo DENTRO de la carpeta del proyecto.
$ErrorActionPreference = "Stop"

$proyecto = Split-Path -Parent $MyInvocation.MyCommand.Path
$lnk = Join-Path $proyecto "Tablero de Oleaje.lnk"
$launcher = Join-Path $proyecto "iniciar_windows.bat"

if (-not (Test-Path $launcher)) {
  Write-Error "No se encontró el lanzador: $launcher"
}

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnk)
$sc.TargetPath = $launcher
$sc.WorkingDirectory = $proyecto
$sc.WindowStyle = 1
$sc.Description = "Tablero de Oleaje (UI web)"
$sc.IconLocation = "$env:SystemRoot\System32\imageres.dll,109"
$sc.Save()

$escritorio = [Environment]::GetFolderPath("Desktop")
$lnkEscritorio = Join-Path $escritorio "Tablero de Oleaje.lnk"
if (Test-Path $lnkEscritorio) {
  Remove-Item $lnkEscritorio -Force
  Write-Host "Eliminado acceso directo del Escritorio: $lnkEscritorio"
}

Write-Host "Acceso directo creado:"
Write-Host "  $lnk"
Write-Host "Apunta a: iniciar_windows.bat (venv + dependencias automaticas)"
