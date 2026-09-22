@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0.."
rem El bootstrap comprueba un marcador validado y no usa la red si el entorno esta listo.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\bootstrap_windows.ps1"
if errorlevel 1 (
  echo.
  echo ERROR durante la preparacion. Revisa salidas\install.log
  echo y GUIAS DE USO\GUIA INSTALACION WINDOWS.txt
  pause
  exit /b 1
)
echo Iniciando Tablero de Oleaje...
".venv\Scripts\python.exe" app_web.py --gui
set "CODIGO=%errorlevel%"
if not "%CODIGO%"=="0" (
  echo.
  echo La aplicacion termino con error. Revisa salidas\app_web.log
  pause
)
exit /b %CODIGO%
