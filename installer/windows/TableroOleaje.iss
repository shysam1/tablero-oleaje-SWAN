; =============================================================================
;  Tablero de Oleaje - Instalador Windows (Inno Setup 6)
; =============================================================================
;  Compilar con:  empaquetar_instalador.bat  (en la raiz del proyecto)
;  o abriendo este .iss en Inno Setup y pulsando "Compile".
;
;  Requiere Inno Setup 6:  https://jrsoftware.org/isinfo.php
;
;  NO empaqueta Python: el usuario debe tener Python 3.11+ en el PATH.
;  El entorno (.venv + dependencias) se crea en el primer arranque.
; =============================================================================

#define MyAppName "Tablero de Oleaje"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Tablero de Oleaje"
#define MyAppExeName "launch_windows.bat"

; Raiz del proyecto, relativa a este .iss (installer\windows\ -> ..\..)
#define SourceRoot "..\.."

[Setup]
AppId={{B3F7A2C1-9D4E-4F2A-8B6C-TABLEROOLEAJE01}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Tablero de Oleaje
DefaultGroupName=Tablero de Oleaje
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; El .exe se genera junto a este script, en  installer\windows
OutputDir=.
OutputBaseFilename=Tablero_Oleaje_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Sin firma de codigo: Windows SmartScreen puede mostrar advertencia (documentado en la guia).

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[Files]
; Copia todo el proyecto excepto entorno, salidas, tests, docs de desarrollo, etc.
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
  Excludes: "\.venv\*,\.venv,\.git\*,\.git,\.gitignore,\.cursor\*,\.cursor,\dist\*,\dist,\salidas\*,\salidas,\__pycache__\*,*\__pycache__\*,*.pyc,\.pytest_cache\*,\.pytest_cache,test_*.py,conftest.py,\docs\*,\docs,*.log,*.lnk,config.json,*.nc,*.mat,*.md,*.vbs,preview_mac.html,empaquetar_entrega.*,empaquetar_instalador.bat,\installer\*,\installer"

[Icons]
Name: "{group}\Tablero de Oleaje"; Filename: "{app}\scripts\launch_windows.bat"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 109; Comment: "Tablero de Oleaje (UI web)"
Name: "{group}\Guia de instalacion"; Filename: "{app}\GUIAS DE USO\GUIA INSTALACION WINDOWS.txt"
Name: "{group}\Desinstalar Tablero de Oleaje"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Tablero de Oleaje"; Filename: "{app}\scripts\launch_windows.bat"; WorkingDir: "{app}"; IconFilename: "{sys}\imageres.dll"; IconIndex: 109; Comment: "Tablero de Oleaje (UI web)"; Tasks: desktopicon

[Run]
Filename: "{app}\scripts\launch_windows.bat"; Description: "Abrir Tablero de Oleaje ahora"; Flags: postinstall shellexec nowait skipifsilent

[UninstallDelete]
; Limpiar solo el entorno generado dentro de {app}; respetar datos del usuario.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
{ Verifica que exista Python 3.11+ en PATH antes de instalar. }
function PythonOk(): Boolean;
var
  ResultCode: Integer;
  Encontrado: Boolean;
begin
  Encontrado := False;

  { Intento 1: el launcher oficial  py -3 }
  if Exec('cmd.exe',
          '/C py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
      Encontrado := True;
  end;

  { Intento 2: python en PATH }
  if not Encontrado then
  begin
    if Exec('cmd.exe',
            '/C python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"',
            '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      if ResultCode = 0 then
        Encontrado := True;
    end;
  end;

  Result := Encontrado;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not PythonOk() then
  begin
    if MsgBox(
      'Tablero de Oleaje necesita Python 3.11 o superior instalado y agregado al PATH.' + #13#10 + #13#10 +
      'No se detecto una version compatible.' + #13#10 + #13#10 +
      'Descarga Python desde https://www.python.org/downloads/ (marca "Add python.exe to PATH" durante la instalacion) y vuelve a ejecutar este instalador.' + #13#10 + #13#10 +
      'Tambien recuerda: la primera vez que abras la aplicacion necesitaras conexion a internet para descargar las librerias.' + #13#10 + #13#10 +
      'Deseas continuar de todas formas?',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
