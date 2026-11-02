$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$cert = Join-Path $projectRoot "datos\https\caddy\pki\authorities\local\root.crt"
if (-not (Test-Path -LiteralPath $cert)) { throw "Inicia HTTPS primero para generar el certificado." }
$dest = Join-Path $projectRoot "recursos\certificado_https_local.crt"
Copy-Item -LiteralPath $cert -Destination $dest -Force
Get-FileHash -LiteralPath $dest -Algorithm SHA256
Write-Output "Comparte solo este certificado publico con los equipos autorizados. Nunca compartas root.key ni la carpeta datos/https."
