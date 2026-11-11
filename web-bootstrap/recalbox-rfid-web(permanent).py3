#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script permanent Recalbox : interface web d'installation / gestion.

À copier dans ``/recalbox/share/userscripts/`` (côté Windows :
``\\\\RECALBOX\\share\\userscripts``) puis redémarrer Recalbox. Ce script

* ne fait rien si le service tourne déjà (il sert lui-même l'interface web) ;
* sert l'interface web après une vingtaine de secondes si le service ne démarre
  pas (dépannage) ;
* sinon, démarre l'interface web depuis le dossier du projet copié sur le
  partage, ce qui permet d'installer le lanceur depuis un simple navigateur.

Aucun mot de passe, aucune ligne de commande : tout se fait dans le navigateur.
"""

import glob
import os
import sys
import time

#: Dossier d'installation (peut être surchargé par la variable RFID_HOME).
RFID_HOME = os.environ.get("RFID_HOME", "/recalbox/share/system/rfid")

#: Racine du partage où chercher le dossier du projet.
SHARE = "/recalbox/share"

#: Nombre d'essais (× 0,5 s) avant de considérer que le service ne démarre pas.
WAIT_TICKS = 40


def daemon_running(home):
    """Vrai si le fichier PID pointe vers un processus vivant."""
    try:
        with open(os.path.join(home, "rfid.pid"), "r", encoding="ascii") as handle:
            pid = int(handle.read().strip())
    except (OSError, ValueError):
        return False
    return pid > 0 and os.path.exists("/proc/%d" % pid)


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


def start_web(source):
    """Démarre l'interface web (remplace le processus courant)."""
    main = os.path.join(source, "app", "main.py")
    sys.stderr.write("recalbox-rfid: interface web depuis %s\n" % source)
    os.execv(
        sys.executable,
        [sys.executable, main, "web", "--home", RFID_HOME, "--source", source],
    )


def main():
    installed = os.path.isfile(os.path.join(RFID_HOME, "app", "main.py"))
    if installed:
        # Le service installe sert normalement l'interface : on lui laisse 20 s.
        for _ in range(WAIT_TICKS):
            if daemon_running(RFID_HOME):
                return 0
            time.sleep(0.5)
        sys.stderr.write("recalbox-rfid: service absent, interface web de secours\n")
        start_web(RFID_HOME)
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
    start_web(source)
    return 1


if __name__ == "__main__":
    sys.exit(main())
