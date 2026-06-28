@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

rem =============================================================================
rem Tablero de Oleaje — lanzador automatico para Windows
rem =============================================================================
rem Uso: doble clic en este archivo (o en el acceso directo "Tablero de Oleaje.lnk")
rem
rem El script:
rem   1. Se coloca en la carpeta del proyecto.
rem   2. Busca Python 3.11 o superior.
rem   3. Crea un entorno virtual (.venv) si aun no existe.
rem   4. Instala o actualiza dependencias desde requirements.txt.
rem   5. Arranca la aplicacion (app_web.py --gui).
rem
rem Requisito: Python 3.11+ y, para la ventana web, WebView2 Runtime (Edge).
rem Ver GUIAS DE USO\GUIA DE USO WINDOWS.txt si falta algo.
rem =============================================================================

cd /d "%~dp0"

set "PY="
set "PY_ARGS="

rem Preferir el launcher oficial de Python en Windows (py -3)
where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%V in ('py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "PY_VER=%%V"
  if defined PY_VER (
    set "PY=py"
    set "PY_ARGS=-3"
    goto :tiene_python
  )
)

where python >nul 2>&1
if not errorlevel 1 (
  set "PY=python"
  set "PY_ARGS="
  goto :tiene_python
)

echo.
echo ERROR: No se encontro Python 3.
echo.
echo Instala Python 3.11 o superior desde:
echo   https://www.python.org/downloads/
echo.
echo En el instalador, marca "Add python.exe to PATH".
echo Luego vuelve a ejecutar este archivo.
echo.
pause
exit /b 1

:tiene_python
for /f "delims=" %%M in ('%PY% %PY_ARGS% -c "import sys; print(sys.version_info.major)" 2^>nul') do set "PY_MAJOR=%%M"
for /f "delims=" %%N in ('%PY% %PY_ARGS% -c "import sys; print(sys.version_info.minor)" 2^>nul') do set "PY_MINOR=%%N"
if not defined PY_MAJOR goto :version_mala
if %PY_MAJOR% LSS 3 goto :version_mala
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 11 goto :version_mala
goto :version_ok

:version_mala
echo.
echo ERROR: Se requiere Python 3.11 o superior.
for /f "delims=" %%V in ('%PY% %PY_ARGS% --version 2^>nul') do echo Detectado: %%V
echo.
pause
exit /b 1

:version_ok
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual en .venv ...
  %PY% %PY_ARGS% -m venv .venv
  if errorlevel 1 (
    echo No se pudo crear el entorno virtual.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo No se pudo activar el entorno virtual.
  pause
  exit /b 1
)

echo Verificando dependencias (puede tardar la primera vez)...
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt -q
if errorlevel 1 (
  echo.
  echo ERROR al instalar dependencias. Revisa GUIAS DE USO\GUIA DE USO WINDOWS.txt
  echo o ejecuta manualmente: pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo Iniciando Tablero de Oleaje...
python app_web.py --gui
if errorlevel 1 (
  echo.
  echo La aplicacion termino con error. Revisa salidas\app_web.log
  echo.
  pause
)

endlocal
