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
WEB_USERSCRIPT_NAME="recalbox-rfid-web(permanent).py3"
BOOT_CONFIG="/boot/recalbox-user-config.txt"

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
if [ -x "$HOME_DIR/rfidctl" ]; then
    sh "$HOME_DIR/rfidctl" stop || true
elif [ -f "$HOME_DIR/rfid.pid" ]; then
    PID=$(cat "$HOME_DIR/rfid.pid" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        sleep 1
    fi
fi
say "  service arrete"

# 2. Retirer le script de demarrage Recalbox
if [ -f "$USERSCRIPTS_DIR/$USERSCRIPT_NAME" ]; then
    rm -f "$USERSCRIPTS_DIR/$USERSCRIPT_NAME"
    say "  script de demarrage supprime"
fi
if [ -f "$USERSCRIPTS_DIR/$WEB_USERSCRIPT_NAME" ]; then
    rm -f "$USERSCRIPTS_DIR/$WEB_USERSCRIPT_NAME"
    say "  interface web de secours supprimee"
fi

# 3. SPI (optionnel)
if [ "$REMOVE_SPI" = "1" ]; then
    if [ -f "$BOOT_CONFIG.bak-rfid-launcher" ]; then
        cp -f "$BOOT_CONFIG" "$BOOT_CONFIG.avant-desinstallation" 2>/dev/null || true
        cp -f "$BOOT_CONFIG.bak-rfid-launcher" "$BOOT_CONFIG"
        say "  configuration boot restauree depuis $BOOT_CONFIG.bak-rfid-launcher"
        say "  (copie de securite : $BOOT_CONFIG.avant-desinstallation)"
    elif [ -f "$BOOT_CONFIG" ]; then
        grep -v -e '^# Active le bus SPI pour le lecteur RFID RC522' \
                -e '^# (ajoute par Recalbox RFID Launcher)' \
                -e '^dtparam=spi=on' \
                "$BOOT_CONFIG" > "$BOOT_CONFIG.tmp" || true
        mv -f "$BOOT_CONFIG.tmp" "$BOOT_CONFIG"
        warn "ligne 'dtparam=spi=on' retiree : verifiez $BOOT_CONFIG si vous utilisez"
        warn "le SPI pour autre chose (ecran TFT par exemple)."
    fi
fi

# 4. Fichiers
if [ "$KEEP_DATA" = "1" ]; then
    rm -rf "$HOME_DIR/app" "$HOME_DIR/userscript" "$HOME_DIR/web-bootstrap" "$HOME_DIR/docs"
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
