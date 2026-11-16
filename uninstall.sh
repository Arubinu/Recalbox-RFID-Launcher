#!/bin/sh
# =============================================================================
#  Recalbox RFID Launcher - uninstaller
#
#      sh /recalbox/share/system/rfid/uninstall.sh
#      sh uninstall.sh --keep-data      (keeps config.ini and tags.json)
#      sh uninstall.sh --remove-spi     (also removes dtparam=spi=on)
#      sh uninstall.sh --from-menu      (used by the Recalbox menu script)
# =============================================================================
set -eu

APP_NAME="Recalbox RFID Launcher"
DEFAULT_HOME="/recalbox/share/system/rfid"
USERSCRIPTS_DIR="/recalbox/share/userscripts"
USERSCRIPT_NAME="recalbox-rfid(permanent).py3"
AGENT_USERSCRIPT_NAME="recalbox-rfid-agent(permanent).py3"
MENU_INSTALL_NAME="Install-RFID-reader.sh"
MENU_UNINSTALL_NAME="Uninstall-RFID-reader.sh"
LEGACY_USERSCRIPTS="recalbox-rfid-autoinstall(permanent).py3 recalbox-rfid-web(permanent).py3"
LEGACY_MENU_SCRIPTS="Installer-lecteur-RFID.sh"
BOOT_CONFIG="/boot/recalbox-user-config.txt"
BOOT_CONFIG_MAIN="/boot/config.txt"

HOME_DIR="${RFID_HOME:-$DEFAULT_HOME}"
KEEP_DATA=0
REMOVE_SPI=0
FROM_MENU=0

say() { printf '%s\n' "$*"; }
warn() { printf 'ATTENTION  %s\n' "$*"; }

usage() {
    cat <<EOF
$APP_NAME - desinstallation

Options :
  --home <dossier>   dossier d'installation (defaut : $DEFAULT_HOME)
  --keep-data        conserve config.ini et tags.json
  --remove-spi       retire la ligne 'dtparam=spi=on' ajoutee a l'installation
  --from-menu        garde « $MENU_INSTALL_NAME » dans le menu de Recalbox
  -h, --help         affiche cette aide
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --home)       [ $# -ge 2 ] || { echo "--home : valeur manquante" >&2; exit 2; }; HOME_DIR="$2"; shift 2 ;;
        --keep-data)  KEEP_DATA=1; shift ;;
        --remove-spi) REMOVE_SPI=1; shift ;;
        --from-menu)  FROM_MENU=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        *)            echo "option inconnue : $1" >&2; usage; exit 2 ;;
    esac
done
HOME_DIR=$(printf '%s' "$HOME_DIR" | sed 's:/*$::')

say "Desinstallation de $APP_NAME"
say "Dossier : $HOME_DIR"

# 1. Stop the service.
# The Recalbox share (exFAT) keeps no execute bit: test that the file exists,
# not -x, and always run it through sh.
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
# The connection agent (used by installer.html) runs on its own: stop it too.
if command -v pkill >/dev/null 2>&1; then
    pkill -f "$HOME_DIR/app/main.py agent" 2>/dev/null || true
    pkill -f "recalbox-rfid/app/main.py agent" 2>/dev/null || true
    say "  agent de connexion arrete"
fi

# 2. Remove the Recalbox startup scripts.
if [ -f "$USERSCRIPTS_DIR/$USERSCRIPT_NAME" ]; then
    rm -f "$USERSCRIPTS_DIR/$USERSCRIPT_NAME"
    say "  script de demarrage supprime"
fi
if [ -f "$USERSCRIPTS_DIR/$AGENT_USERSCRIPT_NAME" ]; then
    rm -f "$USERSCRIPTS_DIR/$AGENT_USERSCRIPT_NAME"
    say "  agent WebSocket supprime"
fi
# Menu scripts (Recalbox 10). From the menu, "Install" stays so that a
# reinstall is one click away; the "manual" folder belongs to Recalbox.
MENU_REMOVE="$MENU_UNINSTALL_NAME $LEGACY_MENU_SCRIPTS"
[ "$FROM_MENU" = "1" ] || MENU_REMOVE="$MENU_REMOVE $MENU_INSTALL_NAME"
for name in $MENU_REMOVE; do
    if [ -f "$USERSCRIPTS_DIR/manual/$name" ]; then
        rm -f "$USERSCRIPTS_DIR/manual/$name"
        say "  script du menu Recalbox supprime : $name"
    fi
done
for legacy in $LEGACY_USERSCRIPTS; do
    if [ -f "$USERSCRIPTS_DIR/$legacy" ]; then
        rm -f "$USERSCRIPTS_DIR/$legacy"
        say "  ancien script supprime : $legacy"
    fi
done

# Menu locked by the player cards option: the previous settings come back.
if [ -f "$HOME_DIR/frontend-lock.json" ] && [ -d "$HOME_DIR/app" ]; then
    if (cd "$HOME_DIR/app" && python3 -c "from rfid import frontend_lock; frontend_lock.apply('$HOME_DIR', False, restart=False)") 2>/dev/null; then
        say "  menu de la Recalbox deverrouille (au prochain demarrage)"
    else
        warn "impossible de deverrouiller le menu : remettez emulationstation.menu=default et emulationstation.favoritesonly=0 dans recalbox.conf"
    fi
fi

# Reader screen straight at boot: Recalbox's interface starts at boot again,
# and the block of custom.sh goes away.
if [ -d "$HOME_DIR/app" ]; then
    if (cd "$HOME_DIR/app" && python3 -c "from rfid import bootmode; bootmode.restore_interface('$HOME_DIR')") 2>/dev/null; then
        say "  demarrage de l'interface de Recalbox retabli"
    else
        warn "verifiez system.es.atstartup dans recalbox.conf (1 ou absent) et /recalbox/share/system/custom.sh"
    fi
fi

# 3. SPI (optional).
# Removes from $1 the lines added at install time. The old full backup is
# never restored: it would wipe the settings changed since then.
strip_spi() {
    target="$1"
    tmp="/tmp/rfid-boot-config.$$"
    if grep -v -e '^# Active le bus SPI pour le lecteur RFID RC522' \
               -e '^# (ajoute par Recalbox RFID Launcher)' \
               -e '^# Enables the SPI bus for the RC522 RFID reader' \
               -e '^# (added by Recalbox RFID Launcher)' \
               -e '^dtparam=spi=on' \
               -e '^# Second SPI bus for the status LEDs' \
               -e '^dtoverlay=spi1-1cs' \
               "$target" > "$tmp" && cat "$tmp" > "$target" 2>/dev/null; then
        rm -f "$target.bak-rfid-launcher" 2>/dev/null || true
        say "  ligne 'dtparam=spi=on' retiree de $target"
    else
        warn "impossible de modifier $target : retirez 'dtparam=spi=on' a la main."
    fi
    rm -f "$tmp"
}

if [ "$REMOVE_SPI" = "1" ]; then
    # /boot is mounted read-only on Recalbox: remount it for the change only
    # (without this, cp/mv failed and set -e stopped everything, leaving the
    # program and the data in place).
    REMOUNTED=0
    if [ ! -w "$BOOT_CONFIG" ] && mount -o remount,rw /boot 2>/dev/null; then
        REMOUNTED=1
    fi
    [ -f "$BOOT_CONFIG" ] && strip_spi "$BOOT_CONFIG"
    # config.txt: the line is added without a comment. It is only removed when
    # the pre-install backup did not have it (SPI already used by something
    # else: leave it alone).
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

# 4. Files.
if [ "$KEEP_DATA" = "1" ]; then
    rm -rf "$HOME_DIR/app" "$HOME_DIR/userscript" "$HOME_DIR/bootstrap" "$HOME_DIR/docs" "$HOME_DIR/web" "$HOME_DIR/cache"
    rm -f "$HOME_DIR/rfidctl" "$HOME_DIR/install.sh" "$HOME_DIR/uninstall.sh" \
          "$HOME_DIR/VERSION" "$HOME_DIR"/README*.md "$HOME_DIR/CHANGELOG.md" \
          "$HOME_DIR/installer.html" "$HOME_DIR/rfid.pid" "$HOME_DIR/status.json"
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
