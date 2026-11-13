# =============================================================================
#  Recalbox RFID Launcher - Windows installation wizard
#
#  Double-click INSTALLER.cmd (in the same folder) rather than running
#  this script directly.
#
#  This script:
#    1. asks for the Recalbox address;
#    2. copies the program to the \\RECALBOX\share share;
#    3. installs the WebSocket agent (management from installer.html);
#    4. offers to install right away over SSH, otherwise opens installer.html.
# =============================================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Items = @("app", "userscript", "bootstrap", "docs", "tests",
           "install.sh", "uninstall.sh", "VERSION", "README.md", "CHANGELOG.md",
           "installer.html", "windows")

function Write-Info($message) { Write-Host "  $message" -ForegroundColor Gray }
function Write-Ok($message) { Write-Host "  OK  $message" -ForegroundColor Green }
function Write-Warn($message) { Write-Host "  ATTENTION  $message" -ForegroundColor Yellow }
function Write-Err($message) { Write-Host "  ERREUR  $message" -ForegroundColor Red }

function Normalize-LineEndings($Path) {
    # Recalbox runs scripts with /bin/sh: a CRLF file breaks everything.
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
# Program copy
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
# WebSocket agent (installation and management from installer.html)
# --------------------------------------------------------------------------- #
$bootstrapName = "recalbox-rfid-agent(permanent).py3"
$bootstrap = Join-Path $destination "bootstrap\$bootstrapName"
$userscripts = Join-Path $share "userscripts"
if (Test-Path $bootstrap) {
    New-Item -ItemType Directory -Path $userscripts -Force | Out-Null
    $installed = Join-Path $userscripts $bootstrapName
    Copy-Item $bootstrap $installed -Force
    Normalize-LineEndings $installed
    Write-Ok "Agent WebSocket installe (demarre avec Recalbox)"
} else {
    Write-Warn "bootstrap introuvable : l'agent WebSocket sera indisponible."
}

# --------------------------------------------------------------------------- #
# Immediate installation over SSH (optional)
# --------------------------------------------------------------------------- #
Write-Host ""
$answer = Read-Host "Installer tout de suite par SSH ? (O/n)"
$installNow = [string]::IsNullOrWhiteSpace($answer) -or ($answer -match '^[oOyY]')

if (-not $installNow) {
    $page = Get-ChildItem -Path (Join-Path $ProjectRoot "dist") -Filter "recalbox-rfid-installer-*.html" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            Select-Object -First 1
    if (-not $page) {
        $page = Get-Item (Join-Path $ProjectRoot "installer.html") -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Ok "Preparation terminee."
    Write-Host ""
    Write-Host " Prochaines etapes :" -ForegroundColor Cyan
    Write-Host "  1. Redemarrez Recalbox (menu QUITTER > REDEMARRER)."
    Write-Host "  2. L'agent WebSocket demarre avec Recalbox (ws://$target`:8765)."
    Write-Host "  3. Ouvrez l'installateur (il s'ouvre ci-dessous si possible) :"
    Write-Host "     - fichier unique : « Choisir \\RECALBOX\share et copier » ;"
    Write-Host "     - sinon : adresse $target, port 8765, jeton de"
    Write-Host "       \\$target\share\system\rfid\token.txt"
    Write-Host "  4. Cliquez sur « Installer », puis redemarrez si le SPI etait inactif."
    Write-Host ""
    if ($page) { Start-Process $page.FullName }
    Read-Host "Appuyez sur Entree pour fermer"
    exit 0
}

$ssh = Get-Command ssh -ErrorAction SilentlyContinue
if (-not $ssh) {
    Write-Warn "La commande 'ssh' est introuvable sur ce PC."
    Write-Host ""
    Write-Host " Utilisez plutot l'agent WebSocket :" -ForegroundColor Yellow
    Write-Host "  1. Redemarrez Recalbox."
    Write-Host "  2. Ouvrez installer.html, connectez-vous a $target`:8765 avec le"
    Write-Host "     jeton de \\$target\share\system\rfid\token.txt, puis « Installer »."
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
    Write-Host " Pas de panique : l'agent WebSocket reste disponible." -ForegroundColor Yellow
    Write-Host "  1. Redemarrez Recalbox."
    Write-Host "  2. Ouvrez installer.html, connectez-vous a $target`:8765 avec le"
    Write-Host "     jeton de \\$target\share\system\rfid\token.txt, puis « Installer »."
    Write-Host ""
    Write-Host " A verifier si vous retentez par SSH : serveur SSH active"
    Write-Host " (RESEAU > SERVEUR SSH > ON), mot de passe, version de Recalbox."
} else {
    Write-Ok "Installation terminee"
    Write-Host ""
    Write-Host " Prochaines etapes :" -ForegroundColor Cyan
    Write-Host "  1. Redemarrez Recalbox si l'installateur le demande (SPI)."
    Write-Host "  2. Ouvrez installer.html (agent : ws://$target`:8765,"
    Write-Host "     jeton : \\$target\share\system\rfid\token.txt)."
    Write-Host "  3. Ou : ssh root@$target `"/recalbox/share/system/rfid/rfidctl test`""
    Write-Host ""
    Write-Host " Documentation : docs/INSTALLATION.md et docs/USAGE.md"
}

Write-Host ""
Read-Host "Appuyez sur Entree pour fermer"
