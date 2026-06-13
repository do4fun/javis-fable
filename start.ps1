# start.ps1 — Démarrage en un clic de Jarvis sous Windows (F5.3).
# Délègue au script Python multiplateforme.
param([switch]$NoBrowser, [int]$Port = 8000)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$args = @("scripts/start.py", "--port", "$Port")
if ($NoBrowser) { $args += "--no-browser" }

python @args
