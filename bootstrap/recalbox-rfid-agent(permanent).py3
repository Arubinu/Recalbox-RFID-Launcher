#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script permanent Recalbox : agent de gestion WebSocket.

Mise en place (une seule fois) :

1. copier le dossier ``recalbox-rfid`` sur le partage (``\\\\RECALBOX\\share``) ;
2. copier **ce fichier** dans le dossier ``userscripts`` du même partage ;
3. redémarrer Recalbox.

Ce script démarre l'agent WebSocket qui permet à ``installer.html`` (ouvert
depuis votre PC) d'installer, mettre à jour et gérer le lanceur RFID. Aucune
interface n'est servie par la Recalbox : uniquement un WebSocket protégé par un
jeton (``/recalbox/share/system/rfid/token.txt``).

Si le programme est déjà installé, l'agent démarre depuis l'installation ; sinon
il démarre depuis le dossier copié sur le partage, ce qui permet d'installer.
"""

import glob
import os
import sys

#: Dossier d'installation (surchargeable par la variable RFID_HOME).
RFID_HOME = os.environ.get("RFID_HOME", "/recalbox/share/system/rfid")

#: Racine du partage où chercher le dossier du projet.
SHARE = "/recalbox/share"


def find_source():
    """Cherche le dossier du projet (app/main.py + install.sh) sur le partage."""
    home = os.path.abspath(RFID_HOME)
    patterns = (
        os.path.join(SHARE, "*", "app", "main.py"),
        os.path.join(SHARE, "*", "*", "app", "main.py"),
        os.path.join(SHARE, "*", "*", "*", "app", "main.py"),
    )
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            folder = os.path.dirname(os.path.dirname(os.path.abspath(candidate)))
            if folder == home:
                continue
            if os.path.isfile(os.path.join(folder, "install.sh")):
                return folder
    return None


def main():
    main_py = os.path.join(RFID_HOME, "app", "main.py")
    if os.path.isfile(main_py):
        os.execv(sys.executable, [sys.executable, main_py, "agent", "--home", RFID_HOME])
        return 1

    source = find_source()
    if source is None:
        sys.stderr.write(
            "recalbox-rfid: dossier du projet introuvable dans %s\n" % SHARE
        )
        sys.stderr.write(
            "Copiez le dossier recalbox-rfid sur le partage, puis redemarrez Recalbox.\n"
        )
        return 1
    os.execv(
        sys.executable,
        [sys.executable, os.path.join(source, "app", "main.py"),
         "agent", "--home", RFID_HOME, "--source", source],
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
