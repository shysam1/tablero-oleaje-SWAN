@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

rem =============================================================================
rem Tablero de Oleaje - compila el instalador .exe (Inno Setup 6)
rem =============================================================================
rem Requiere Inno Setup 6 instalado. Genera:
rem   installer\windows\Tablero_Oleaje_Setup_1.0.1.exe
rem =============================================================================

cd /d "%~dp0"

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  where ISCC >nul 2>&1
  if not errorlevel 1 set "ISCC=ISCC"
)

if not defined ISCC (
  echo.
  echo ERROR: No se encontro el compilador de Inno Setup (ISCC.exe).
  echo Instala Inno Setup 6 desde:
  echo   https://jrsoftware.org/isinfo.php
  echo.
  pause
  exit /b 1
)

echo Compilando instalador con Inno Setup...
where py >nul 2>&1
if errorlevel 1 (
  python scripts\empaquetar.py --inno installer\windows\archivos_entrega.iss
) else (
  py -3 scripts\empaquetar.py --inno installer\windows\archivos_entrega.iss
)
if errorlevel 1 (
  echo No se pudo validar el contenido de la entrega.
  pause
  exit /b 1
)
"%ISCC%" "installer\windows\TableroOleaje.iss"
if errorlevel 1 (
  echo.
  echo ERROR al compilar el instalador.
  echo.
  pause
  exit /b 1
)

echo.
echo Listo. Instalador generado en:
echo   installer\windows\Tablero_Oleaje_Setup_1.0.1.exe
echo.
if exist "installer\windows" start "" explorer.exe "installer\windows"
endlocal
