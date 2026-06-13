# run.ps1 — Démarrage du serveur Jarvis sous Windows PowerShell.
# Crée le venv si besoin, installe les dépendances, puis lance uvicorn.

param(
  [switch]$Reload,
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
  Write-Host "Création de l'environnement virtuel..." -ForegroundColor Cyan
  python -m venv .venv
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "Installation des dépendances..." -ForegroundColor Cyan
& $py -m pip install --quiet -r requirements.txt

$uvArgs = @("-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) { $uvArgs += "--reload" }

Write-Host "Jarvis sur http://localhost:$Port (Ctrl+C pour arrêter)" -ForegroundColor Green
& $py @uvArgs
