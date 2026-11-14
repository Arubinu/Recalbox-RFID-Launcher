#!/bin/sh
# =============================================================================
#  Recalbox RFID Launcher - installer and updater
#
#  To run on Recalbox, as root (SSH connection), from the folder copied
#  to the network share:
#
#      sh /recalbox/share/recalbox-rfid/install.sh
#
#  The script is idempotent: running it again installs the new version while
#  keeping the configuration (config.ini) and the badges (tags.json).
# =============================================================================
set -eu

APP_NAME="Recalbox RFID Launcher"
VERSION="2.17.0"
DEFAULT_HOME="/recalbox/share/system/rfid"
USERSCRIPTS_DIR="/recalbox/share/userscripts"
USERSCRIPT_NAME="recalbox-rfid(permanent).py3"
AGENT_USERSCRIPT_NAME="recalbox-rfid-agent(permanent).py3"
MENU_SCRIPT_NAMES="Install-RFID-reader.sh Uninstall-RFID-reader.sh"
LEGACY_MENU_SCRIPTS="Installer-lecteur-RFID.sh"
BOOT_CONFIG="/boot/recalbox-user-config.txt"
BOOT_CONFIG_MAIN="/boot/config.txt"

HOME_DIR="${RFID_HOME:-$DEFAULT_HOME}"
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# The reference version is the package VERSION file.
if [ -f "$SCRIPT_DIR/VERSION" ]; then
    VERSION=$(tr -d ' \t\r\n' < "$SCRIPT_DIR/VERSION")
elif [ -f "$HOME_DIR/VERSION" ]; then
    VERSION=$(tr -d ' \t\r\n' < "$HOME_DIR/VERSION")
fi

DO_SPI=1
DO_START=0
DO_UPGRADE=0
DO_UNINSTALL=0
NO_RESTART=0
REMOTE_URL=""
PASSTHRU=""

NEED_REBOOT=0
WARN_FRONTEND=0
IS_ROOT=0
WAS_RUNNING=0

# --------------------------------------------------------------------------- #
# Affichage
# --------------------------------------------------------------------------- #
if [ -t 1 ]; then
    C_TITLE=$(printf '\033[1;36m')
    C_OK=$(printf '\033[1;32m')
    C_WARN=$(printf '\033[1;33m')
    C_ERR=$(printf '\033[1;31m')
    C_OFF=$(printf '\033[0m')
else
    C_TITLE=""; C_OK=""; C_WARN=""; C_ERR=""; C_OFF=""
fi

say() { printf '%s\n' "$*"; }
step() { printf '\n%s== %s ==%s\n' "$C_TITLE" "$*" "$C_OFF"; }
ok() { printf '%s  OK  %s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '%sATTENTION%s %s\n' "$C_WARN" "$C_OFF" "$*"; }
die() {
    printf '\n%sERREUR%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
$APP_NAME $VERSION - installateur

Utilisation :
  sh install.sh [options]

Options :
  --home <dossier>   dossier d'installation (defaut : $DEFAULT_HOME)
  --upgrade          mise a jour : conserve configuration et badges
  --start            demarre le service a la fin de l'installation
  --no-restart       ne redemarre pas le service (utilise par l'agent)
  --no-spi           n'active pas le bus SPI automatiquement
  --from-url <url>   telecharge et installe le fichier ZIP indique
  --uninstall        desinstalle (equivalent a uninstall.sh)
  -y, --yes          ne pose aucune question
  -h, --help         affiche cette aide

Exemples :
  sh install.sh
  sh install.sh --start
  sh install.sh --upgrade
  sh $HOME_DIR/rfidctl self-update https://exemple.fr/recalbox-rfid.zip
EOF
}

# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
while [ $# -gt 0 ]; do
    case "$1" in
        --home)
            [ $# -ge 2 ] || die "--home : valeur manquante"
            HOME_DIR="$2"; PASSTHRU="$PASSTHRU --home $2"; shift 2 ;;
        --upgrade)   DO_UPGRADE=1; PASSTHRU="$PASSTHRU --upgrade"; shift ;;
        --start)     DO_START=1;   PASSTHRU="$PASSTHRU --start";   shift ;;
        --no-restart) NO_RESTART=1; PASSTHRU="$PASSTHRU --no-restart"; shift ;;
        --no-spi)    DO_SPI=0;     PASSTHRU="$PASSTHRU --no-spi";  shift ;;
        --uninstall) DO_UNINSTALL=1; PASSTHRU="$PASSTHRU --uninstall"; shift ;;
        --from-url)
            [ $# -ge 2 ] || die "--from-url : valeur manquante"
            REMOTE_URL="$2"; shift 2 ;;
        -y|--yes)    PASSTHRU="$PASSTHRU -y"; shift ;;
        -h|--help)   usage; exit 0 ;;
        *)           die "option inconnue : $1 (voir --help)" ;;
    esac
done

HOME_DIR=$(printf '%s' "$HOME_DIR" | sed 's:/*$::')

# --------------------------------------------------------------------------- #
# Python 3 interpreter (python3, or python if its version is 3)
# --------------------------------------------------------------------------- #
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done
[ -n "$PYTHON" ] || die "Python 3 est introuvable. Recalbox 9 ou plus est necessaire."

# --------------------------------------------------------------------------- #
# Installation from a remote ZIP
# --------------------------------------------------------------------------- #
if [ -n "$REMOTE_URL" ]; then
    step "Telechargement de la mise a jour"
    command -v curl >/dev/null 2>&1 || die "curl est introuvable sur ce systeme"

    TMP_DIR=$(mktemp -d /tmp/recalbox-rfid-XXXXXX)
    say "URL : $REMOTE_URL"
    if ! curl -fsSL --connect-timeout 20 -o "$TMP_DIR/update.zip" "$REMOTE_URL"; then
        rm -rf "$TMP_DIR"
        die "telechargement impossible (verifiez l'URL et la connexion)"
    fi
    mkdir -p "$TMP_DIR/src"
    if ! "$PYTHON" -m zipfile -e "$TMP_DIR/update.zip" "$TMP_DIR/src"; then
        rm -rf "$TMP_DIR"
        die "le fichier ZIP est invalide"
    fi
    NEW_INSTALLER=$(find "$TMP_DIR/src" -type f -name install.sh | head -n 1)
    [ -n "$NEW_INSTALLER" ] || die "install.sh absent du ZIP"
    ok "Archive extraite : $TMP_DIR/src"
    say "Lancement de l'installateur de la nouvelle version..."
    # shellcheck disable=SC2086
    exec sh "$NEW_INSTALLER" --home "$HOME_DIR" --upgrade $PASSTHRU
fi

# --------------------------------------------------------------------------- #
# Verifications
# --------------------------------------------------------------------------- #
if [ "$(id -u)" = "0" ]; then
    IS_ROOT=1
fi

if [ "$DO_UNINSTALL" = "1" ]; then
    if [ -x "$HOME_DIR/uninstall.sh" ]; then
        exec sh "$HOME_DIR/uninstall.sh" --home "$HOME_DIR"
    elif [ -f "$SCRIPT_DIR/uninstall.sh" ]; then
        exec sh "$SCRIPT_DIR/uninstall.sh" --home "$HOME_DIR"
    fi
    die "uninstall.sh introuvable"
fi

command -v "$PYTHON" >/dev/null 2>&1 || die \
    "Python 3 est introuvable. Recalbox 9 ou plus est necessaire."

if [ ! -f "$SCRIPT_DIR/app/main.py" ]; then
    die "dossier 'app' absent : lancez install.sh depuis le dossier complet du projet"
fi

say ""
say "$C_TITLE=============================================="
say " $APP_NAME $VERSION"
say "==============================================$C_OFF"

if [ -f /recalbox/recalbox.version ]; then
    say "Recalbox           : $(cat /recalbox/recalbox.version)"
else
    warn "Ce systeme ne semble pas etre Recalbox (fichier /recalbox/recalbox.version absent)."
fi
say "Python             : $("$PYTHON" -c 'import sys; print(sys.version.split()[0])')"
say "Dossier cible      : $HOME_DIR"
say "Sources            : $SCRIPT_DIR"

if [ "$IS_ROOT" != "1" ]; then
    warn "Le script n'est pas lance en root : le bus SPI et le script de demarrage"
    warn "ne pourront pas etre installes (relancez avec 'su -' ou en root SSH)."
fi

# Service state before the update (to restart it at the end)
if [ -f "$HOME_DIR/rfid.pid" ]; then
    OLD_PID=$(cat "$HOME_DIR/rfid.pid" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        WAS_RUNNING=1
    fi
fi

# --------------------------------------------------------------------------- #
# Fichiers
# --------------------------------------------------------------------------- #
step "Installation des fichiers"
mkdir -p "$HOME_DIR" "$HOME_DIR/logs"

if [ "$SCRIPT_DIR" = "$HOME_DIR" ]; then
    ok "Sources deja en place, copie inutile"
else
    rm -rf "$HOME_DIR/app.new" "$HOME_DIR/app.old"
    cp -R "$SCRIPT_DIR/app" "$HOME_DIR/app.new"
    if [ -d "$HOME_DIR/app" ]; then
        mv "$HOME_DIR/app" "$HOME_DIR/app.old"
    fi
    mv "$HOME_DIR/app.new" "$HOME_DIR/app"
    rm -rf "$HOME_DIR/app.old"

    if [ -d "$SCRIPT_DIR/userscript" ]; then
        rm -rf "$HOME_DIR/userscript"
        cp -R "$SCRIPT_DIR/userscript" "$HOME_DIR/userscript"
    fi
    if [ -d "$SCRIPT_DIR/bootstrap" ]; then
        rm -rf "$HOME_DIR/bootstrap"
        cp -R "$SCRIPT_DIR/bootstrap" "$HOME_DIR/bootstrap"
    fi
    if [ -d "$SCRIPT_DIR/docs" ]; then
        rm -rf "$HOME_DIR/docs"
        cp -R "$SCRIPT_DIR/docs" "$HOME_DIR/docs"
    fi
    # Management page served to phones (http://recalbox.local:8765/).
    if [ -d "$SCRIPT_DIR/web" ]; then
        rm -rf "$HOME_DIR/web"
        cp -R "$SCRIPT_DIR/web" "$HOME_DIR/web"
    fi
    for extra in install.sh uninstall.sh VERSION CHANGELOG.md installer.html; do
        if [ -f "$SCRIPT_DIR/$extra" ]; then
            cp -f "$SCRIPT_DIR/$extra" "$HOME_DIR/$extra"
        fi
    done
    # One README per language (README.md is English, README.<code>.md the others).
    for readme in "$SCRIPT_DIR"/README*.md; do
        if [ -f "$readme" ]; then
            cp -f "$readme" "$HOME_DIR/"
        fi
    done
    ok "Programme installe dans $HOME_DIR/app"
fi

printf '%s\n' "$VERSION" > "$HOME_DIR/VERSION"

# Command line shortcut
cat > "$HOME_DIR/rfidctl" <<EOF
#!/bin/sh
# Shortcut to $APP_NAME
exec $PYTHON "$HOME_DIR/app/main.py" --home "$HOME_DIR" "\$@"
EOF
chmod +x "$HOME_DIR/rfidctl"
ok "Commande installee : $HOME_DIR/rfidctl"

# Configuration and badge database (never overwritten)
if [ -f "$HOME_DIR/config.ini" ]; then
    ok "Configuration conservee : $HOME_DIR/config.ini"
else
    "$PYTHON" "$HOME_DIR/app/main.py" --home "$HOME_DIR" config-init >/dev/null
    ok "Configuration creee : $HOME_DIR/config.ini"
fi
if [ -f "$HOME_DIR/tags.json" ]; then
    TAGS_COUNT=$("$PYTHON" -c "import json,sys;print(len(json.load(open(sys.argv[1])).get('tags',{})))" "$HOME_DIR/tags.json" 2>/dev/null || echo "?")
    ok "Badges conserves : $HOME_DIR/tags.json ($TAGS_COUNT entree(s))"
else
    ok "Base de badges : $HOME_DIR/tags.json (sera creee au premier badge)"
fi

# --------------------------------------------------------------------------- #
# Demarrage automatique (script permanent Recalbox)
# --------------------------------------------------------------------------- #
step "Demarrage automatique avec Recalbox"
TEMPLATE="$HOME_DIR/userscript/$USERSCRIPT_NAME"
if [ ! -f "$TEMPLATE" ]; then
    TEMPLATE="$SCRIPT_DIR/userscript/$USERSCRIPT_NAME"
fi
if [ "$IS_ROOT" = "1" ] && [ -f "$TEMPLATE" ]; then
    mkdir -p "$USERSCRIPTS_DIR"
    sed "s|@RFID_HOME@|$HOME_DIR|g" "$TEMPLATE" > "$USERSCRIPTS_DIR/$USERSCRIPT_NAME"
    chmod +x "$USERSCRIPTS_DIR/$USERSCRIPT_NAME"
    ok "Script de demarrage : $USERSCRIPTS_DIR/$USERSCRIPT_NAME"

    # WebSocket agent: installation, update and management from installer.html.
    AGENT_TEMPLATE="$HOME_DIR/bootstrap/$AGENT_USERSCRIPT_NAME"
    [ -f "$AGENT_TEMPLATE" ] || AGENT_TEMPLATE="$SCRIPT_DIR/bootstrap/$AGENT_USERSCRIPT_NAME"
    if [ -f "$AGENT_TEMPLATE" ]; then
        cp -f "$AGENT_TEMPLATE" "$USERSCRIPTS_DIR/$AGENT_USERSCRIPT_NAME"
        chmod +x "$USERSCRIPTS_DIR/$AGENT_USERSCRIPT_NAME"
        ok "Agent WebSocket : $USERSCRIPTS_DIR/$AGENT_USERSCRIPT_NAME"
    fi

    # Recalbox 10: install / uninstall scripts runnable from the menu
    # (repair or removal without SSH). Older names are removed.
    for name in $LEGACY_MENU_SCRIPTS; do
        rm -f "$USERSCRIPTS_DIR/manual/$name" 2>/dev/null || true
    done
    for name in $MENU_SCRIPT_NAMES; do
        MENU_TEMPLATE="$HOME_DIR/bootstrap/manual/$name"
        [ -f "$MENU_TEMPLATE" ] || MENU_TEMPLATE="$SCRIPT_DIR/bootstrap/manual/$name"
        if [ -f "$MENU_TEMPLATE" ]; then
            mkdir -p "$USERSCRIPTS_DIR/manual"
            cp -f "$MENU_TEMPLATE" "$USERSCRIPTS_DIR/manual/$name"
            chmod +x "$USERSCRIPTS_DIR/manual/$name" 2>/dev/null || true
            ok "Script du menu Recalbox : $USERSCRIPTS_DIR/manual/$name"
        fi
    done
else
    warn "Script de demarrage non installe (droits root necessaires)."
    say "  Copiez manuellement le fichier $USERSCRIPT_NAME dans $USERSCRIPTS_DIR"
fi

# --------------------------------------------------------------------------- #
# Bus SPI
# --------------------------------------------------------------------------- #
step "Bus SPI (lecteur RC522)"
# The line is written even when SPI is already live: an uninstall may have
# removed it without a reboot since, and SPI would then be off at next boot.
# A reboot is only needed when the bus is not live yet.
SPI_LIVE=0
[ -e /dev/spidev0.0 ] && SPI_LIVE=1
if [ "$DO_SPI" = "0" ]; then
    warn "Activation du SPI ignoree (--no-spi)."
    say "  Ajoutez 'dtparam=spi=on' dans $BOOT_CONFIG puis redemarrez."
else
    if [ "$IS_ROOT" = "1" ] && [ -f "$BOOT_CONFIG" ]; then
        if grep -q '^[[:space:]]*dtparam=spi=on' "$BOOT_CONFIG" 2>/dev/null; then
            ok "SPI deja configure dans $BOOT_CONFIG"
            [ "$SPI_LIVE" = "1" ] || NEED_REBOOT=1
        else
            # On Recalbox 9/10, /boot is mounted read-only: it is remounted
            # read-write for the change, then set back to read-only.
            BOOT_RW=0
            if touch "$BOOT_CONFIG.rfid-test" 2>/dev/null; then
                rm -f "$BOOT_CONFIG.rfid-test" 2>/dev/null
            elif mount -o remount,rw /boot 2>/dev/null; then
                BOOT_RW=1
                ok "Partition /boot remontee en ecriture"
            fi
            if cp -f "$BOOT_CONFIG" "$BOOT_CONFIG.bak-rfid-launcher" 2>/dev/null; then
                say "  Sauvegarde : $BOOT_CONFIG.bak-rfid-launcher"
            fi
            if {
                printf '\n# Enables the SPI bus for the RC522 RFID reader\n'
                printf '# (added by %s)\n' "$APP_NAME"
                printf 'dtparam=spi=on\n'
            } >> "$BOOT_CONFIG" 2>/dev/null; then
                ok "SPI active dans $BOOT_CONFIG"
                [ "$SPI_LIVE" = "1" ] || NEED_REBOOT=1
            else
                warn "Impossible d'ecrire dans $BOOT_CONFIG (lecture seule)."
                say "  Activez le SPI a la main, puis redemarrez :"
                say "    - en SSH : mount -o remount,rw /boot, ajoutez 'dtparam=spi=on'"
                say "      a $BOOT_CONFIG, puis mount -o remount,ro /boot ;"
                say "    - ou depuis un PC : partition 'boot' de la carte SD, meme ligne."
                say "  Le reste de l'installation est termine malgre cela."
            fi
            if [ "$BOOT_RW" = "1" ]; then
                mount -o remount,ro /boot 2>/dev/null || true
            fi
        fi
    else
        warn "Impossible d'activer le SPI automatiquement."
        say "  Ajoutez cette ligne dans $BOOT_CONFIG :"
        say "      dtparam=spi=on"
        say "  puis redemarrez Recalbox."
    fi
fi

# --------------------------------------------------------------------------- #
# Recalbox 10: make sure the line is in /boot/config.txt itself
# --------------------------------------------------------------------------- #
# On Recalbox 10, the user file may be ignored (or overwritten): the line
# must be in the global section of config.txt.
if [ "$DO_SPI" != "0" ] && [ "$IS_ROOT" = "1" ] && [ -f "$BOOT_CONFIG_MAIN" ]; then
    if grep -q '^[[:space:]]*dtparam=spi=on' "$BOOT_CONFIG_MAIN" 2>/dev/null; then
        ok "SPI deja present dans $BOOT_CONFIG_MAIN"
        [ "$SPI_LIVE" = "1" ] || NEED_REBOOT=1
    else
        BOOT_RW=0
        if touch "$BOOT_CONFIG_MAIN.rfid-test" 2>/dev/null; then
            rm -f "$BOOT_CONFIG_MAIN.rfid-test" 2>/dev/null
        elif mount -o remount,rw /boot 2>/dev/null; then
            BOOT_RW=1
        fi
        if cp -f "$BOOT_CONFIG_MAIN" "$BOOT_CONFIG_MAIN.bak-rfid-launcher" 2>/dev/null; then
            say "  Sauvegarde : $BOOT_CONFIG_MAIN.bak-rfid-launcher"
        fi
        # Inserted right after the first dtparam line (global section).
        if awk -v ligne='dtparam=spi=on' '
            { print }
            !fait && $0 ~ /^[[:space:]]*dtparam=/ { print ligne; fait = 1 }
            END { if (!fait) print ligne }
        ' "$BOOT_CONFIG_MAIN" > "$BOOT_CONFIG_MAIN.rfid-new" 2>/dev/null &&
            mv -f "$BOOT_CONFIG_MAIN.rfid-new" "$BOOT_CONFIG_MAIN" 2>/dev/null; then
            ok "SPI ajoute dans $BOOT_CONFIG_MAIN (section globale)"
            [ "$SPI_LIVE" = "1" ] || NEED_REBOOT=1
        else
            rm -f "$BOOT_CONFIG_MAIN.rfid-new" 2>/dev/null
            warn "Impossible d'ecrire dans $BOOT_CONFIG_MAIN."
            say "  En SSH : mount -o remount,rw /boot, puis ajoutez"
            say "  'dtparam=spi=on' dans $BOOT_CONFIG_MAIN, puis mount -o remount,ro /boot."
        fi
        if [ "$BOOT_RW" = "1" ]; then
            mount -o remount,ro /boot 2>/dev/null || true
        fi
    fi
fi

# --------------------------------------------------------------------------- #
# Recalbox frontend check
# --------------------------------------------------------------------------- #
step "Verification du frontend Recalbox"
if "$PYTHON" "$HOME_DIR/app/main.py" --home "$HOME_DIR" frontend; then
    ok "Lancement de jeu par script disponible"
else
    WARN_FRONTEND=1
    warn "La commande de lancement n'a pas ete detectee."
    say "  Le lancement automatique des jeux necessite Recalbox 9 ou plus recent."
    say "  Le reste (lecture des badges, association) fonctionnera quand meme."
fi

# --------------------------------------------------------------------------- #
# Service startup
# --------------------------------------------------------------------------- #
step "Service"
if [ "$NO_RESTART" = "1" ]; then
    say "Redemarrage du service non demande (--no-restart)."
    say "Utilisez le bouton « Redemarrer Recalbox » de installer.html."
elif [ "$NEED_REBOOT" = "1" ]; then
    say "Redemarrage de Recalbox necessaire pour activer le SPI."
    say "Le service demarrera tout seul apres le redemarrage."
elif [ "$WAS_RUNNING" = "1" ] || [ "$DO_START" = "1" ]; then
    if "$PYTHON" "$HOME_DIR/app/main.py" --home "$HOME_DIR" restart; then
        ok "Service demarre"
    else
        warn "Le service n'a pas demarre : consultez $HOME_DIR/logs/rfid.log"
    fi
else
    say "Le service demarrera automatiquement au prochain demarrage de Recalbox."
    say "Pour le demarrer maintenant : sh $HOME_DIR/rfidctl start"
fi

# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
# Agent address (first IP address of the Raspberry Pi).
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$LOCAL_IP" ] || LOCAL_IP="recalbox.local"
AGENT_URL="ws://$LOCAL_IP:8765"

step "Termine"
say "Programme     : $HOME_DIR/app"
say "Configuration : $HOME_DIR/config.ini"
say "Badges        : $HOME_DIR/tags.json"
say "Journal       : $HOME_DIR/logs/rfid.log"
say "Agent WebSocket: $AGENT_URL"
say "Acces         : appui de 3 s sur le bouton (aucun mot de passe)"
say ""
say "Tout se gere depuis installer.html (ouvert sur votre PC) :"
say "  1. ouvrez installer.html (livre avec le projet) ;"
say "  2. adresse $LOCAL_IP, port 8765, puis bouton 3 s pour autoriser ;"
say "  3. installez, mettez a jour et gerez les badges."
say ""
say "Prochaines etapes :"
STEP=1
if [ "$NEED_REBOOT" = "1" ]; then
    say "  $STEP. Redemarrez Recalbox (menu > QUITTER > REDEMARRER) pour activer le SPI."
    STEP=$((STEP + 1))
fi
say "  $STEP. Connectez installer.html (bouton 3 s sur le boitier)"
STEP=$((STEP + 1))
say "  $STEP. Cliquez sur « Installer », puis redemarrez si le SPI etait inactif."
STEP=$((STEP + 1))
say "  $STEP. Choisissez un jeu dans Recalbox, appuyez sur le bouton, scannez un badge."
say ""
say "Aide : sh $HOME_DIR/rfidctl help   --   Mise a jour : $HOME_DIR/install.sh --upgrade"
if [ "$WARN_FRONTEND" = "1" ]; then
    say ""
    warn "Pensez a mettre a jour Recalbox (version 9 minimum) pour le lancement des jeux."
fi
say ""
