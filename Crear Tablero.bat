@echo off
rem Regenera el acceso directo dentro de esta carpeta y lo abre.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0crear_acceso_directo.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "%~dp0Tablero de Oleaje.lnk"
