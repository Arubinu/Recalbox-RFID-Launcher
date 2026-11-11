# =============================================================================
#  Recalbox RFID Launcher - assistant d'installation Windows
#
#  Double-cliquez sur INSTALLER.cmd (dans le meme dossier) plutot que de lancer
#  ce script directement.
#
#  Ce script :
#    1. demande l'adresse de la Recalbox ;
#    2. copie le programme sur le partage \\RECALBOX\share ;
#    3. lance l'installation par SSH (mot de passe par defaut : recalboxroot).
# =============================================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Items = @("app", "userscript", "docs", "tests", "install.sh", "uninstall.sh",
           "VERSION", "README.md", "CHANGELOG.md", "windows")

function Write-Info($message) { Write-Host "  $message" -ForegroundColor Gray }
function Write-Ok($message) { Write-Host "  OK  $message" -ForegroundColor Green }
function Write-Warn($message) { Write-Host "  ATTENTION  $message" -ForegroundColor Yellow }
function Write-Err($message) { Write-Host "  ERREUR  $message" -ForegroundColor Red }

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

function Normalize-LineEndings($Path) {
    # Recalbox execute les scripts avec /bin/sh : un fichier en CRLF casse tout.
    $text = [System.IO.File]::ReadAllText($Path)
    if ($text.Contains("`r`n")) {
        $normalized = $text -replace "`r`n", "`n"
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($Path, $normalized, $encoding)
    }
}

$ssh = Get-Command ssh -ErrorAction SilentlyContinue
if (-not $ssh) {
    Write-Warn "La commande 'ssh' est introuvable sur ce PC."
    Write-Host ""
    Write-Host " Installez le client OpenSSH (Windows 10/11 :" -ForegroundColor Yellow
    Write-Host " Parametres > Applications > Fonctionnalites facultatives)."
    Write-Host " Ou connectez-vous depuis la Recalbox avec un clavier :"
    Write-Host ""
    Write-Host "   sh /recalbox/share/recalbox-rfid/install.sh --start" -ForegroundColor White
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
    Write-Err "L'installation a echoue (code $exitCode)."
    Write-Host ""
    Write-Host " A verifier :" -ForegroundColor Yellow
    Write-Host "  - le serveur SSH est active (menu RESEAU > SERVEUR SSH > ON) ;"
    Write-Host "  - le mot de passe est correct (recalboxroot par defaut) ;"
    Write-Host "  - la Recalbox est bien en version 9 ou plus recente."
    Write-Host ""
    Write-Host " Detail du diagnostic : docs/DEPANNAGE.md"
} else {
    Write-Ok "Installation terminee"
    Write-Host ""
    Write-Host " Prochaines etapes :" -ForegroundColor Cyan
    Write-Host "  1. Redemarrez Recalbox si l'installateur le demande (SPI)."
    Write-Host "  2. Verifiez le materiel :"
    Write-Host "       ssh root@$target `"/recalbox/share/system/rfid/rfidctl test`""
    Write-Host "  3. Selectionnez un jeu dans Recalbox, appui court sur le bouton,"
    Write-Host "     scannez un badge."
    Write-Host ""
    Write-Host " Documentation : docs/INSTALLATION.md et docs/UTILISATION.md"
}

Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"
