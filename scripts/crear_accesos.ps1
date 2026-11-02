$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$caddyConfig = Get-Content -LiteralPath (Join-Path $projectRoot "configuracion\Caddyfile") -Raw
$match = [regex]::Match($caddyConfig, 'https://(?!localhost)([a-zA-Z0-9.:-]+)')
if (-not $match.Success) { throw "No se encuentra la direccion de red en configuracion/Caddyfile." }
$url = $match.Value
$shell = New-Object -ComObject WScript.Shell
$desktop = $shell.SpecialFolders.Item("Desktop")
$shortcut = $shell.CreateShortcut((Join-Path $desktop "Rehabilitacion - Servidor.lnk"))
$shortcut.TargetPath = Join-Path $env:WINDIR "System32\wscript.exe"
$shortcut.Arguments = '"' + (Join-Path $projectRoot "IniciarServidor.vbs") + '"'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "Iniciar API, Streamlit y HTTPS"
$icon = Join-Path $projectRoot "recursos\RehabilitacionIcon.ico"
if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = $icon }
$shortcut.Save()
# El enlace de usuario contiene solo la URL, sin rutas privadas ni credenciales.
$linkText = "[InternetShortcut]`r`nURL=$url`r`n"
$encoding = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $desktop "Rehabilitacion - Usuario.url"), $linkText, $encoding)
[System.IO.File]::WriteAllText((Join-Path $projectRoot "recursos\Rehabilitacion - Usuario.url"), $linkText, $encoding)
Write-Output "Accesos creados en el escritorio. URL de usuarios: $url"
