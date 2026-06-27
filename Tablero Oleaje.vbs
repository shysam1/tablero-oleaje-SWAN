' Lanza el Tablero de Oleaje sin ventana de consola.
Dim sh, fso, dir, app, python
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
app = dir & "\app_web.py"
sh.CurrentDirectory = dir

' pythonw.exe cierra app_web.py al instante (exit 1) con pywebview en este PC;
' python.exe funciona. WindowStyle 0 oculta la consola.
python = "C:\Users\123ja\AppData\Local\Programs\Python\Python313\python.exe"
If Not fso.FileExists(python) Then
  python = "python"
End If

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
