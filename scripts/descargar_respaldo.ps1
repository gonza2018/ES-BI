# Descarga un respaldo de gserelic.com a esta PC (Windows / PowerShell).
#
# Uso:        .\scripts\descargar_respaldo.ps1
# Requiere:   variable de entorno de usuario GSERELIC_RESPALDO_TOKEN con el mismo valor
#             que RESPALDO_TOKEN en Render. Crearla una sola vez con:
#             [Environment]::SetEnvironmentVariable("GSERELIC_RESPALDO_TOKEN", "<token>", "User")
# Programar:  Programador de tareas de Windows, semanal (ver README).

param(
    [string]$Destino = "$env:USERPROFILE\Documents\Respaldos_gserelic",
    [string]$Url = "https://www.gserelic.com/gestion/respaldo/",
    [int]$Conservar = 12
)

$ErrorActionPreference = "Stop"
$token = [Environment]::GetEnvironmentVariable("GSERELIC_RESPALDO_TOKEN", "User")
if (-not $token) { throw "Falta la variable de entorno GSERELIC_RESPALDO_TOKEN." }

New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$archivo = Join-Path $Destino ("respaldo_{0:yyyyMMdd_HHmmss}.tar.gz" -f (Get-Date))

Invoke-WebRequest -Uri $Url -Headers @{ Authorization = "Bearer $token" } -OutFile $archivo -UseBasicParsing
if ((Get-Item $archivo).Length -lt 1024) { throw "El respaldo descargado es demasiado chico: revisar el token." }
Write-Host "Respaldo guardado en $archivo"

# Conservar solo los más recientes
Get-ChildItem $Destino -Filter "respaldo_*.tar.gz" | Sort-Object Name -Descending |
    Select-Object -Skip $Conservar | Remove-Item
