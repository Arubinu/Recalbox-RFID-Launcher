#!/bin/sh
# =============================================================================
#  Recalbox RFID Launcher - desinstallation
#
#      sh /recalbox/share/system/rfid/uninstall.sh
#      sh uninstall.sh --keep-data      (conserve config.ini et tags.json)
#      sh uninstall.sh --remove-spi     (retire aussi dtparam=spi=on)
# =============================================================================
set -eu

APP_NAME="Recalbox RFID Launcher"
DEFAULT_HOME="/recalbox/share/system/rfid"
USERSCRIPTS_DIR="/recalbox/share/userscripts"
USERSCRIPT_NAME="recalbox-rfid(permanent).py3"
AGENT_USERSCRIPT_NAME="recalbox-rfid-agent(permanent).py3"
MANUAL_SCRIPT_NAME="Installer-lecteur-RFID.sh"
LEGACY_USERSCRIPTS="recalbox-rfid-autoinstall(permanent).py3 recalbox-rfid-web(permanent).py3"
BOOT_CONFIG="/boot/recalbox-user-config.txt"
BOOT_CONFIG_MAIN="/boot/config.txt"

HOME_DIR="${RFID_HOME:-$DEFAULT_HOME}"
KEEP_DATA=0
REMOVE_SPI=0

say() { printf '%s\n' "$*"; }
warn() { printf 'ATTENTION  %s\n' "$*"; }

usage() {
    cat <<EOF
$APP_NAME - desinstallation

Options :
  --home <dossier>   dossier d'installation (defaut : $DEFAULT_HOME)
  --keep-data        conserve config.ini et tags.json
  --remove-spi       retire la ligne 'dtparam=spi=on' ajoutee a l'installation
  -h, --help         affiche cette aide
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --home)       [ $# -ge 2 ] || { echo "--home : valeur manquante" >&2; exit 2; }; HOME_DIR="$2"; shift 2 ;;
        --keep-data)  KEEP_DATA=1; shift ;;
        --remove-spi) REMOVE_SPI=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        *)            echo "option inconnue : $1" >&2; usage; exit 2 ;;
    esac
done
HOME_DIR=$(printf '%s' "$HOME_DIR" | sed 's:/*$::')

say "Desinstallation de $APP_NAME"
say "Dossier : $HOME_DIR"

# 1. Arreter le service
# Le partage Recalbox (exFAT) ne garde aucun droit d'execution : on teste
# l'existence du fichier, pas -x, et on l'appelle toujours avec sh.
if [ -f "$HOME_DIR/rfidctl" ]; then
    sh "$HOME_DIR/rfidctl" stop || true
elif [ -f "$HOME_DIR/rfid.pid" ]; then
    PID=$(cat "$HOME_DIR/rfid.pid" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        sleep 1
    fi
fi
say "  service arrete"
# L'agent de connexion (installer.html) tourne a part : on l'arrete aussi.
if command -v pkill >/dev/null 2>&1; then
    pkill -f "$HOME_DIR/app/main.py agent" 2>/dev/null || true
    say "  agent de connexion arrete"
fi

# 2. Retirer le script de demarrage Recalbox
if [ -f "$USERSCRIPTS_DIR/$USERSCRIPT_NAME" ]; then
    rm -f "$USERSCRIPTS_DIR/$USERSCRIPT_NAME"
    say "  script de demarrage supprime"
fi
if [ -f "$USERSCRIPTS_DIR/$AGENT_USERSCRIPT_NAME" ]; then
    rm -f "$USERSCRIPTS_DIR/$AGENT_USERSCRIPT_NAME"
    say "  agent WebSocket supprime"
fi
if [ -f "$USERSCRIPTS_DIR/manual/$MANUAL_SCRIPT_NAME" ]; then
    rm -f "$USERSCRIPTS_DIR/manual/$MANUAL_SCRIPT_NAME"
    rmdir "$USERSCRIPTS_DIR/manual" 2>/dev/null || true
    say "  script du menu Recalbox supprime"
fi
for legacy in $LEGACY_USERSCRIPTS; do
    if [ -f "$USERSCRIPTS_DIR/$legacy" ]; then
        rm -f "$USERSCRIPTS_DIR/$legacy"
        say "  ancien script supprime : $legacy"
    fi
done

# 3. SPI (optionnel)
# Retire de $1 les lignes ajoutees par l'installation. On ne restaure jamais
# l'ancienne sauvegarde complete : elle effacerait les reglages faits depuis.
strip_spi() {
    target="$1"
    tmp="/tmp/rfid-boot-config.$$"
    if grep -v -e '^# Active le bus SPI pour le lecteur RFID RC522' \
               -e '^# (ajoute par Recalbox RFID Launcher)' \
               -e '^dtparam=spi=on' \
               "$target" > "$tmp" && cat "$tmp" > "$target" 2>/dev/null; then
        rm -f "$target.bak-rfid-launcher" 2>/dev/null || true
        say "  ligne 'dtparam=spi=on' retiree de $target"
    else
        warn "impossible de modifier $target : retirez 'dtparam=spi=on' a la main."
    fi
    rm -f "$tmp"
}

if [ "$REMOVE_SPI" = "1" ]; then
    # /boot est monte en lecture seule sur Recalbox : on le rouvre le temps
    # de la modification (sans cela, cp/mv echouaient et set -e arretait tout,
    # programme et donnees restant en place).
    REMOUNTED=0
    if [ ! -w "$BOOT_CONFIG" ] && mount -o remount,rw /boot 2>/dev/null; then
        REMOUNTED=1
    fi
    [ -f "$BOOT_CONFIG" ] && strip_spi "$BOOT_CONFIG"
    # config.txt : la ligne est ajoutee sans commentaire. On ne la retire que
    # si la sauvegarde d'avant installation ne la contenait pas (SPI deja
    # utilise par autre chose : on n'y touche pas).
    MAIN_BACKUP="$BOOT_CONFIG_MAIN.bak-rfid-launcher"
    if [ -f "$BOOT_CONFIG_MAIN" ] && [ -f "$MAIN_BACKUP" ] \
       && ! grep -q '^[[:space:]]*dtparam=spi=on' "$MAIN_BACKUP"; then
        strip_spi "$BOOT_CONFIG_MAIN"
    fi
    warn "verifiez la configuration si vous utilisez le SPI pour autre chose"
    warn "(ecran TFT par exemple)."
    sync
    if [ "$REMOUNTED" = "1" ]; then
        mount -o remount,ro /boot 2>/dev/null || true
    fi
fi

# 4. Fichiers
if [ "$KEEP_DATA" = "1" ]; then
    rm -rf "$HOME_DIR/app" "$HOME_DIR/userscript" "$HOME_DIR/bootstrap" "$HOME_DIR/docs"
    rm -f "$HOME_DIR/rfidctl" "$HOME_DIR/install.sh" "$HOME_DIR/uninstall.sh" \
          "$HOME_DIR/VERSION" "$HOME_DIR/README.md" "$HOME_DIR/CHANGELOG.md" \
          "$HOME_DIR/rfid.pid" "$HOME_DIR/status.json"
    say "  programme supprime, donnees conservees :"
    say "    $HOME_DIR/config.ini"
    say "    $HOME_DIR/tags.json"
else
    rm -rf "$HOME_DIR"
    say "  dossier $HOME_DIR supprime"
fi

say ""
say "Desinstallation terminee."
if [ "$REMOVE_SPI" = "1" ]; then
    say "Redemarrez Recalbox pour appliquer la configuration du bus SPI."
fi
