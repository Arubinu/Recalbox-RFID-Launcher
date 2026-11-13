#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recalbox permanent script: starts the RFID service.

Recalbox / EmulationStation runs, when the interface starts, every script
placed in /recalbox/share/userscripts whose name contains "(permanent)".
This file only runs the application installed in the folder given below. It
is rewritten on each install or update: do not edit it, edit
/recalbox/share/system/rfid/config.ini instead.
"""

import os
import sys

# Replaced by install.sh at install time.
RFID_HOME = "@RFID_HOME@"

MAIN = os.path.join(RFID_HOME, "app", "main.py")


def main():
    if not os.path.isfile(MAIN):
        sys.stderr.write("recalbox-rfid: programme introuvable: %s\n" % MAIN)
        return 1
    # os.execv replaces the current process: EmulationStation keeps tracking
    # the right PID and the service inherits its environment (audio...).
    os.execv(sys.executable, [sys.executable, MAIN, "daemon", "--home", RFID_HOME])
    return 1


if __name__ == "__main__":
    sys.exit(main())
