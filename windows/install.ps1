# =============================================================================
#  Recalbox RFID Launcher - assistant d'installation Windows
#
#  Double-cliquez sur INSTALLER.cmd (dans le meme dossier) plutot que de lancer
#  ce script directement.
#
#  Ce script :
#    1. demande l'adresse de la Recalbox ;
#    2. copie le programme sur le partage \\RECALBOX\share ;
#    3. installe l'interface web d'installation (sans SSH) ;
#    4. propose d'installer tout de suite par SSH, sinon indique l'adresse a
#       ouvrir dans le navigateur.
# =============================================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Items = @("app", "userscript", "web-bootstrap", "docs", "tests",
           "install.sh", "uninstall.sh", "VERSION", "README.md", "CHANGELOG.md",
           "windows")

function Write-Info($message) { Write-Host "  $message" -ForegroundColor Gray }
function Write-Ok($message) { Write-Host "  OK  $message" -ForegroundColor Green }
function Write-Warn($message) { Write-Host "  ATTENTION  $message" -ForegroundColor Yellow }
function Write-Err($message) { Write-Host "  ERREUR  $message" -ForegroundColor Red }

function Normalize-LineEndings($Path) {
    # Recalbox execute les scripts avec /bin/sh : un fichier en CRLF casse tout.
    $text = [System.IO.File]::ReadAllText($Path)
    if ($text.Contains("`r`n")) {
        $normalized = $text -replace "`r`n", "`n"
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($Path, $normalized, $encoding)
    }
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Recalbox RFID Launcher - installation" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path (Join-Path $ProjectRoot "install.sh"))) {
    Write-Err "install.sh introuvable dans $ProjectRoot"
    Write-Info "Le dossier windows/ doit rester dans le dossier du projet."
    exit 1
}

$target = Read-Host "Adresse de la Recalbox (IP ou nom, vide = recalbox.local)"
if ([string]::IsNullOrWhiteSpace($target)) { $target = "recalbox.local" }

$share = "\\$target\share"
$webURL = "http://${target}:8080"

Write-Host ""
Write-Info "Verification du partage $share ..."
if (-not (Test-Path $share)) {
    Write-Err "Partage inaccessible : $share"
    Write-Host ""
    Write-Host " A verifier :" -ForegroundColor Yellow
    Write-Host "  - la Recalbox est allumee et connectee au reseau ;"
    Write-Host "  - le partage reseau est active (menu RESEAU > PARTAGE SMB > ON) ;"
    Write-Host "  - l'adresse saisie est correcte (voir RESEAU > INFORMATIONS)."
    Write-Host ""
    Read-Host "Appuyez sur Entree pour fermer"
    exit 1
}
Write-Ok "Partage accessible"

# --------------------------------------------------------------------------- #
# Copie du programme
# --------------------------------------------------------------------------- #
$destination = Join-Path $share "recalbox-rfid"
Write-Info "Copie du programme vers $destination ..."
if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
New-Item -ItemType Directory -Path $destination -Force | Out-Null
foreach ($item in $Items) {
    $source = Join-Path $ProjectRoot $item
    if (Test-Path $source) {
        Copy-Item $source $destination -Recurse -Force
    }
}
Write-Ok "Fichiers copies"

Write-Info "Normalisation des fins de ligne (LF) pour les scripts..."
$scripts = Get-ChildItem -Path $destination -Recurse -File -Include *.sh, *.py, *.py3 -ErrorAction SilentlyContinue
foreach ($script in $scripts) { Normalize-LineEndings $script.FullName }
Write-Ok "Scripts compatibles Recalbox"

# --------------------------------------------------------------------------- #
# Interface web d'installation (aucun SSH necessaire)
# --------------------------------------------------------------------------- #
$bootstrapName = "recalbox-rfid-web(permanent).py3"
$bootstrap = Join-Path $destination "web-bootstrap\$bootstrapName"
$userscripts = Join-Path $share "userscripts"
if (Test-Path $bootstrap) {
    New-Item -ItemType Directory -Path $userscripts -Force | Out-Null
    $installed = Join-Path $userscripts $bootstrapName
    Copy-Item $bootstrap $installed -Force
    Normalize-LineEndings $installed
    Write-Ok "Interface web installee (demarre avec Recalbox)"
} else {
    Write-Warn "web-bootstrap introuvable : l'installation par navigateur sera indisponible."
}

# --------------------------------------------------------------------------- #
# Installation immediate par SSH (facultatif)
# --------------------------------------------------------------------------- #
Write-Host ""
$answer = Read-Host "Installer tout de suite par SSH ? (O/n)"
$installNow = [string]::IsNullOrWhiteSpace($answer) -or ($answer -match '^[oOyY]')

if (-not $installNow) {
    Write-Host ""
    Write-Ok "Preparation terminee."
    Write-Host ""
    Write-Host " Prochaines etapes :" -ForegroundColor Cyan
    Write-Host "  1. Redemarrez Recalbox (menu QUITTER > REDEMARRER)."
    Write-Host "  2. Ouvrez $webURL dans un navigateur."
    Write-Host "  3. Cliquez sur « Installer maintenant », puis « Redemarrer Recalbox »."
    Write-Host ""
    Write-Host " (Rien d'autre a taper : tout se fait dans le navigateur.)"
    Write-Host ""
    Read-Host "Appuyez sur Entree pour fermer"
    exit 0
}

$ssh = Get-Command ssh -ErrorAction SilentlyContinue
if (-not $ssh) {
    Write-Warn "La commande 'ssh' est introuvable sur ce PC."
    Write-Host ""
    Write-Host " Utilisez plutot le navigateur :" -ForegroundColor Yellow
    Write-Host "  1. Redemarrez Recalbox."
    Write-Host "  2. Ouvrez $webURL puis cliquez sur « Installer maintenant »."
    Write-Host ""
    Write-Host " (Ou installez OpenSSH : Parametres > Applications >"
    Write-Host "  Fonctionnalites facultatives > Client OpenSSH.)"
    Write-Host ""
    Read-Host "Appuyez sur Entree pour fermer"
    exit 1
}

Write-Host ""
Write-Info "Installation sur la Recalbox (mot de passe par defaut : recalboxroot)"
Write-Host ""
& ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=NUL "root@$target" `
    "sh /recalbox/share/recalbox-rfid/install.sh --start"
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -ne 0) {
    Write-Err "L'installation par SSH a echoue (code $exitCode)."
    Write-Host ""
    Write-Host " Pas de panique : l'interface web reste disponible." -ForegroundColor Yellow
    Write-Host "  1. Redemarrez Recalbox."
    Write-Host "  2. Ouvrez $webURL puis cliquez sur « Installer maintenant »."
    Write-Host ""
    Write-Host " A verifier si vous retentez par SSH : serveur SSH active"
    Write-Host " (RESEAU > SERVEUR SSH > ON), mot de passe, version de Recalbox."
} else {
    Write-Ok "Installation terminee"
    Write-Host ""
    Write-Host " Prochaines etapes :" -ForegroundColor Cyan
    Write-Host "  1. Redemarrez Recalbox si l'installateur le demande (SPI)."
    Write-Host "  2. Ouvrez $webURL pour verifier le materiel et associer les badges."
    Write-Host "  3. Ou : ssh root@$target `"/recalbox/share/system/rfid/rfidctl test`""
    Write-Host ""
    Write-Host " Documentation : docs/INSTALLATION.md et docs/UTILISATION.md"
}

Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"
