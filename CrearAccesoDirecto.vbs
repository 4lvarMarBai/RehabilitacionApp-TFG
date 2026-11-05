Option Explicit
Dim fso, shell, root, script, result
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(root, "scripts\crear_accesos.ps1")
If Not fso.FileExists(script) Then
    MsgBox "No se encuentra scripts\crear_accesos.ps1.", vbCritical, "Rehabilitacion"
    WScript.Quit 1
End If
result = shell.Run("powershell -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & script & Chr(34), 0, True)
If result = 0 Then
    MsgBox "Se han creado los accesos Servidor, Detener servidor y Usuario en el escritorio.", vbInformation, "Rehabilitacion"
Else
    MsgBox "No se pudieron crear los accesos. Ejecuta scripts\crear_accesos.ps1 desde PowerShell para ver el error.", vbCritical, "Rehabilitacion"
End If
