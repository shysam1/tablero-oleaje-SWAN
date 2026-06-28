' Lanza el Tablero de Oleaje sin ventana de consola.
Dim sh, fso, dir, app, python
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
app = dir & "\app_web.py"
sh.CurrentDirectory = dir

' pythonw.exe puede fallar con pywebview; python.exe + WindowStyle 0 oculta la consola.
python = "python"

On Error Resume Next
sh.Run """" & python & """ """ & app & """", 0, False
If Err.Number <> 0 Then
  Err.Clear
  sh.Run "python """ & app & """", 0, False
End If
If Err.Number <> 0 Then
  MsgBox "No se pudo iniciar el Tablero de Oleaje." & vbCrLf & vbCrLf & _
         "Comprueba que Python esté instalado y que pywebview esté disponible:" & vbCrLf & _
         "pip install pywebview", vbCritical, "Tablero de Oleaje"
End If
On Error GoTo 0
