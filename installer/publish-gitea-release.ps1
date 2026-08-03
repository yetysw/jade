# Publie la release Jade sur Gitea (installateur + archive modeles) via l'API.
#
# Prerequis IMPORTANT : la taille max des pieces jointes de Gitea (par defaut
# 4 Mo !) doit etre relevee, sinon l'upload du zip (1,9 Go) est refuse. Dans
# app.ini du serveur Gitea :
#     [attachment]
#     MAX_SIZE = 3000        ; en Mo
#     MAX_FILES = 10
# puis redemarrer Gitea. Si Gitea est derriere nginx : client_max_body_size 3g;
#
# Usage (PowerShell) :
#     .\installer\publish-gitea-release.ps1 -Token "<jeton_gitea>"
#
# Le jeton se cree dans Gitea : Parametres -> Applications -> Generer un jeton
# (droit "repo"). Ne le versionne pas.

param(
  [Parameter(Mandatory = $true)][string]$Token,
  [string]$GiteaUrl = "https://git.example.com",
  [string]$Owner    = "Jade",
  [string]$Repo     = "jade",
  # Vide = version courante lue dans ragagent/__init__.py (evite de publier une
  # release avec un numero fige et obsolete).
  [string]$Tag      = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $Tag) {
  $initPy = Join-Path $root "ragagent\__init__.py"
  $m = Select-String -Path $initPy -Pattern '__version__\s*=\s*"([^"]+)"'
  if (-not $m) { throw "Version introuvable dans $initPy — passer -Tag explicitement." }
  $Tag = "v" + $m.Matches[0].Groups[1].Value
  Write-Host "Version detectee : $Tag"
}
$ver  = $Tag.TrimStart('v')
$exeName = "Jade-Setup-$ver.exe"
$exe  = Join-Path $root "dist\installer\$exeName"
if (-not (Test-Path $exe)) { throw "Fichier manquant : $exe" }

$api = "$GiteaUrl/api/v1/repos/$Owner/$Repo"
$hdr = @{ Authorization = "token $Token" }
$notes = @"
Jade $Tag

Installation :
1. Telecharger et lancer $exeName
2. Renseigner les identifiants Jade demandes par l'assistant
Les modeles de recherche locaux sont telecharges automatiquement au premier lancement (connexion Internet requise).
Mises a jour ensuite automatiques (bouton dans l'app / tache planifiee sur RDS).
"@

# 1) creer la release (ou la recuperer si elle existe deja)
try {
  $body = @{ tag_name = $Tag; name = "Jade $Tag"; body = $notes; draft = $false; prerelease = $false } | ConvertTo-Json
  $rel = Invoke-RestMethod -Method Post -Uri "$api/releases" -Headers $hdr -ContentType "application/json" -Body $body
  Write-Host "Release creee (id $($rel.id))" -ForegroundColor Green
} catch {
  $rel = Invoke-RestMethod -Method Get -Uri "$api/releases/tags/$Tag" -Headers $hdr
  Write-Host "Release existante reutilisee (id $($rel.id))" -ForegroundColor Yellow
}

# 2) uploader les assets (curl.exe gere les gros fichiers, contrairement a
#    Invoke-RestMethod -Form sous Windows PowerShell 5.1)
function Publish-Asset($path, $name) {
  Write-Host "Upload de $name ..." -ForegroundColor Cyan
  curl.exe -sS -X POST "$api/releases/$($rel.id)/assets?name=$name" `
    -H "Authorization: token $Token" -F "attachment=@$path" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Echec de l'upload de $name" }
}
Publish-Asset $exe $exeName

Write-Host ""
Write-Host "Termine. Release : $GiteaUrl/$Owner/$Repo/releases/tag/$Tag" -ForegroundColor Green
Write-Host "Installateur : $GiteaUrl/$Owner/$Repo/releases/download/$Tag/$exeName"
