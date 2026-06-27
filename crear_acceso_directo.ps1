# Crea/reemplaza el acceso directo DENTRO de la carpeta del proyecto.
$ErrorActionPreference = "Stop"

$proyecto = Split-Path -Parent $MyInvocation.MyCommand.Path
$lnk = Join-Path $proyecto "Tablero de Oleaje.lnk"
$app = Join-Path $proyecto "app_web.py"

if (-not (Test-Path $app)) {
  Write-Error "No se encontró la UI web: $app"
}

$python = $null
foreach ($candidato in @(
  (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
  "C:\Users\123ja\AppData\Local\Programs\Python\Python313\python.exe"
)) {
  if ($candidato -and (Test-Path $candidato)) { $python = $candidato; break }
}
if (-not $python) {
  Write-Error "No se encontró python.exe"
}

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnk)
$sc.TargetPath = $python
$sc.Arguments = "`"$app`" --gui"
$sc.WorkingDirectory = $proyecto
$sc.WindowStyle = 1
$sc.Description = "Tablero de Oleaje (UI web)"
$sc.IconLocation = "$python,0"
$sc.Save()

$escritorio = [Environment]::GetFolderPath("Desktop")
$lnkEscritorio = Join-Path $escritorio "Tablero de Oleaje.lnk"
if (Test-Path $lnkEscritorio) {
  Remove-Item $lnkEscritorio -Force
  Write-Host "Eliminado acceso directo del Escritorio: $lnkEscritorio"
}

Write-Host "Acceso directo creado:"
Write-Host "  $lnk"
