<#
.SYNOPSIS
    Mise à jour automatique de Jade sur serveur RDS (install partagée).

.DESCRIPTION
    Sur un serveur RDS, l'application est installée dans un dossier partagé
    (Program Files) sur lequel un utilisateur standard n'a pas les droits
    d'écriture — la mise à jour ne peut donc PAS se faire depuis une session
    utilisateur. Ce script, exécuté par une tâche planifiée sous le compte
    SYSTEM, la nuit, applique la mise à jour hors session :

      1. lit la version installée (registre de désinstallation Inno) ;
      2. interroge la dernière *release* Gitea ;
      3. si plus récente ET qu'aucun utilisateur n'est connecté, télécharge
         l'installateur et l'exécute en silencieux ;
      4. sinon, ne fait rien et réessaiera la nuit suivante.

    Côté application, mettre UPDATE_MODE=scheduled dans le .env pour masquer le
    bouton de mise à jour de l'interface (la MAJ passe uniquement par ce script).

.PARAMETER Register
    Crée/actualise la tâche planifiée (SYSTEM, tous les jours à 01:00) au lieu
    d'exécuter la vérification.

.PARAMETER Force
    Applique la mise à jour même si des sessions utilisateur sont ouvertes
    (déconseillé : ferme Jade chez les utilisateurs connectés).

.EXAMPLE
    # Installer la tâche planifiée (à lancer une fois, en administrateur) :
    powershell -ExecutionPolicy Bypass -File jade-update-task.ps1 -Register

.EXAMPLE
    # Vérifier/appliquer immédiatement (test manuel) :
    powershell -ExecutionPolicy Bypass -File jade-update-task.ps1
#>
[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$Force,
    [string]$ApiUrl = 'https://git.example.com',
    [string]$Repo   = 'example/jade',
    [string]$Token  = '',
    [string]$SetupPassword = '',
    [int]$Hour = 1,
    [int]$Minute = 0
)

$ErrorActionPreference = 'Stop'
$LogDir = Join-Path $env:ProgramData 'Jade\logs'
$LogFile = Join-Path $LogDir 'update.log'

function Write-Log {
    param([string]$Message)
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    $line = ('{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Host $line
}

# --- installation de la tâche planifiée --------------------------------------
if ($Register) {
    $script = $MyInvocation.MyCommand.Definition
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $script)
    $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($Hour).AddMinutes($Minute))
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName 'Jade - Mise a jour' -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    Write-Log ('Tâche planifiée installée (tous les jours à {0:00}:{1:00}, compte SYSTEM).' -f $Hour, $Minute)
    return
}

# --- version + emplacement installés (clé de désinstallation Inno Setup) ------
function Get-JadeInstall {
    $roots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        foreach ($key in Get-ChildItem $root) {
            $p = Get-ItemProperty $key.PSPath
            if ($p.DisplayName -like 'Jade*' -and $p.DisplayVersion) {
                return [pscustomobject]@{
                    Version  = [version]($p.DisplayVersion -replace '[^0-9.]', '')
                    Location = $p.InstallLocation
                }
            }
        }
    }
    return $null
}

# Mot de passe de l'installateur chiffré (lu dans le .env installé) pour que la
# mise à jour silencieuse puisse déchiffrer l'installateur.
function Get-SetupPassword {
    param([string]$InstallLocation)
    if ($SetupPassword) { return $SetupPassword }
    if (-not $InstallLocation) { return '' }
    $envFile = Join-Path $InstallLocation 'backend\.env'
    if (-not (Test-Path $envFile)) { return '' }
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*SETUP_PASSWORD\s*=\s*(.+)$') { return $Matches[1].Trim() }
    }
    return ''
}

# --- présence d'utilisateurs connectés ---------------------------------------
function Test-UsersLoggedOn {
    try {
        $out = & quser 2>$null
        # ligne d'en-tête + au moins une session = utilisateur présent
        return (($out | Measure-Object -Line).Lines -gt 1)
    } catch {
        return $false  # quser absent (pas un serveur RDS) : on considère libre
    }
}

try {
    $install = Get-JadeInstall
    if (-not $install) { Write-Log 'Version installée introuvable — abandon.'; return }
    $installed = $install.Version

    $headers = @{}
    if ($Token) { $headers['Authorization'] = "token $Token" }
    $rel = Invoke-RestMethod -Uri "$ApiUrl/api/v1/repos/$Repo/releases/latest" -Headers $headers -TimeoutSec 30
    $latest = [version](($rel.tag_name) -replace '[^0-9.]', '')
    $asset = $rel.assets | Where-Object { $_.name -like '*.exe' } | Select-Object -First 1

    Write-Log ('Installée : {0} · dernière : {1}' -f $installed, $latest)
    if (-not $asset) { Write-Log 'Aucun installateur .exe dans la release — abandon.'; return }
    if ($latest -le $installed) { Write-Log 'Déjà à jour.'; return }

    if ((Test-UsersLoggedOn) -and -not $Force) {
        Write-Log 'Utilisateur(s) connecté(s) : mise à jour reportée à la nuit prochaine.'
        return
    }

    $dest = Join-Path $env:TEMP $asset.name
    Write-Log ('Téléchargement de {0} …' -f $asset.name)
    Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $dest -TimeoutSec 600

    $args = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS')
    $pw = Get-SetupPassword -InstallLocation $install.Location
    if ($pw) { $args += "/PASSWORD=$pw" }  # installateur chiffré

    Write-Log 'Installation silencieuse…'
    $proc = Start-Process -FilePath $dest -ArgumentList $args -Wait -PassThru
    Write-Log ('Installateur terminé (code {0}). Mise à jour vers {1} appliquée.' -f $proc.ExitCode, $latest)
    Remove-Item $dest -Force -ErrorAction SilentlyContinue
} catch {
    Write-Log ('ERREUR : {0}' -f $_.Exception.Message)
}
