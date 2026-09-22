@echo off
setlocal EnableExtensions
rem Genera dist\Tablero_Oleaje_entrega_FECHA.zip listo para enviar al cliente.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0empaquetar_entrega.ps1"
set "CODIGO=%errorlevel%"
if not "%CODIGO%"=="0" pause
exit /b %CODIGO%
