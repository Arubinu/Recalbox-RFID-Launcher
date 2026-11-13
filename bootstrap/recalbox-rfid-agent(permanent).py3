#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recalbox permanent script: automatic installation + management agent.

Setup (once):

1. copy the files to the share (the page or the `.cmd` installer does it);
2. reboot Recalbox, or on Recalbox 10 run "Install-RFID-reader" from the
   user scripts menu (it starts this script without a reboot).

At startup, this script:

* installs the launcher if it is missing (and enables the SPI bus);
* installs the version found on the share if it is newer;
* reboots Recalbox once if SPI has just been enabled (never during a game:
  the reboot is then postponed);
* starts the RFID service;
* then runs the WebSocket agent that lets `installer.html` manage the badges.

No interface is served by the Recalbox: only the WebSocket agent, open to a
computer once it has been authorized with a 3 s press on the box button.
"""

import glob
import os
import subprocess
import sys
import time

#: Install folder (can be overridden with the RFID_HOME variable).
RFID_HOME = os.environ.get("RFID_HOME", "/recalbox/share/system/rfid")

#: Share root where the project folder is looked for.
SHARE = "/recalbox/share"

#: Boot configuration file (SPI is enabled here).
BOOT_CONFIG = "/boot/recalbox-user-config.txt"

#: Frontend state file (so as not to reboot during a game).
STATE_FILE = "/tmp/es_state.inf"

#: Maximum duration of an installation (seconds).
INSTALL_TIMEOUT = 900

#: Delay before the automatic reboot (seconds).
REBOOT_DELAY = 8


# ---------------------------------------------------------------------------
# Logging (the script is started by Recalbox, without a console)
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
# Installation state
# ---------------------------------------------------------------------------
def main_py(home=None):
    return os.path.join(home or RFID_HOME, "app", "main.py")


def installed():
    return os.path.isfile(main_py())


def version_tuple(value):
    """Converts "1.2.0" into (1, 2, 0); non-numeric parts count as 0."""
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
    if not source_version:
        return False
    try:
        return version_tuple(source_version) > version_tuple(read_version(RFID_HOME))
    except ValueError:
        return False


def find_source():
    """Looks for the project folder (app/main.py + install.sh) on the share."""
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
# Hardware / system
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
            return "State=playing" in handle.read()
    except OSError:
        return False


def needs_reboot():
    return not spi_active() and spi_configured()


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
        log("demarrage du service impossible : %s" % exc)


def launch_agent(source):
    """Runs the management agent (from the install if possible, else from the share)."""
    if installed():
        os.execv(sys.executable, [sys.executable, main_py(), "agent", "--home", RFID_HOME])
        return
    if source:
        os.execv(
            sys.executable,
            [sys.executable, os.path.join(source, "app", "main.py"),
             "agent", "--home", RFID_HOME, "--source", source],
        )


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

    if installed():
        if newer_source_available(source):
            log("mise a jour automatique vers %s" % read_version(source))
            if run_install(source) != 0:
                log("mise a jour en echec (l'installation actuelle reste utilisee)")
            else:
                start_service()
        launch_agent(source)
        return 1

    if source is None:
        log("dossier du projet introuvable dans %s" % SHARE)
        log("copiez le dossier recalbox-rfid sur le partage puis redemarrez.")
        return 1

    log("installation automatique depuis %s" % source)
    if run_install(source) != 0:
        log("installation en echec : le service est demarre quand meme")
        start_service()       # the agent and the reader stay usable
        launch_agent(source)  # agent from the share, for diagnosis
        return 1

    if needs_reboot():
        if game_running():
            log("un jeu est en cours : redemarrage reporte")
            start_service()
        else:
            reboot_system()
            return 0
    else:
        start_service()

    launch_agent(source)
    return 1


if __name__ == "__main__":
    sys.exit(main())
