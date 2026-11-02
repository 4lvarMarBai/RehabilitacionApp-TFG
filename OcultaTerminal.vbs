Option Explicit

Dim fso, shell, root, batPath, pythonPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = fso.BuildPath(root, "Ruta.bat")
pythonPath = fso.BuildPath(root, ".venv\Scripts\python.exe")

If Not fso.FileExists(batPath) Then
    MsgBox "No se encuentra Ruta.bat junto a este archivo.", vbCritical, "RehabilitacionApp"
    WScript.Quit 1
End If



If Not fso.FileExists(pythonPath) Then
    MsgBox "Primera ejecución: se creará el entorno virtual y se instalarán las dependencias. Necesitarás Python e Internet.", vbInformation, "RehabilitacionApp"
End If

shell.CurrentDirectory = root
shell.Run Chr(34) & batPath & Chr(34), 0, False
