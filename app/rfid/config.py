"""Service configuration (INI file).

The default file is written by the installer to
``/recalbox/share/system/rfid/config.ini``. It is the only file the user has
to edit to change a pin or turn the sound off (most settings are also
available in the page's Settings tab).
"""

from __future__ import annotations

import configparser
import os
import re

DEFAULT_CONFIG_TEXT = """\
# ==============================================================================
#  Recalbox RFID Launcher  --  configuration
#  File: /recalbox/share/system/rfid/config.ini
#
#  After a change:  sh /recalbox/share/system/rfid/rfidctl restart
# ==============================================================================

[general]
# Log level: DEBUG, INFO, WARNING or ERROR
log_level = INFO
# Maximum log size before rotation (bytes)
log_max_bytes = 1048576

[rfid]
# SPI port of the RC522 reader (reader wired to CE0 = physical pin 24)
spi_device = /dev/spidev0.0
spi_speed_hz = 1000000
# GPIO pin of the RC522 RST (BCM). Set -1 if the pin is not wired.
reset_pin = 25
# Interval between two reader polls (milliseconds)
poll_interval_ms = 150
# Time during which the same badge is ignored (seconds)
same_tag_cooldown_s = 2.5
# "Cartridge" mode: a badge left on the reader triggers the action only once.
# It must be away for this long (milliseconds) to be scanned again and repeat
# the action.
rearm_absent_ms = 1200

[button]
# Pairing push button: wired between the pin and GND.
# The Raspberry Pi internal pull-up is enabled: no resistor needed.
enabled = 1
pin = 17
# Time (seconds) given to scan the badge after a press
arm_timeout_s = 10
# Hold time (seconds) that authorizes a browser to drive the Recalbox.
# The authorization is sent as soon as it is reached, without waiting for release.
hold_press_s = 3
# Debounce (milliseconds)
debounce_ms = 40

[display]
# What the TV shows: "recalbox" = Recalbox's interface, "reader" = the reader
# screen (consoles, active player); games then start with the cards only
mode = recalbox
# Reader screen: the quit hotkey and the RetroArch menu are turned off during
# the games (only with stop_on_remove: removing the card quits the game)
no_quit_hotkey = 0
# Reader screen resolution: "recalbox" = the one of Recalbox's interface and
# games (no mode change, no black flash), "native" = the screen's own (sharper)
resolution = recalbox
# Reader screen: the game is shown (picture, name) before it starts
show_game = 1
# Reader screen: the game shown starts only when a controller button is pressed
confirm_with_pad = 0
# Reader screen: when a player is active, their own games instead of the consoles
player_games = 0

[launch]
# The Recalbox frontend listens for the "START|system|game" command on this UDP port
udp_host = 127.0.0.1
udp_port = 1337
# Do not start a game if a game is already running
ignore_when_game_running = 1
# Quit the game when the badge is removed from the reader (0 = no)
stop_on_remove = 0
# Save the game (RetroArch save state) before the reader quits it, and resume
# it at the next launch of the game (0 = no)
save_on_quit = 1
# Action when an already registered badge is scanned:
#   launch = starts the game (historical behaviour)
#   none   = starts nothing: confirmation beep and log only
# (The Recalbox frontend only accepts the START command: there is no official
#  command to "open the game page" without starting it.)
action = launch

[feedback]
# Confirmation beeps (paplay or aplay, shipped with Recalbox)
sound = 1
# auto, paplay, aplay or none
sound_player = auto

[time]
# Play time allowed by a game card that has no limit of its own
# (minutes, 0 = no limit). Warnings 5 and 1 minute before the end.
default_limit_min = 0

[screen]
# Messages on the game screen (time left, bonus, access request...).
# Shown by RetroArch during a game; the Recalbox menu cannot show them.
messages = 1
# RetroArch network command port
retroarch_port = 55355

[led]
# Status light: none, rgb (RGB LED on 3 GPIO pins) or ws2812 (programmable
# LEDs on the second SPI bus, data on GPIO20 = physical pin 38).
type = none
# RGB LED: GPIO pins (BCM) of the red, green and blue legs
pin_red = 22
pin_green = 23
pin_blue = 24
# Shared leg of the RGB LED: cathode (to GND) or anode (to 3.3 V)
common = cathode
# Programmable LEDs: number of LEDs, brightness (%), SPI port
count = 1
brightness = 40
spi_device = /dev/spidev1.0
# Light on (green) when nothing happens (0 = off at rest)
idle = 1

[agent]
# WebSocket agent used by installer.html (ws://recalbox.local:8765)
enabled = 1
port = 8765
# Serve the management page to phones and tablets (http://recalbox.local:8765/).
# 0 = only the page saved on a computer can connect.
web = 1

[players]
# Player cards: each person places their card before playing; the time
# played is counted per player (quota per day or week, set on the card).
enabled = 0
# Quit the games started without a player card (from the menu too).
require = 0
# Quit the games of a player whose time is used up, even when started from
# the Recalbox menu.
block_exhausted = 1
# Play time without a player card, per period (minutes, 0 = no limit).
guest_quota_min = 0
# day or week
guest_period = day
# The play time counters restart at this hour (0-23, 0 = midnight), and the
# weekly ones on this day (monday ... sunday).
reset_hour = 0
week_start = monday
# The player of a card stays active for the next games (no need to place the
# card again), until their time is up, another player card or the unlock card.
keep_active = 0
# A player card placed during another player's game takes the game over: the
# time counts for the new player from then on (0 = it is for the next game).
switch_on_card = 0
# Locks the Recalbox menu: favourite games only, no START menu (the page
# applies it to recalbox.conf and restarts the menu).
lock_frontend = 0

[cards]
# Card designer: box art, screenshot, title screen and game logo downloaded
# from the libretro thumbnail server (needs internet, no account).
# 0 = only the pictures of the Recalbox.
online_art = 1

[update]
# URL of the update ZIP file (see docs/UPDATING.md). Optional.
url =
# Check for updates when the service starts (0/1)
check_on_start = 0
"""


class ConfigError(Exception):
    """Error while reading the configuration file."""


class Config:
    """Read access to the configuration (and writing of the template)."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._data = {}
        self.reload()

    # ------------------------------------------------------------------ reading
    def reload(self) -> None:
        """Reloads the file; missing values take their default."""
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

    # ---------------------------------------------------------------- writing
    def create_default(self, overwrite: bool = False) -> bool:
        """Writes the configuration template. True if the file was written."""
        if self.exists() and not overwrite:
            return False
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(DEFAULT_CONFIG_TEXT)
        self.reload()
        return True

    def write_values(self, values: dict) -> list:
        """Updates keys in the file while keeping its layout.

        ``values`` maps "section.key" to the new value. Returns the list of the keys
        really changed. Missing keys are added at the end of their section (the
        section is created when needed).
        """
        chemin = self.path
        try:
            with open(chemin, "r", encoding="utf-8") as handle:
                lignes = handle.read().split("\n")
        except OSError:
            lignes = []
        modifiees = []
        a_ajouter = {}
        for cle_complete, valeur in values.items():
            if "." not in cle_complete:
                raise ConfigError("cle invalide : %s" % cle_complete)
            section, cle = cle_complete.split(".", 1)
            valeur = str(valeur).strip()
            section_courante = None
            trouvee = False
            for index, ligne in enumerate(lignes):
                depouillee = ligne.strip()
                if depouillee.startswith("[") and depouillee.endswith("]"):
                    section_courante = depouillee[1:-1].strip()
                    continue
                if section_courante != section:
                    continue
                if not depouillee or depouillee.startswith(("#", ";")):
                    continue
                if re.match(r"^%s\s*=" % re.escape(cle), depouillee):
                    indent = ligne[: len(ligne) - len(ligne.lstrip())]
                    lignes[index] = "%s%s = %s" % (indent, cle, valeur)
                    trouvee = True
                    break
            if not trouvee:
                a_ajouter.setdefault(section, []).append("%s = %s" % (cle, valeur))
            if trouvee:
                modifiees.append(cle_complete)
        for section, nouvelles in a_ajouter.items():
            entete = "[%s]" % section
            if entete in (ligne.strip() for ligne in lignes):
                index = next(i for i, ligne in enumerate(lignes) if ligne.strip() == entete)
                fin = index + 1
                while fin < len(lignes) and not lignes[fin].strip().startswith("["):
                    fin += 1
                while fin > index + 1 and not lignes[fin - 1].strip():
                    fin -= 1
                lignes[fin:fin] = nouvelles
            else:
                if lignes and lignes[-1].strip():
                    lignes.append("")
                lignes.append(entete)
                lignes.extend(nouvelles)
            modifiees.extend("%s.%s" % (section, ligne.split("=")[0].strip()) for ligne in nouvelles)
        temporaire = chemin + ".tmp"
        try:
            with open(temporaire, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lignes))
            os.replace(temporaire, chemin)
        except OSError as exc:
            raise ConfigError("ecriture impossible : %s" % exc)
        self.reload()
        return modifiees

    def get_list(self, section: str, key: str) -> list:
        raw = self.get(section, key, "")
        return [item.strip() for item in raw.split(",") if item.strip()]
