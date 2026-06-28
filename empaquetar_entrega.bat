@echo off
rem Genera dist\Tablero_Oleaje_entrega_FECHA.zip listo para enviar al cliente.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0empaquetar_entrega.ps1"
if errorlevel 1 pause
