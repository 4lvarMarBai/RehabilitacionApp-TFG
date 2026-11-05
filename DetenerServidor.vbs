Option Explicit
Dim fso, shell, root, python, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
python = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
If Not fso.FileExists(python) Then
    MsgBox "No se encuentra el entorno Python del proyecto.", vbCritical, "Rehabilitacion"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
command = Chr(34) & python & Chr(34) & " -m scripts.detener_servidor"
shell.Run command, 0, False
