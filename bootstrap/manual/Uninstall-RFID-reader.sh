#!/bin/sh
# =============================================================================
#  Recalbox RFID Launcher - uninstall from the Recalbox menu (Recalbox 10+)
#
#  START > ADVANCED SETTINGS > USER SCRIPTS > Uninstall-RFID-reader.
#
#  Removes the program, the startup scripts and the SPI line added at install
#  time, and stops the reader service and the agent. Badges (tags.json) and
#  settings (config.ini) are KEPT, and so is "Install-RFID-reader" in the same
#  menu: reinstalling later is a single click and finds everything again.
#  The SPI change only takes effect after the next reboot.
#
#  Full removal (data included): sh /recalbox/share/system/rfid/uninstall.sh
# =============================================================================

SHARE="/recalbox/share"
HOME_DIR="$SHARE/system/rfid"
UNINSTALL="$HOME_DIR/uninstall.sh"
[ -f "$UNINSTALL" ] || UNINSTALL="$SHARE/recalbox-rfid/uninstall.sh"
LOG="$HOME_DIR/logs/uninstall.log"

if [ ! -f "$UNINSTALL" ]; then
    echo "The RFID reader is not installed."
    exit 0
fi

mkdir -p "$(dirname "$LOG")"
# Copied to /tmp first: uninstall.sh deletes its own folder while running.
cp -f "$UNINSTALL" /tmp/rfid-uninstall.sh
{
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
    sh /tmp/rfid-uninstall.sh --keep-data --remove-spi --from-menu
} >> "$LOG" 2>&1
CODE=$?
rm -f /tmp/rfid-uninstall.sh

if [ "$CODE" = "0" ]; then
    echo "RFID reader uninstalled. Badges and settings are kept."
else
    echo "Uninstall failed (code $CODE): see $LOG"
fi
exit "$CODE"
