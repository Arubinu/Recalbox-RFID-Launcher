#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script permanent Recalbox : demarre le service RFID.

Recalbox / EmulationStation execute au demarrage de l'interface tous les scripts
places dans /recalbox/share/userscripts dont le nom contient "(permanent)".
Ce fichier ne fait qu'executer l'application installee dans le dossier indique
ci-dessous. Il est reecrit a chaque installation ou mise a jour : ne le
modifiez pas, modifiez plutot /recalbox/share/system/rfid/config.ini.
"""

import os
import sys

# Remplace par install.sh au moment de l'installation.
RFID_HOME = "@RFID_HOME@"

MAIN = os.path.join(RFID_HOME, "app", "main.py")


def main():
    if not os.path.isfile(MAIN):
        sys.stderr.write("recalbox-rfid: programme introuvable: %s\n" % MAIN)
        return 1
    # os.execv remplace le processus courant : EmulationStation continue de
    # suivre le bon PID et le service herite de son environnement (audio...).
    os.execv(sys.executable, [sys.executable, MAIN, "daemon", "--home", RFID_HOME])
    return 1


if __name__ == "__main__":
    sys.exit(main())
