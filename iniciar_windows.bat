@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

rem =============================================================================
rem Tablero de Oleaje - lanzador (Windows)
rem =============================================================================
rem Compatibilidad: este archivo se mantiene para la entrega en .zip (doble clic).
rem Toda la logica vive ahora en scripts\launch_windows.bat (+ bootstrap), que es
rem lo que usa tambien el instalador .exe. Aqui solo delegamos.
rem
rem Requisito: Python 3.11+ y, para la ventana web, WebView2 Runtime (Edge).
rem Ver  GUIAS DE USO\GUIA INSTALACION WINDOWS.txt  si falta algo.
rem =============================================================================

cd /d "%~dp0"

if not exist "scripts\launch_windows.bat" (
  echo.
  echo ERROR: no se encontro  scripts\launch_windows.bat
  echo La carpeta del proyecto parece incompleta.
  echo.
  pause
  exit /b 1
)

call "scripts\launch_windows.bat"
exit /b %errorlevel%
