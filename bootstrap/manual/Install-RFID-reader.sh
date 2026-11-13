#!/bin/sh
# =============================================================================
#  Recalbox RFID Launcher - install from the Recalbox menu (Recalbox 10+)
#
#  Recalbox 10 lists the scripts of /recalbox/share/userscripts/manual in
#  START > ADVANCED SETTINGS > USER SCRIPTS and reads that folder again every
#  time the menu opens: installer.html drops this file there, the user runs it
#  with the controller, and the installation starts WITHOUT a reboot.
#
#  This script only starts, detached, the usual permanent script (install +
#  service + agent). Running it again is harmless: a second agent cannot open
#  the port already in use, and the installer does nothing when the version is
#  already the right one. If the reader has just been enabled, Recalbox
#  reboots once by itself: that is expected.
# =============================================================================

SHARE="/recalbox/share"
NAME="recalbox-rfid-agent(permanent).py3"
BOOT="$SHARE/userscripts/$NAME"
[ -f "$BOOT" ] || BOOT="$SHARE/recalbox-rfid/bootstrap/$NAME"

if [ ! -f "$BOOT" ]; then
    echo "RFID files not found on the Recalbox."
    echo "Copy them again from the page on your computer."
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# Detached from the menu: the script returns at once, the agent keeps running.
if command -v setsid >/dev/null 2>&1; then
    setsid "$PYTHON" "$BOOT" </dev/null >/dev/null 2>&1 &
else
    nohup "$PYTHON" "$BOOT" </dev/null >/dev/null 2>&1 &
fi

echo "RFID reader installation started."
echo "Go back to the page on your computer: it carries on by itself."
exit 0
