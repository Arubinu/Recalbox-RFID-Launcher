"""Constantes partagees du projet."""

from __future__ import annotations

import os

#: Dossier d'installation par defaut sur Recalbox (persistant, visible depuis
#: le partage reseau Windows : \\\\RECALBOX\\share\\system\\rfid).
DEFAULT_HOME = "/recalbox/share/system/rfid"

#: Fichier d'etat ecrit par le frontend Recalbox a chaque evenement.
ES_STATE_FILE = "/tmp/es_state.inf"

#: Commande UDP officielle du frontend Recalbox (Recalbox 9 et suivants).
ES_UDP_HOST = "127.0.0.1"
ES_UDP_PORT = 1337

#: Verrou empechant deux instances du service (tmpfs, remis a zero au reboot).
LOCK_FILE = "/var/run/rfid-launcher.lock"

#: Nom du fichier de configuration.
CONFIG_FILENAME = "config.ini"

#: Nom du fichier de base de donnees.
DB_FILENAME = "tags.json"

#: Dossier des journaux.
LOG_DIRNAME = "logs"


def home_dir() -> str:
    """Retourne le dossier de travail (surchargeable avec RFID_HOME)."""
    return os.environ.get("RFID_HOME", DEFAULT_HOME)


def config_path() -> str:
    return os.path.join(home_dir(), CONFIG_FILENAME)


def db_path() -> str:
    return os.path.join(home_dir(), DB_FILENAME)


def log_dir() -> str:
    return os.path.join(home_dir(), LOG_DIRNAME)
