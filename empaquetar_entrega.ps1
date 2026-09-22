# Empaqueta exclusivamente el manifiesto scripts/archivos_entrega.txt.
param([switch]$NoAbrir)
$ErrorActionPreference = "Stop"
$proyecto = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $proyecto
$zipPath = Join-Path $proyecto ("dist\Tablero_Oleaje_entrega_" + (Get-Date -Format "yyyy-MM-dd_HHmmss") + ".zip")
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 scripts/empaquetar.py --zip $zipPath
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python scripts/empaquetar.py --zip $zipPath
} else { throw "Se requiere Python 3.11 o superior para empaquetar." }
if ($LASTEXITCODE -ne 0) { throw "No se genero una entrega completa; revisa el error anterior." }
Write-Host "Entrega creada: $zipPath"
if (-not $NoAbrir) { Start-Process explorer.exe -ArgumentList ('"' + (Split-Path -Parent $zipPath) + '"') }
