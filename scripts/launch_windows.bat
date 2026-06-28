@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

rem =============================================================================
rem Tablero de Oleaje - lanzador diario (Windows)
rem =============================================================================
rem Lo usa el acceso directo del Escritorio / menu Inicio creado por el
rem instalador. Si el entorno no existe, llama al bootstrap (primera vez).
rem =============================================================================

rem --- Raiz del proyecto = carpeta padre de \scripts ---
cd /d "%~dp0.."

set "VENV_PY=.venv\Scripts\python.exe"

rem --- Crear entorno la primera vez ---
if not exist "%VENV_PY%" (
  echo Preparando Tablero de Oleaje. Esto solo ocurre la primera vez...
  echo Necesitas conexion a internet.
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\bootstrap_windows.ps1"
  if errorlevel 1 (
    echo.
    echo ERROR durante la preparacion del entorno.
    echo Revisa  salidas\install.log
    echo y la guia  GUIAS DE USO\GUIA INSTALACION WINDOWS.txt
    echo.
    pause
    exit /b 1
  )
)

if not exist "%VENV_PY%" (
  echo.
  echo ERROR: no se encontro el entorno virtual tras la preparacion.
  echo Revisa  salidas\install.log
  echo.
  pause
  exit /b 1
)

echo Iniciando Tablero de Oleaje...
"%VENV_PY%" app_web.py --gui
if errorlevel 1 (
  echo.
  echo La aplicacion termino con error.
  echo Revisa  salidas\app_web.log  y  salidas\install.log
  echo.
  pause
)

endlocal
