"""Configuration du service (fichier INI).

Le fichier par defaut est ecrit par l'installeur dans
``/recalbox/share/system/rfid/config.ini``. Il est volontairement commente en
francais : c'est le seul fichier que l'utilisateur doit modifier pour changer
une broche ou desactiver le son.
"""

from __future__ import annotations

import configparser
import os

DEFAULT_CONFIG_TEXT = """\
# ==============================================================================
#  Recalbox RFID Launcher  --  configuration
#  Fichier : /recalbox/share/system/rfid/config.ini
#
#  Apres une modification :  sh /recalbox/share/system/rfid/rfidctl restart
# ==============================================================================

[general]
# Niveau du journal : DEBUG, INFO, WARNING ou ERROR
log_level = INFO
# Taille maximale du journal avant rotation (octets)
log_max_bytes = 1048576

[rfid]
# Port SPI du lecteur RC522 (lecteur branche sur CE0 = broche physique 24)
spi_device = /dev/spidev0.0
spi_speed_hz = 1000000
# Broche GPIO du RST du RC522 (BCM). Mettre -1 si la broche n'est pas branchee.
reset_pin = 25
# Intervalle entre deux interrogations du lecteur (millisecondes)
poll_interval_ms = 150
# Duree pendant laquelle le meme badge est ignore (secondes)
same_tag_cooldown_s = 2.5
# Mode "cartouche" : un badge laisse sur le lecteur ne declenche l'action qu'une
# seule fois. Il faut l'eloigner ce temps-la (millisecondes) pour pouvoir le
# rescanner et refaire l'action.
rearm_absent_ms = 1200

[button]
# Bouton poussoir d'association : branche entre la broche et GND.
# Le pull-up interne du Raspberry Pi est active : aucune resistance necessaire.
enabled = 1
pin = 17
# Delai (secondes) accorde pour scanner le badge apres un appui
arm_timeout_s = 10
# Anti-rebond (millisecondes)
debounce_ms = 40

[launch]
# Le frontend Recalbox ecoute la commande "START|systeme|jeu" sur ce port UDP
udp_host = 127.0.0.1
udp_port = 1337
# Ne pas lancer de jeu si un jeu tourne deja
ignore_when_game_running = 1
# Action quand un badge deja enregistre est scanne :
#   launch = lance le jeu (comportement historique)
#   none   = ne lance rien : bip de confirmation et journal seulement
# (Le frontend Recalbox n'accepte que la commande START : il n'existe pas de
#  commande officielle pour "ouvrir la fiche du jeu" sans le lancer.)
action = launch

[feedback]
# Bips sonores de confirmation (paplay ou aplay, fourni par Recalbox)
sound = 1
# auto, paplay, aplay ou none
sound_player = auto

[agent]
# Agent WebSocket utilise par installer.html (ws://recalbox.local:8765)
enabled = 1
port = 8765

[update]
# URL du fichier ZIP de mise a jour (voir docs/MISE-A-JOUR.md). Facultatif.
url =
# Verifier les mises a jour au demarrage du service (0/1)
check_on_start = 0
"""


class ConfigError(Exception):
    """Erreur de lecture du fichier de configuration."""


class Config:
    """Acces en lecture (et reecriture du modele) a la configuration."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._data = {}
        self.reload()

    # ------------------------------------------------------------------ lecture
    def reload(self) -> None:
        """Recharge le fichier ; les valeurs absentes prennent le defaut."""
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(DEFAULT_CONFIG_TEXT)

        if os.path.isfile(self.path):
            user = configparser.ConfigParser(interpolation=None)
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    user.read_file(handle)
            except (OSError, configparser.Error) as exc:
                raise ConfigError("Impossible de lire %s : %s" % (self.path, exc))
            for section in user.sections():
                if not parser.has_section(section):
                    parser.add_section(section)
                for key, value in user.items(section):
                    parser.set(section, key, value)

        self._data = {section: dict(parser.items(section)) for section in parser.sections()}

    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def get(self, section: str, key: str, default: str = "") -> str:
        try:
            return self._data[section][key].strip()
        except KeyError:
            return default

    def get_int(self, section: str, key: str, default: int = 0) -> int:
        raw = self.get(section, key, str(default))
        try:
            return int(raw)
        except ValueError:
            return default

    def get_float(self, section: str, key: str, default: float = 0.0) -> float:
        raw = self.get(section, key, str(default))
        try:
            return float(raw)
        except ValueError:
            return default

    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        raw = self.get(section, key, "1" if default else "0").lower()
        return raw in ("1", "yes", "true", "on", "oui")

    def section(self, section: str) -> dict:
        return dict(self._data.get(section, {}))

    def section_list(self) -> list:
        return list(self._data.keys())

    def default_text(self) -> str:
        return DEFAULT_CONFIG_TEXT

    # ---------------------------------------------------------------- ecriture
    def create_default(self, overwrite: bool = False) -> bool:
        """Ecrit le modele de configuration. True si le fichier a ete ecrit."""
        if self.exists() and not overwrite:
            return False
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(DEFAULT_CONFIG_TEXT)
        self.reload()
        return True

    def get_list(self, section: str, key: str) -> list:
        raw = self.get(section, key, "")
        return [item.strip() for item in raw.split(",") if item.strip()]
