$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$env:XDG_DATA_HOME = Join-Path $projectRoot "datos\https"
$env:XDG_CONFIG_HOME = Join-Path $projectRoot "datos\https-config"
$caddy = Join-Path $projectRoot "herramientas\caddy.exe"
if (-not (Test-Path -LiteralPath $caddy)) { throw "Falta herramientas\caddy.exe" }
& $caddy run --config (Join-Path $projectRoot "configuracion\Caddyfile") --adapter caddyfile
