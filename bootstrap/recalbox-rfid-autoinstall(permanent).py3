#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script permanent Recalbox : installation et mise à jour automatiques.

Mise en place (une seule fois) :

1. copier le dossier ``recalbox-rfid`` sur le partage (``\\\\RECALBOX\\share``) ;
2. copier **ce fichier** dans le dossier ``userscripts`` du même partage ;
3. redémarrer Recalbox.

Au démarrage, ce script :

* installe le lanceur s'il est absent ;
* installe la version présente dans le dossier copié si elle est plus récente ;
* redémarre Recalbox une fois si l'activation du bus SPI l'exige ;
* sinon démarre le service (qui sert l'interface web de gestion) ;
* en cas d'échec, sert l'interface web pour diagnostiquer et relancer
  l'installation à la main.

Aucun serveur n'est nécessaire pour installer : le programme arrive par le
partage réseau, et tout s'exécute sur la Recalbox.
"""

import glob
import os
import subprocess
import sys
import time

#: Dossier d'installation (surchargeable par la variable RFID_HOME).
RFID_HOME = os.environ.get("RFID_HOME", "/recalbox/share/system/rfid")

#: Racine du partage où chercher le dossier du projet.
SHARE = "/recalbox/share"

#: Fichier de configuration du boot (le SPI s'active ici).
BOOT_CONFIG = "/boot/recalbox-user-config.txt"

#: Fichier d'état du frontend (pour ne pas redémarrer pendant un jeu).
STATE_FILE = "/tmp/es_state.inf"

#: Attente maximale du service au démarrage (x 0,5 s).
WAIT_TICKS = 40

#: Délai maximal d'une installation.
INSTALL_TIMEOUT = 900

#: Délai avant redémarrage automatique (secondes).
REBOOT_DELAY = 8


# ---------------------------------------------------------------------------
# Journalisation (le script est lancé par Recalbox, sans console)
# ---------------------------------------------------------------------------
def log(message):
    line = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        sys.stderr.write(line)
    except (OSError, ValueError):
        pass
    try:
        folder = os.path.join(RFID_HOME, "logs")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "auto-install.log"), "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Etat de l'installation
# ---------------------------------------------------------------------------
def main_py(home=None):
    return os.path.join(home or RFID_HOME, "app", "main.py")


def installed():
    return os.path.isfile(main_py())


def daemon_running():
    """Vrai si le fichier PID pointe vers un processus vivant."""
    try:
        with open(os.path.join(RFID_HOME, "rfid.pid"), "r", encoding="ascii") as handle:
            pid = int(handle.read().strip())
    except (OSError, ValueError):
        return False
    return pid > 0 and os.path.exists("/proc/%d" % pid)


def version_tuple(value):
    """Convertit "1.2.0" en (1, 2, 0) ; les parties non numériques valent 0."""
    parts = []
    for chunk in str(value).strip().split("."):
        digits = "".join(char for char in chunk if char.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def read_version(folder):
    try:
        with open(os.path.join(folder, "VERSION"), "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def newer_source_available(source):
    if not source:
        return False
    source_version = read_version(source)
    current_version = read_version(RFID_HOME)
    if not source_version:
        return False
    try:
        return version_tuple(source_version) > version_tuple(current_version)
    except ValueError:
        return False


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


# ---------------------------------------------------------------------------
# Matériel / système
# ---------------------------------------------------------------------------
def spi_active():
    return os.path.exists("/dev/spidev0.0")


def spi_configured():
    try:
        with open(BOOT_CONFIG, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip().replace(" ", "") == "dtparam=spi=on":
                    return True
    except OSError:
        return False
    return False


def game_running():
    try:
        with open(STATE_FILE, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    except OSError:
        return False
    return "State=playing" in content


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def run_install(source):
    installer = os.path.join(source, "install.sh")
    if not os.path.isfile(installer):
        log("install.sh introuvable dans %s" % source)
        return 1
    command = ["sh", installer, "--upgrade", "--no-restart", "--home", RFID_HOME]
    log("installation : %s" % " ".join(command))
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=INSTALL_TIMEOUT,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log("echec de l'installation : %s" % exc)
        return 1
    for line in (result.stdout or "").splitlines():
        log("  " + line)
    log("code de retour de l'installateur : %d" % result.returncode)
    return result.returncode


def start_service():
    if not installed():
        return
    log("demarrage du service")
    try:
        subprocess.Popen(
            [sys.executable, main_py(), "start", "--home", RFID_HOME],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        log("demarrage impossible : %s" % exc)


def serve_web(source):
    """Sert l'interface web (secours ou fin d'installation manuelle)."""
    base = RFID_HOME if installed() else source
    if not base:
        log("interface web impossible : aucun programme")
        return 1
    main = os.path.join(base, "app", "main.py")
    if not os.path.isfile(main):
        log("interface web impossible : %s absent" % main)
        return 1
    arguments = [sys.executable, main, "web", "--home", RFID_HOME]
    if not installed():
        arguments += ["--source", source]
    log("interface web de secours : %s" % main)
    os.execv(sys.executable, arguments)
    return 1


def reboot_system():
    log("redemarrage de Recalbox pour activer le SPI (dans %d s)" % REBOOT_DELAY)
    try:
        subprocess.Popen(
            ["sh", "-c", "sleep %d; sync; reboot" % REBOOT_DELAY],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        log("redemarrage impossible : %s" % exc)


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------
def main():
    source = find_source()

    if installed() and daemon_running():
        return 0  # tout va bien, le service sert l'interface web

    if installed():
        # Course au démarrage : on laisse 20 s au service pour apparaître.
        for _ in range(WAIT_TICKS):
            if daemon_running():
                return 0
            time.sleep(0.5)
        if newer_source_available(source):
            log("mise a jour automatique vers %s" % read_version(source))
            if run_install(source) == 0:
                start_service()
                return 0
        serve_web(source)
        return 1

    if source is None:
        log("dossier du projet introuvable dans %s" % SHARE)
        log("copiez le dossier recalbox-rfid sur le partage puis redemarrez.")
        return 1

    log("installation automatique depuis %s" % source)
    if run_install(source) != 0:
        log("installation en echec : ouverture de l'interface web")
        serve_web(source)
        return 1

    if not spi_active() and spi_configured():
        if game_running():
            log("un jeu est en cours : redemarrage reporte, activez le SPI plus tard")
            start_service()
            return 0
        reboot_system()
        return 0

    start_service()
    return 0


if __name__ == "__main__":
    sys.exit(main())
