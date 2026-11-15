"""The reader screen: shown instead of Recalbox's interface (option).

An attract screen drawn with pygame (SDL2, the same library as Recalbox's
interface) from the Recalbox theme itself: one console at a time in the
spotlight (its drawing, its logo, its number of games, on a glow of its
colour), a band with the logos of every console that has games, the clock,
and the active player with their play time. Games start with the cards.

No sound is opened. The controllers are read only (a game shown waits for a
button, START + SELECT open the power menu); the screen quits before each
game, so it never holds a device the game needs. It quits on SIGTERM (the
service stops it before a game and starts it again afterwards).

``RFID_SCREEN_ASSETS`` points to a copy of the theme files (preview on a
computer: ``python -m rfid.screen --preview out.png``).
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import signal
import sys
import threading
import time

from .es_command import ROMS_DIRS, read_conf
from .osd import recalbox_language

STATUS_FILENAME = "status.json"
THEME = "/recalbox/share_init/system/.emulationstation/themes/recalbox-next/data"
PATHS = {
    "systemlist": "/recalbox/share_init/system/.emulationstation/systemlist.xml",
    "logos": "/recalbox/system/resources/logos",
    "arts": THEME + "/arts/systems_assets",
    "fonts": THEME + "/fonts",
}
#: Seconds a console stays in the spotlight, and length of the change.
HOLD_S = 7.0
FADE_S = 0.9
#: The chosen logo of the band lights up over this time, once the band has stopped.
HIGHLIGHT_S = 0.35

TEXTS = {
    "hint": {"fr": "Pose une carte pour jouer", "en": "Place a card to play", "de": "Leg eine Karte auf, um zu spielen",
             "es": "Pon una tarjeta para jugar", "it": "Appoggia una carta per giocare", "pt": "Pousa um cartão para jogar"},
    "games": {"fr": "jeux", "en": "games", "de": "Spiele", "es": "juegos", "it": "giochi", "pt": "jogos"},
    "game": {"fr": "jeu", "en": "game", "de": "Spiel", "es": "juego", "it": "gioco", "pt": "jogo"},
    "left": {"fr": "{t} restantes", "en": "{t} left", "de": "noch {t}", "es": "quedan {t}", "it": "{t} rimasti",
             "pt": "faltam {t}"},
    "unlimited": {"fr": "sans limite", "en": "no limit", "de": "ohne Limit", "es": "sin límite", "it": "senza limiti",
                  "pt": "sem limite"},
    "played": {"fr": "{t} jouées aujourd'hui", "en": "{t} played today", "de": "heute {t} gespielt",
               "es": "{t} jugados hoy", "it": "{t} giocati oggi", "pt": "{t} jogados hoje"},
    "played_week": {"fr": "{t} jouées cette semaine", "en": "{t} played this week", "de": "diese Woche {t} gespielt",
                    "es": "{t} jugados esta semana", "it": "{t} giocati questa settimana", "pt": "{t} jogados esta semana"},
    "guest": {"fr": "Invité", "en": "Guest", "de": "Gast", "es": "Invitado", "it": "Ospite", "pt": "Convidado"},
    "launching": {"fr": "Lancement…", "en": "Starting…", "de": "Wird gestartet…", "es": "Iniciando…",
                  "it": "Avvio…", "pt": "A iniciar…"},
    "press": {"fr": "Appuie sur un bouton de la manette pour jouer", "en": "Press a controller button to play",
              "de": "Drück eine Taste am Controller, um zu spielen", "es": "Pulsa un botón del mando para jugar",
              "it": "Premi un tasto del controller per giocare", "pt": "Carrega num botão do comando para jogar"},
    "cancel_hint": {"fr": "Retire la carte pour annuler", "en": "Remove the card to cancel",
                    "de": "Karte entfernen zum Abbrechen", "es": "Retira la tarjeta para cancelar",
                    "it": "Togli la carta per annullare", "pt": "Retira o cartão para cancelar"},
    "player_games": {"fr": "Les jeux de {name}", "en": "{name}'s games", "de": "Die Spiele von {name}",
                     "es": "Los juegos de {name}", "it": "I giochi di {name}", "pt": "Os jogos de {name}"},
    "no_games": {"fr": "Pas encore de jeu joué : pose une carte !", "en": "No game played yet: place a card!",
                 "de": "Noch kein Spiel gespielt: leg eine Karte auf!", "es": "Aún no hay juegos: ¡pon una tarjeta!",
                 "it": "Ancora nessun gioco: appoggia una carta!", "pt": "Ainda sem jogos: pousa um cartão!"},
    "next": {"fr": "prochaine partie", "en": "next game", "de": "nächstes Spiel", "es": "próxima partida",
             "it": "prossima partita", "pt": "próximo jogo"},
    "consoles": {"fr": "{n} consoles", "en": "{n} consoles", "de": "{n} Konsolen", "es": "{n} consolas",
                 "it": "{n} console", "pt": "{n} consolas"},
    "power_title": {"fr": "Éteindre ou redémarrer ?", "en": "Turn off or restart?", "de": "Ausschalten oder neu starten?",
                    "es": "¿Apagar o reiniciar?", "it": "Spegnere o riavviare?", "pt": "Desligar ou reiniciar?"},
    "power_title_off": {"fr": "Éteindre la console ?", "en": "Turn the console off?", "de": "Konsole ausschalten?",
                        "es": "¿Apagar la consola?", "it": "Spegnere la console?", "pt": "Desligar a consola?"},
    "poweroff": {"fr": "Éteindre", "en": "Turn off", "de": "Ausschalten", "es": "Apagar", "it": "Spegni",
                 "pt": "Desligar"},
    "reboot": {"fr": "Redémarrer", "en": "Restart", "de": "Neu starten", "es": "Reiniciar", "it": "Riavvia",
               "pt": "Reiniciar"},
    "cancel": {"fr": "Annuler", "en": "Cancel", "de": "Abbrechen", "es": "Cancelar", "it": "Annulla", "pt": "Cancelar"},
    "menu_hint": {"fr": "Croix pour choisir, un bouton pour valider", "en": "D-pad to choose, a button to confirm",
                  "de": "Steuerkreuz zum Wählen, eine Taste zum Bestätigen",
                  "es": "Cruceta para elegir, un botón para aceptar",
                  "it": "Croce per scegliere, un tasto per confermare",
                  "pt": "Direcional para escolher, um botão para confirmar"},
    "off_in": {"fr": "Extinction dans {n} s", "en": "Turning off in {n} s", "de": "Ausschalten in {n} s",
               "es": "Apagado en {n} s", "it": "Spegnimento tra {n} s", "pt": "A desligar em {n} s"},
    "reboot_in": {"fr": "Redémarrage dans {n} s", "en": "Restarting in {n} s", "de": "Neustart in {n} s",
                  "es": "Reinicio en {n} s", "it": "Riavvio tra {n} s", "pt": "A reiniciar em {n} s"},
    "press_cancel": {"fr": "Appuie sur un bouton de la manette pour annuler", "en": "Press a controller button to cancel",
                     "de": "Drück eine Controller-Taste zum Abbrechen", "es": "Pulsa un botón del mando para cancelar",
                     "it": "Premi un tasto del controller per annullare", "pt": "Carrega num botão do comando para cancelar"},
    "tip_power": {"fr": "START + SELECT : éteindre ou redémarrer", "en": "START + SELECT: turn off or restart",
                  "de": "START + SELECT: ausschalten oder neu starten", "es": "START + SELECT: apagar o reiniciar",
                  "it": "START + SELECT: spegnere o riavviare", "pt": "START + SELECT: desligar ou reiniciar"},
    "tip_power_off": {"fr": "START + SELECT : éteindre la console", "en": "START + SELECT: turn the console off",
                      "de": "START + SELECT: Konsole ausschalten", "es": "START + SELECT: apagar la consola",
                      "it": "START + SELECT: spegnere la console", "pt": "START + SELECT: desligar a consola"},
    "favourite": {"fr": "Jeu préféré de {name} : {game}", "en": "{name}'s favourite game: {game}",
                  "de": "Lieblingsspiel von {name}: {game}", "es": "Juego favorito de {name}: {game}",
                  "it": "Gioco preferito di {name}: {game}", "pt": "Jogo favorito de {name}: {game}"},
    "week_game": {"fr": "Jeu de la semaine : {game}", "en": "Game of the week: {game}", "de": "Spiel der Woche: {game}",
                  "es": "Juego de la semana: {game}", "it": "Gioco della settimana: {game}",
                  "pt": "Jogo da semana: {game}"},
    "trophy_count": {"fr": "{name} : {n} trophée(s), dernier : {what}", "en": "{name}: {n} trophy(ies), last: {what}",
                     "de": "{name}: {n} Trophäe(n), zuletzt: {what}", "es": "{name}: {n} trofeo(s), último: {what}",
                     "it": "{name}: {n} trofeo/i, ultimo: {what}", "pt": "{name}: {n} troféu(s), último: {what}"},
    "t_consoles": {"fr": "{n} consoles", "en": "{n} consoles", "de": "{n} Konsolen", "es": "{n} consolas",
                   "it": "{n} console", "pt": "{n} consolas"},
    "t_games": {"fr": "{n} jeux", "en": "{n} games", "de": "{n} Spiele", "es": "{n} juegos", "it": "{n} giochi",
                "pt": "{n} jogos"},
    "t_streak": {"fr": "{n} jours d'affilée", "en": "{n} days in a row", "de": "{n} Tage am Stück",
                 "es": "{n} días seguidos", "it": "{n} giorni di fila", "pt": "{n} dias seguidos"},
    "t_hours": {"fr": "{n} heures de jeu", "en": "{n} hours of play", "de": "{n} Stunden Spielzeit",
                "es": "{n} horas de juego", "it": "{n} ore di gioco", "pt": "{n} horas de jogo"},
    "good_night": {"fr": "C'est l'heure de dormir : bonne nuit !", "en": "Bedtime: good night!",
                   "de": "Schlafenszeit: gute Nacht!", "es": "Hora de dormir: ¡buenas noches!",
                   "it": "È ora di dormire: buonanotte!", "pt": "Hora de dormir: boa noite!"},
    "idle_cancel": {"fr": "Personne ne joue : un bouton ou une carte annule",
                    "en": "Nobody is playing: a button or a card cancels",
                    "de": "Niemand spielt: eine Taste oder eine Karte bricht ab",
                    "es": "Nadie juega: un botón o una tarjeta cancela",
                    "it": "Nessuno gioca: un tasto o una carta annulla",
                    "pt": "Ninguém está a jogar: um botão ou um cartão cancela"},
}

BACKGROUND = (10, 12, 17)
TEXT = (240, 243, 248)
MUTED = (150, 158, 175)
FAINT = (92, 100, 116)
DEFAULT_ACCENT = (84, 112, 246)
PLATE = (244, 245, 248, 255)
#: Messages of the service (see osd.py), shown as a toast.
MESSAGE_FILE = "/tmp/rfid-screen-message.json"
TOAST_S = 5.0
#: A message older than this when the screen reads it is not shown.
MESSAGE_MAX_AGE_S = 8.0
#: How long the screen waits for a busy display (boot) before giving up.
DISPLAY_WAIT_S = 60.0


def text(key: str, language: str, **values) -> str:
    entry = TEXTS.get(key, {})
    value = entry.get(language) or entry.get("en") or key
    for name, replacement in values.items():
        value = value.replace("{" + name + "}", str(replacement))
    return value


def duration(seconds) -> str:
    minutes = max(0, int(round((seconds or 0) / 60.0)))
    if minutes < 60:
        return "%d min" % minutes
    return "%d h %02d" % (minutes // 60, minutes % 60)


def paths() -> dict:
    root = os.environ.get("RFID_SCREEN_ASSETS")
    if not root:
        return dict(PATHS)
    return {"systemlist": os.path.join(root, "systemlist.xml"), "logos": os.path.join(root, "logos"),
            "arts": os.path.join(root, "arts"), "fonts": os.path.join(root, "fonts")}


# ------------------------------------------------------------------ data
def count_games(roms_dirs=ROMS_DIRS, systemlist: str = None) -> list:
    """Consoles that have games, in the Recalbox order:
    [{"id", "name", "count", "maker", "year"}].

    The files with an extension of the console (as Recalbox's interface
    counts them), in the console folder and its sub-folders.
    """
    found = []
    try:
        from xml.etree import ElementTree
        root = ElementTree.parse(systemlist or paths()["systemlist"]).getroot()
    except Exception:  # noqa: BLE001 - no list: nothing to show
        return found
    for node in root.iter("system"):
        name = node.get("name") or ""
        descriptor = node.find("descriptor")
        if not name or descriptor is None:
            continue
        extensions = tuple(ext.lower().rstrip("!") for ext in (descriptor.get("extensions") or "").split())
        if not extensions:
            continue
        seen = set()
        for base in roms_dirs:
            folder = os.path.join(base, name)
            if not os.path.isdir(folder):
                continue
            for path, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("media", "downloaded_images")]
                for file in files:
                    if file.lower().endswith(extensions) and not file.startswith((".", "_")):
                        seen.add(os.path.relpath(os.path.join(path, file), folder).lower())
        if seen:
            properties = node.find("properties")
            props = properties.attrib if properties is not None else {}
            found.append({"id": name, "name": node.get("fullname") or name, "count": len(seen),
                          "maker": props.get("manufacturer", ""), "year": (props.get("releasedate") or "")[:4]})
    return found


def read_players(home: str) -> dict:
    try:
        with open(os.path.join(home, STATUS_FILENAME), "r", encoding="utf-8") as handle:
            return json.load(handle).get("players") or {}
    except (OSError, ValueError):
        return {}


def player_info(players: dict, language: str):
    """{"name", "uid", "detail", "ratio"} of the active or waiting player
    (or of the guest when the guest has a time limit), or None.

    detail: the time left when the player has a limit, otherwise the time
    played today (or this week).
    """
    current = players.get("current") or {}
    rows = {row.get("uid"): row for row in players.get("players") or []}
    uid = current.get("uid") if current.get("uid") != "guest" else None
    waiting = False
    if not current.get("uid") and players.get("pending"):
        uid, waiting = players.get("pending_uid"), True
    if uid or waiting:
        row = rows.get(uid, {})
        name = current.get("name") or players.get("pending") or row.get("name") or ""
        info = {"name": name, "uid": uid or "", "ratio": None, "avatar": row.get("avatar", 0)}
        quota = (row.get("quota_min") or 0) * 60
        if quota and row.get("remaining_s") is not None:
            left = max(0, row.get("remaining_s") or 0)
            info.update(detail=text("left", language, t=duration(left)), ratio=left / float(quota))
        elif row.get("used_s", 0) >= 60:
            key = "played_week" if row.get("period") == "week" else "played"
            info["detail"] = text(key, language, t=duration(row["used_s"]))
        else:
            info["detail"] = text("next" if waiting else "unlimited", language)
        return info
    guest = players.get("guest") or {}
    if guest.get("quota_min"):
        left = max(0, guest.get("remaining_s") or 0)
        return {"name": text("guest", language), "uid": "", "ratio": left / float(guest["quota_min"] * 60),
                "detail": text("left", language, t=duration(left))}
    return None


LAUNCH_FILE = "/tmp/rfid-screen-launch.json"
ANSWER_FILE = "/tmp/rfid-screen-answer.json"


class Watcher:
    """A JSON file written by the service, read when it changes (one stat per call)."""

    def __init__(self, path: str, wall=None, max_age: float = 8.0):
        self.path = path
        self.wall = wall or time.time
        self.max_age = max_age
        self.stamp = None

    def poll(self):
        try:
            stamp = os.stat(self.path).st_mtime_ns
        except OSError:
            return None
        if stamp == self.stamp:
            return None
        self.stamp = stamp
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or abs(self.wall() - float(data.get("at") or 0)) > self.max_age:
            return None
        return data


def answer_go(path: str = ANSWER_FILE) -> None:
    """A controller button: the game shown may start."""
    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump({"answer": "go", "at": time.time()}, handle)
        os.replace(temporary, path)
    except OSError:
        pass


_IMAGES = {}


def find_image(system: str, name: str, roms_dirs=ROMS_DIRS) -> str:
    """Scraped picture of a game known by its name (gamelist.xml), or ""."""
    if system not in _IMAGES:
        found = {}
        try:
            from xml.etree import ElementTree
        except ImportError:  # pragma: no cover
            ElementTree = None
        for base in roms_dirs if ElementTree is not None else ():
            folder = os.path.join(base, system)
            try:
                root = ElementTree.parse(os.path.join(folder, "gamelist.xml")).getroot()
            except Exception:  # noqa: BLE001 - no list here
                continue
            for node in root.iter("game"):
                picture = (node.findtext("thumbnail") or node.findtext("image") or "").strip()
                if not picture:
                    continue
                full = os.path.normpath(os.path.join(folder, picture))
                path = (node.findtext("path") or "").strip()
                for key in ((node.findtext("name") or "").strip(), os.path.splitext(os.path.basename(path))[0]):
                    if key and key not in found:
                        found[key] = full
        _IMAGES[system] = found
    path = _IMAGES[system].get(name, "")
    return path if path and os.path.isfile(path) else ""


def player_games(home: str, uid: str, limit: int = 6, days: int = 30) -> list:
    """The games of a player, last played first: [{"system", "name", "seconds", "image"}]."""
    from .players import read_file

    _usage, games = read_file(os.path.join(home, "players.json"))
    first = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    table = {}
    for day, played in (games.get(uid) or {}).items():
        if day < first:
            continue
        for key, seconds in played.items():
            entry = table.setdefault(key, {"seconds": 0.0, "last": ""})
            entry["seconds"] += seconds
            entry["last"] = max(entry["last"], day)
    ordered = sorted(table.items(), key=lambda item: (item[1]["last"], item[1]["seconds"]), reverse=True)
    result = []
    for key, entry in ordered[:limit]:
        system, name = key.split("|", 1)
        result.append({"system": system, "name": name, "seconds": entry["seconds"], "image": find_image(system, name)})
    return result


#: A game shown for the controller stays readable this long after it was written.
CONFIRM_MAX_AGE_S = 30.0


def open_pads(pygame) -> list:
    """The controllers, to read their buttons (game started with the controller)."""
    try:
        pygame.joystick.init()
        return [pygame.joystick.Joystick(number) for number in range(pygame.joystick.get_count())]
    except Exception:  # noqa: BLE001 - no controller support: the card only
        return []


#: The controllers as set up in Recalbox (which button is START, SELECT, A...).
ES_INPUT = "/recalbox/share/system/.emulationstation/es_input.cfg"
#: A stick pushed this far counts as a direction.
AXIS_DEAD = 0.6
#: Hat bits in Recalbox's settings (SDL): up, right, down, left.
HAT_BITS = {1: (0, 1), 2: (1, 0), 4: (0, -1), 8: (-1, 0)}
#: Without settings for a controller: the usual layout of the directions.
FALLBACK_INPUTS = {"up": [("hat", 0, 1), ("axis", 1, -1)], "down": [("hat", 0, 4), ("axis", 1, 1)]}


def pad_settings(path: str = ES_INPUT) -> list:
    """[{"guid", "name", "inputs": {name: [(type, id, value)...]}}] from Recalbox's settings."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []
    found = []
    for config in root.iter("inputConfig"):
        if config.get("type") != "joystick":
            continue
        inputs = {}
        for item in config.iter("input"):
            try:
                entry = (item.get("type"), int(item.get("id")), int(item.get("value")))
            except (TypeError, ValueError):
                continue
            inputs.setdefault(str(item.get("name") or "").lower(), []).append(entry)
        found.append({"guid": str(config.get("deviceGUID") or "").lower(),
                      "name": str(config.get("deviceName") or ""), "inputs": inputs})
    return found


def pad_inputs(settings: list, guid: str, name: str) -> dict:
    """The settings of one controller (same GUID, else same name)."""
    def bare(value):
        # Characters 4-8 hold a checksum of the name in recent SDL versions only.
        return value[:4] + value[8:] if len(value) == 32 else value

    guid = str(guid or "").lower()
    for wanted in ("guid", "bare", "name"):
        for entry in settings:
            if ((wanted == "guid" and guid and entry["guid"] == guid)
                    or (wanted == "bare" and guid and bare(entry["guid"]) == bare(guid))
                    or (wanted == "name" and name and entry["name"] == name)):
                return entry["inputs"]
    return {}


def event_names(event_type: str, number: int, value, inputs: dict) -> set:
    """The names (start, a, up...) of a controller event.

    ``event_type`` is "button" (pressed), "hat" (``value``: (x, y)) or "axis"
    (``value``: -1 or 1, the stick pushed past ``AXIS_DEAD``).
    """
    names = set()
    table = dict(FALLBACK_INPUTS)
    table.update(inputs or {})
    for name, entries in table.items():
        for kind, ident, expected in entries:
            if kind != event_type or ident != number:
                continue
            if kind == "button":
                names.add(name)
            elif kind == "hat" and expected in HAT_BITS and tuple(value) == HAT_BITS[expected]:
                names.add(name)
            elif kind == "axis" and expected and value and (expected > 0) == (value > 0):
                names.add(name)
            if name == "joystick1up" and kind == "axis" == event_type and ident == number and expected and value:
                names.add("up" if (expected > 0) == (value > 0) else "down")  # the left stick moves too
    if event_type == "button" and not inputs:
        names.add("a")  # a controller unknown to Recalbox: any button confirms
    return names


def button_of(inputs: dict, name: str):
    for kind, ident, _value in (inputs or {}).get(name, ()):
        if kind == "button":
            return ident
    return None


class PowerMenu:
    """The power menu of the reader screen (START + SELECT)."""

    #: Closed by itself after this long without a button.
    TIMEOUT_S = 20.0

    def __init__(self, actions, clock=None):
        self.clock = clock or time.monotonic
        self.items = list(actions) + ["cancel"]
        self.selected = 0
        self.touched = self.clock()

    def move(self, step: int) -> None:
        self.selected = (self.selected + step) % len(self.items)
        self.touched = self.clock()

    def choice(self) -> str:
        return self.items[self.selected]

    def expired(self) -> bool:
        return self.clock() - self.touched >= self.TIMEOUT_S


class Pads:
    """The controllers and their Recalbox settings: events -> names, START + SELECT."""

    def __init__(self, pygame, settings_path: str = ES_INPUT):
        self.pg = pygame
        self.settings = pad_settings(settings_path)
        self.open()

    def open(self) -> None:
        self.pads = {}
        for joystick in open_pads(self.pg):
            try:
                ident = joystick.get_instance_id() if hasattr(joystick, "get_instance_id") else joystick.get_id()
                guid = joystick.get_guid() if hasattr(joystick, "get_guid") else ""
                self.pads[ident] = (joystick, pad_inputs(self.settings, guid, joystick.get_name()))
            except Exception:  # noqa: BLE001 - a controller unplugged meanwhile
                continue
        self.axes = {}

    def names(self, event) -> set:
        """The names of a controller event (empty for other events)."""
        pg = self.pg
        ident = getattr(event, "instance_id", getattr(event, "joy", None))
        inputs = self.pads.get(ident, (None, {}))[1]
        if event.type == pg.JOYBUTTONDOWN:
            return event_names("button", event.button, 1, inputs)
        if event.type == pg.JOYHATMOTION:
            return event_names("hat", event.hat, event.value, inputs)
        if event.type == pg.JOYAXISMOTION:
            side = 0 if abs(event.value) < AXIS_DEAD else (1 if event.value > 0 else -1)
            key = (ident, event.axis)
            if self.axes.get(key, 0) == side:
                return set()  # still pushed: one move per push
            self.axes[key] = side
            return event_names("axis", event.axis, side, inputs) if side else set()
        return set()

    def combo(self, event) -> bool:
        """START and SELECT held together on the controller of this event."""
        if event.type != self.pg.JOYBUTTONDOWN:
            return False
        ident = getattr(event, "instance_id", getattr(event, "joy", None))
        joystick, inputs = self.pads.get(ident, (None, {}))
        start, select = button_of(inputs, "start"), button_of(inputs, "select")
        if joystick is None or start is None or select is None or event.button not in (start, select):
            return False
        try:
            return bool(joystick.get_button(start)) and bool(joystick.get_button(select))
        except Exception:  # noqa: BLE001
            return False


def setting(home: str, section: str, key: str, default: str = "") -> str:
    try:
        from .config import Config

        return Config(os.path.join(home, "config.ini")).get(section, key, default)
    except Exception:  # noqa: BLE001
        return default


def power_texts(state: dict, language: str, wall=None):
    """(title, detail) of a countdown of the service."""
    left = max(0, int(math.ceil(float(state.get("until") or 0) - (wall or time.time)())))
    title = text("off_in" if state.get("action") == "poweroff" else "reboot_in", language, n=left)
    source = state.get("source")
    detail = text({"card": "cancel_hint", "idle": "idle_cancel", "curfew": "good_night"}.get(source, "press_cancel"),
                  language)
    return title, detail


class PowerControl:
    """The power menu (START + SELECT) and the countdowns of the service, on the reader screen."""

    #: The screen tells the service that someone uses a controller (idle power-off).
    ACTIVITY_S = 10.0
    #: Presses ignored just after the menu opens (the other button of the pair).
    SETTLE_S = 0.4

    def __init__(self, home: str, language: str, pads, clock=None, wall=None, send=None, read=None):
        from . import power

        self.power = power
        self.home = home
        self.language = language
        self.pads = pads
        self.clock = clock or time.monotonic
        self.wall = wall or time.time
        self.send = send or power.request
        self.read = read or power.read_state
        self.menu = None
        self.state = None
        self.actions = ()
        self.checked_at = None
        self.polled_at = None
        self.sent_at = None
        self.opened_at = 0.0
        self.key = None

    def _send(self, action: str) -> None:
        self.send(action)
        self.sent_at = self.clock()

    def refresh_actions(self) -> None:
        now = self.clock()
        if self.checked_at is None or now - self.checked_at >= 5.0:
            self.checked_at = now
            self.actions = self.power.menu_actions(setting(self.home, "display", "power_menu", "both"))

    def handle(self, event, busy: bool = False) -> bool:
        """A controller event: True when it was for the power menu or the countdown."""
        pg = self.pads.pg
        pressed = event.type == pg.JOYBUTTONDOWN
        names = self.pads.names(event)
        if not pressed and not names:
            return False
        now = self.clock()
        if self.state is not None:
            if pressed:
                self._send("cancel")
            return True
        if self.menu is not None:
            # START and SELECT pressed together arrive as two presses: the one
            # after the opening must not confirm the first line ("Turn off").
            if pressed and (names & {"start", "select", "hotkey"} or now - self.opened_at < self.SETTLE_S):
                return True
            if "up" in names:
                self.menu.move(-1)
            elif "down" in names:
                self.menu.move(1)
            elif pressed:
                choice = self.menu.choice()
                self.menu = None
                if choice != "cancel":
                    self._send(choice)
            return True
        self.refresh_actions()
        if pressed and self.actions and not busy and self.pads.combo(event):
            self.menu = PowerMenu(self.actions, clock=self.clock)
            self.opened_at = now
            self._send("activity")
            return True
        if pressed and (self.sent_at is None or now - self.sent_at >= self.ACTIVITY_S):
            self._send("activity")
        return False

    def poll(self, busy: bool = False) -> None:
        now = self.clock()
        if self.polled_at is None or now - self.polled_at >= 0.25:
            self.polled_at = now
            self.state = self.read()
        if self.menu is not None and (busy or self.state is not None or self.menu.expired()):
            self.menu = None

    def view(self):
        """(key, title, detail, items, selected, bar, until, total) of what to show, or None."""
        if self.state is not None:
            title, detail = power_texts(self.state, self.language, self.wall)
            total = self.power.DELAYS.get(self.state.get("source"), 10.0)
            return ("count", title, detail), title, detail, (), 0, True, float(self.state.get("until") or 0), total
        if self.menu is not None:
            title = text("power_title" if "reboot" in self.menu.items else "power_title_off", self.language)
            items = [text(item, self.language) for item in self.menu.items]
            detail = text("menu_hint", self.language)
            return ("menu", tuple(items), self.menu.selected), title, detail, items, self.menu.selected, False, None, None
        return None

    def update(self, painter, show) -> bool:
        """Calls ``show(panel, until, total)`` (``panel`` None: hidden) when the view changes."""
        view = self.view()
        key = view[0] if view else None
        if key == self.key:
            return False
        self.key = key
        if view is None:
            show(None, None, None)
        else:
            _key, title, detail, items, selected, bar, until, total = view
            show(painter.power_panel(title, detail, items, selected, bar), until, total)
        return True


#: The parent's message, written by the page (home/screen-note.json).
NOTE_FILENAME = "screen-note.json"
NOTE_COLOUR = (246, 196, 92)
#: Each text of the hint line stays this long, and fades in and out.
HINT_S = 7.0
HINT_FADE_S = 0.5
#: Recalbox's screen saver (display.dim_min = "recalbox").
ES_SETTINGS = "/recalbox/share/system/.emulationstation/es_settings.cfg"
#: Opacity of the dark veil: dimmed, or black (Recalbox's "black" screen saver).
DIM_ALPHA = 200
BLACK_ALPHA = 250


def read_note(home: str) -> str:
    try:
        with open(os.path.join(home, NOTE_FILENAME), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return ""
    return str(data.get("text") or "").strip()[:120] if isinstance(data, dict) else ""


def recalbox_screensaver(path: str = ES_SETTINGS):
    """(minutes, black) of Recalbox's screen saver; minutes 0 = never."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    except OSError:
        return 5.0, False
    delay = re.search(r'name="ScreenSaverTime"\s+value="(\d+)"', content)
    behaviour = re.search(r'name="ScreenSaverBehavior"\s+value="([^"]*)"', content)
    minutes = int(delay.group(1)) / 60000.0 if delay else 5.0
    return minutes, bool(behaviour and behaviour.group(1).lower() == "black")


def dim_setting(value: str, saver=recalbox_screensaver):
    """(minutes, black) of display.dim_min: "0" = never, minutes, or "recalbox"."""
    value = str(value or "0").strip().lower()
    if value == "recalbox":
        return saver()
    try:
        return max(0.0, float(value)), False
    except ValueError:
        return 0.0, False


def week_game(games: dict, today: float = None) -> str:
    """Name of the game played most these last 7 days (every player), or ""."""
    first = time.strftime("%Y-%m-%d", time.localtime((today or time.time()) - 6 * 86400))
    table = {}
    for days in games.values():
        for day, played in days.items():
            if day >= first:
                for key, seconds in played.items():
                    table[key] = table.get(key, 0.0) + seconds
    if not table:
        return ""
    return max(table.items(), key=lambda item: item[1])[0].split("|", 1)[1]


def favourite_game(days: dict, today: float = None) -> str:
    first = time.strftime("%Y-%m-%d", time.localtime((today or time.time()) - 30 * 86400))
    table = {}
    for day, played in (days or {}).items():
        if day >= first:
            for key, seconds in played.items():
                table[key] = table.get(key, 0.0) + seconds
    if not table:
        return ""
    return max(table.items(), key=lambda item: item[1])[0].split("|", 1)[1]


def screen_infos(home: str, players: dict, language: str, power_actions=()) -> list:
    """The useful facts shown now and then in place of the hint."""
    from . import trophies
    from .players import read_file

    infos = []
    if power_actions:
        infos.append((text("tip_power" if "reboot" in power_actions else "tip_power_off", language), "info"))
    _usage, games = read_file(os.path.join(home, "players.json"))
    info = player_info(players, language)
    if info and info.get("uid"):
        favourite = favourite_game(games.get(info["uid"]) or {})
        if favourite:
            infos.append((text("favourite", language, name=info["name"], game=favourite), "info"))
        keys = trophies.read(home).get(info["uid"]) or {}
        last = trophies.latest(keys)
        if last is not None:
            infos.append((text("trophy_count", language, name=info["name"], n=len(keys),
                               what=text("t_" + last[0], language, n=last[1])), "trophy"))
    else:
        game = week_game(games)
        if game:
            infos.append((text("week_game", language, game=game), "info"))
    return infos


def hint_sequence(hint: str, note: str, infos: list) -> list:
    """[(text, colour, kind)]: the hint, then each extra in turn (the note more often).

    ``infos``: [(text, kind)], kind "info" or "trophy" (the icon before the text).
    """
    infos = [item if isinstance(item, tuple) else (item, "info") for item in infos or ()]
    extras = []
    if note:
        for info in infos or [None]:
            extras.append((note, NOTE_COLOUR, "note"))
            if info:
                extras.append((info[0], TEXT, info[1]))
    else:
        extras = [(info[0], TEXT, info[1]) for info in infos]
    sequence = []
    for extra in extras:
        sequence += [(hint, TEXT, "card"), extra]
    return sequence or [(hint, TEXT, "card")]


def hint_slot(count: int, now: float):
    """(index, opacity) of the text shown at ``now`` among ``count``."""
    if count <= 1:
        return 0, 1.0
    cycle = now % (HINT_S * count)
    index = int(cycle // HINT_S)
    phase = cycle - index * HINT_S
    return index, max(0.0, min(1.0, phase / HINT_FADE_S, (HINT_S - phase) / HINT_FADE_S))


def refresh_hints(painter, home: str, language: str, players: dict, power_ui=None) -> None:
    """The texts of the hint line: the hint, the parent's message, the useful facts."""
    try:
        infos = []
        if wants(home, "show_info", True):
            if power_ui is not None:
                power_ui.refresh_actions()
            infos = screen_infos(home, players, language, power_ui.actions if power_ui is not None else ())
        painter.hints = hint_sequence(text("hint", language), read_note(home), infos)
    except Exception as exc:  # noqa: BLE001 - the plain hint then
        print("hints: %s" % exc, flush=True)
        painter.hints = None


class Dimmer:
    """Darkens the reader screen after a while with no card, game or button."""

    def __init__(self, home: str, clock=None, read=None):
        self.home = home
        self.clock = clock or time.monotonic
        self.read = read or (lambda: dim_setting(setting(home, "display", "dim_min", "0")))
        self.active_at = self.clock()
        self.checked_at = None
        self.minutes, self.black = 0.0, False
        self.level = 0.0
        self.stamp = self.clock()

    def wake(self) -> None:
        self.active_at = self.clock()

    @property
    def dark(self) -> bool:
        return self.level > 0.05

    def step(self) -> float:
        """The darkness now (0..1): fades in slowly, out quickly."""
        now = self.clock()
        if self.checked_at is None or now - self.checked_at >= 5.0:
            self.checked_at = now
            self.minutes, self.black = self.read()
        target = 1.0 if self.minutes > 0 and now - self.active_at >= self.minutes * 60 else 0.0
        elapsed = max(0.0, now - self.stamp)
        self.stamp = now
        if target > self.level:
            self.level = min(target, self.level + elapsed / 1.5)
        else:
            self.level = max(target, self.level - elapsed / 0.3)
        return self.level

    def alpha(self) -> int:
        return int((BLACK_ALPHA if self.black else DIM_ALPHA) * ease(self.level))


def wants(home: str, key: str, default: bool = False) -> bool:
    try:
        from .config import Config

        return Config(os.path.join(home, "config.ini")).get_bool("display", key, default)
    except Exception:  # noqa: BLE001
        return default


class Messages:
    """Watches the message file of the service (cheap: one stat per call)."""

    def __init__(self, path: str = MESSAGE_FILE, wall=None):
        self.path = path
        self.wall = wall or time.time
        self.stamp = None  # a recent message (age check) is shown even at start

    def _stamp(self):
        try:
            return os.stat(self.path).st_mtime_ns
        except OSError:
            return None

    def poll(self):
        """The new message text, or None."""
        stamp = self._stamp()
        if stamp is None or stamp == self.stamp:
            return None
        self.stamp = stamp
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or abs(self.wall() - float(data.get("at") or 0)) > MESSAGE_MAX_AGE_S:
            return None
        return str(data.get("text") or "").strip() or None


def toast_alpha(elapsed: float) -> float:
    """Opacity of a toast shown ``elapsed`` seconds ago (fades in and out)."""
    if elapsed < 0 or elapsed >= TOAST_S:
        return 0.0
    return ease(min(1.0, elapsed / 0.3, (TOAST_S - elapsed) / 0.6))


def accent_from_svg(svg: str):
    """Main colour of a logo: its most used saturated colour (as the page does)."""
    counts = {}
    for match in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", svg or ""):
        value = match[1:]
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        rgb = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        high, low = max(rgb), min(rgb)
        saturation = (high - low) / high if high else 0
        light = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0
        if saturation < 0.35 or light > 0.92 or light < 0.06:
            continue
        counts[rgb] = counts.get(rgb, 0) + 1
    if not counts:
        return None
    best = max(counts.items(), key=lambda item: (item[1], max(item[0]) - min(item[0])))[0]
    return best


# ------------------------------------------------------------------ drawing
def sized_svg(data: bytes, width: int, height: int) -> bytes:
    """The SVG with its size set, so that it is rasterized sharp at that size."""
    textual = data.decode("utf-8", "replace")
    match = re.search(r"<svg\b[^>]*>", textual)
    if not match:
        return data
    tag = match.group(0)
    view = re.search(r'viewBox\s*=\s*"([^"]+)"', tag)
    if not view:
        w = re.search(r'\bwidth\s*=\s*"([\d.]+)', tag)
        h = re.search(r'\bheight\s*=\s*"([\d.]+)', tag)
        if not (w and h):
            return data
        tag = tag[:-1] + ' viewBox="0 0 %s %s">' % (w.group(1), h.group(1))
    tag = re.sub(r'\s(width|height)\s*=\s*"[^"]*"', "", tag)
    tag = tag[:-1] + ' width="%d" height="%d" preserveAspectRatio="xMidYMid meet">' % (width, height)
    return (textual[:match.start()] + tag + textual[match.end():]).encode("utf-8")


class Painter:
    """Builds the frames (no display needed: also used for the preview)."""

    def __init__(self, pygame, width: int, height: int, consoles: list, language: str, region: str = "eu"):
        self.pg = pygame
        self.w, self.h = width, height
        #: Vertical screen (Recalbox's rotation setting): another layout.
        self.portrait = height > width
        self.u = min(width, height) / 100.0
        self.consoles = consoles
        self.language = language
        self.region = region
        self.p = paths()
        self.cache = {}
        self.lock = threading.Lock()
        self.fonts = {}
        self.strip = None
        self.strip_centres = []
        self.dark = None
        self.shown = 0
        self._clock = None
        self._hint = None
        self.gap = 0
        self.home = None          # where the player avatars are (avatars/<UID>.jpg)
        self._avatars = {}
        self.cache_covers = {}
        self._shapes = {}

    # ---- resources
    def font(self, name: str, size: float):
        key = (name, int(size))
        if key not in self.fonts:
            path = os.path.join(self.p["fonts"], name)
            try:
                self.fonts[key] = self.pg.font.Font(path if os.path.isfile(path) else None, int(size))
            except Exception:  # noqa: BLE001
                self.fonts[key] = self.pg.font.Font(None, int(size))
        return self.fonts[key]

    def svg(self, path: str, width: int, height: int):
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            return None, ""
        try:
            image = self.pg.image.load(io.BytesIO(sized_svg(data, width, height)), "image.svg")
        except Exception:  # noqa: BLE001 - unreadable picture
            return None, ""
        # Cut to the drawing itself (the pictures have transparent margins).
        box = image.get_bounding_rect()
        if box.width and box.height and box.size != image.get_size():
            image = image.subsurface(box).copy()
        return image, data.decode("utf-8", "replace")

    def art_path(self, console_id: str) -> str:
        for name in ("%s-%s-consolegame.svg" % (console_id, self.region), "%s-consolegame.svg" % console_id,
                     "%s-%s-console.svg" % (console_id, self.region), "%s-console.svg" % console_id):
            path = os.path.join(self.p["arts"], name)
            if os.path.isfile(path):
                return path
        return ""

    #: Shapes are drawn this many times larger, then shrunk: smooth edges.
    SUPERSAMPLE = 4

    def shape(self, width: int, height: int, colour, radius: int = 0, line: int = 0, ellipse: bool = False):
        """A rounded rectangle, a frame, a disc or an ellipse with smooth
        edges (pygame draws them without anti-aliasing)."""
        width, height = max(1, int(width)), max(1, int(height))
        colour = tuple(colour)
        rgba = colour if len(colour) == 4 else colour + (255,)
        key = (width, height, rgba, int(radius), int(line), ellipse)
        cached = self._shapes.get(key)
        if cached is not None:
            return cached
        pg, k = self.pg, self.SUPERSAMPLE
        big = pg.Surface((width * k, height * k), pg.SRCALPHA)
        big.fill(rgba[:3] + (0,))  # transparent of the same colour: no dark fringe once shrunk
        if ellipse:
            pg.draw.ellipse(big, rgba, big.get_rect(), int(line) * k)
        else:
            pg.draw.rect(big, rgba, big.get_rect(), width=int(line) * k,
                         border_radius=min(int(radius) * k, height * k // 2, width * k // 2))
        image = pg.transform.smoothscale(big, (width, height))
        if len(self._shapes) > 400:
            self._shapes.clear()
        self._shapes[key] = image
        return image

    def draw_shape(self, surface, rect, colour, radius: int = 0, line: int = 0, ellipse: bool = False):
        x, y, width, height = (int(value) for value in rect)
        surface.blit(self.shape(width, height, colour, radius, line, ellipse), (x, y))

    def plate(self, image, pad_x: int, pad_y: int):
        """A logo on a light rounded plate: every logo stays readable in its own colours."""
        pg = self.pg
        width, height = image.get_width() + 2 * pad_x, image.get_height() + 2 * pad_y
        plate = self.shape(width, height, PLATE, min(height // 2, int(self.u * 1.6))).copy()
        shadow = self.logo_shadow(image)
        if shadow is not None:
            spread = (shadow.get_width() - image.get_width()) // 2
            plate.blit(shadow, (pad_x - spread, pad_y - spread + max(1, int(self.u * 0.12))))
        plate.blit(image, (pad_x, pad_y))
        return plate

    #: Darkness of the veil of shadow under the logos (0-255).
    LOGO_SHADOW = 110

    def logo_shadow(self, image):
        """A very light blurred shadow of a logo's own shape: its white parts
        stay visible on the white plate."""
        pg = self.pg
        try:
            spread = max(2, int(self.u * 0.35))
            width, height = image.get_width() + 2 * spread, image.get_height() + 2 * spread
            silhouette = pg.Surface((width, height), pg.SRCALPHA)
            silhouette.blit(image, (spread, spread))
            silhouette.fill((0, 0, 0, 255), special_flags=pg.BLEND_RGBA_MIN)          # black, its own alpha
            silhouette.fill((255, 255, 255, self.LOGO_SHADOW), special_flags=pg.BLEND_RGBA_MULT)
            small = pg.transform.smoothscale(silhouette, (max(1, width // 3), max(1, height // 3)))
            return pg.transform.smoothscale(small, (width, height))           # blurred
        except Exception:  # noqa: BLE001 - no shadow rather than no logo
            return None

    def glow(self, colour, radius: int):
        """A soft round glow (small, then enlarged smoothly)."""
        small = self.pg.Surface((64, 64), self.pg.SRCALPHA)
        for step in range(32, 0, -1):
            alpha = int(150 * (1 - step / 32.0) ** 2.2)
            self.pg.draw.circle(small, colour + (alpha,), (32, 32), step)
        return self.pg.transform.smoothscale(small, (radius * 2, radius * 2))

    # ---- one console: background, drawing and texts (built once)
    def hero(self, index: int):
        with self.lock:
            if index in self.cache:
                return self.cache[index]
        pg, u, w, h = self.pg, self.u, self.w, self.h
        console = self.consoles[index]
        portrait = self.portrait
        # Boxes (fractions of the screen): logo, console drawing, glow.
        logo_box = (w * 0.62, h * 0.075) if portrait else (w * 0.26, h * 0.1)
        art_box = (w * 0.88, h * 0.33) if portrait else (w * 0.52, h * 0.56)
        art_cx, art_bottom = (w * 0.5, h * 0.53) if portrait else (w * 0.31, h * 0.73)
        logo, logo_svg = self.svg(os.path.join(self.p["logos"], console["id"] + ".svg"),
                                  int(logo_box[0]), int(logo_box[1] * 1.1))
        accent = accent_from_svg(logo_svg) or DEFAULT_ACCENT
        art = None
        art_path = self.art_path(console["id"])
        if art_path:
            art, art_svg = self.svg(art_path, int(art_box[0]), int(art_box[1] * 1.07))
            accent = accent_from_svg(logo_svg) or accent_from_svg(art_svg) or accent
        frame = pg.Surface((w, h))
        frame.fill(BACKGROUND)
        # Floor light and glow of the console colour.
        floor = pg.Surface((w, h), pg.SRCALPHA)
        for y in range(int(h * 0.55), h, 4):
            alpha = int(36 * (y - h * 0.55) / (h * 0.45))
            pg.draw.rect(floor, accent + (alpha,), (0, y, w, 4))
        frame.blit(floor, (0, 0))
        halo = self.glow(accent, int(min(w, h) * 0.62))
        frame.blit(halo, (int(art_cx) - halo.get_width() // 2,
                          int(art_bottom - art_box[1] * 0.48) - halo.get_height() // 2))
        second = self.glow(tuple(min(255, c + 40) for c in accent), int(min(w, h) * 0.28))
        frame.blit(second, (int(w * 0.80) - second.get_width() // 2, int(h * 0.12) - second.get_height() // 2))
        # The console drawing, with its shadow.
        if art is not None:
            box_w, box_h = int(art_box[0]), int(art_box[1])
            scale = min(box_w / art.get_width(), box_h / art.get_height(), 1.0)
            if scale < 1.0:
                art = pg.transform.smoothscale(art, (int(art.get_width() * scale), int(art.get_height() * scale)))
            cx, bottom = int(art_cx), int(art_bottom)
            shadow = self.shape(int(art.get_width() * 0.9), int(u * 5), (0, 0, 0, 110), ellipse=True)
            frame.blit(shadow, (cx - shadow.get_width() // 2, bottom - shadow.get_height() // 2))
            frame.blit(art, (cx - art.get_width() // 2, bottom - art.get_height()))
        # Logo, name, number of games (on the right; centred under the drawing
        # on a vertical screen).
        x = int(w * 0.62)
        y = int(h * 0.58) if portrait else int(h * 0.25)

        def left(width):
            return (w - width) // 2 if portrait else x

        if logo is not None:
            scale = min(logo_box[0] / logo.get_width(), logo_box[1] / logo.get_height(), 1.0)
            if scale < 1.0:
                logo = pg.transform.smoothscale(logo, (int(logo.get_width() * scale), int(logo.get_height() * scale)))
            logo = self.plate(logo, int(u * 3), int(u * 2))
            shade = self.shape(logo.get_width(), logo.get_height(), (0, 0, 0, 90), int(u * 1.6))
            frame.blit(shade, (left(logo.get_width()) + int(u * 0.6), y + int(u * 0.9)))
            frame.blit(logo, (left(logo.get_width()), y))
            y += logo.get_height() + int(u * 3)
        name = self.font("OpenSans-CondLight.ttf", u * 4.6).render(console["name"], True, TEXT)
        frame.blit(name, (left(name.get_width()), y))
        y += name.get_height() + int(u * 0.6)
        facts = " · ".join(part for part in (console.get("maker"), console.get("year")) if part)
        if facts:
            line = self.font("OpenSans-CondLight.ttf", u * 3.4).render(facts, True, MUTED)
            frame.blit(line, (left(line.get_width()), y))
            y += line.get_height()
        y += int(u * 3)
        number = self.font("Exo2-Bold.ttf", u * 15).render(str(console["count"]), True, TEXT)
        label = self.font("Exo2-SemiBoldCondensed.otf", u * 5).render(
            text("game" if console["count"] == 1 else "games", self.language), True, accent)
        nx = left(number.get_width() + int(u * 2) + label.get_width())
        frame.blit(number, (nx, y))
        frame.blit(label, (nx + number.get_width() + int(u * 2), y + number.get_height() - label.get_height() - int(u * 2.2)))
        bar_x = (w - int(u * 9)) // 2 if portrait else nx
        self.draw_shape(frame, (bar_x, y + number.get_height() + int(u * 0.5), int(u * 9), int(u * 0.7)), accent,
                        int(u * 0.35))
        try:
            frame = frame.convert()  # same format as the screen: much faster to show
        except Exception:  # noqa: BLE001 - no display (tests)
            pass
        result = {"frame": frame, "accent": accent}
        with self.lock:
            self.cache[index] = result
            # Kept: the console shown, the one before (during a change) and
            # the next ones (memory of a Pi 3).
            count = len(self.consoles)
            for key in list(self.cache):
                if (key - self.shown) % count not in (0, 1, 2, count - 1):
                    del self.cache[key]
        return result

    def cached(self, index: int) -> bool:
        with self.lock:
            return index in self.cache

    # ---- the band with every logo (built once)
    def build_strip(self):
        pg, u, w, h = self.pg, self.u, self.w, self.h
        height = int(u * 4.6)
        logos = []
        for console in self.consoles:
            image, _svg = self.svg(os.path.join(self.p["logos"], console["id"] + ".svg"), int(u * 30), height)
            if image is None:
                image = self.font("Exo2-SemiBoldCondensed.otf", u * 4.2).render(console["name"], True, (40, 44, 52))
            scale = min(height / image.get_height(), u * 20 / image.get_width(), 1.0)
            if scale < 1.0:
                image = pg.transform.smoothscale(image, (int(image.get_width() * scale), int(image.get_height() * scale)))
            box = pg.Surface((int(u * 20), height), pg.SRCALPHA)
            box.blit(image, ((box.get_width() - image.get_width()) // 2, (height - image.get_height()) // 2))
            logos.append(self.plate(box, int(u * 1.6), int(u * 1.2)))
        self.gap = int(u * 2.4)
        total = sum(image.get_width() for image in logos) + self.gap * max(0, len(logos) - 1)
        height = logos[0].get_height() if logos else height
        strip = pg.Surface((max(1, total), height), pg.SRCALPHA)
        centres = []
        x = 0
        self.plates = []
        for image in logos:
            strip.blit(image, (x, 0))
            centres.append((x + image.get_width() / 2.0, image.get_width()))
            self.plates.append((x, image))
            x += image.get_width() + self.gap
        dim = strip.copy()
        dim.fill((255, 255, 255, 70), special_flags=pg.BLEND_RGBA_MULT)
        self.strip, self.strip_dim, self.strip_centres = self._fast(strip), self._fast(dim), centres
        self.band_h = int(u * 16)
        self.band_y = h - self.band_h
        band = pg.Surface((w, self.band_h), pg.SRCALPHA)
        band.fill((0, 0, 0, 120))
        band.fill((255, 255, 255, 34), (0, 0, w, max(1, int(u * 0.15))))
        self.band = self._fast(band)
        fade = pg.Surface((int(w * 0.18), self.band_h), pg.SRCALPHA)
        for x in range(fade.get_width()):
            alpha = int(255 * (1 - x / fade.get_width()) ** 1.6)
            fade.fill(BACKGROUND + (alpha,), (x, 0, 1, self.band_h))
        self.fade_left = self._fast(fade)
        self.fade_right = self._fast(pg.transform.flip(fade, True, False))
        self.dark = pg.Surface((w, h))
        self.dark.fill(BACKGROUND)
        try:
            self.dark = self.dark.convert()
        except Exception:  # noqa: BLE001
            pass

    def _fast(self, surface):
        try:
            return surface.convert_alpha()
        except Exception:  # noqa: BLE001 - no display (tests)
            return surface

    # ---- the scene: console in the spotlight and band (redrawn on changes)
    def scene(self, surface, index: int, previous, progress: float) -> None:
        if self.strip is None:
            self.build_strip()
        changing = previous is not None and progress < 1.0
        if changing:
            # The console leaves into the dark, the next one comes out of it.
            first = progress < 0.5
            surface.blit(self.hero(previous if first else index)["frame"], (0, 0))
            depth = ease(progress * 2) if first else 1 - ease((progress - 0.5) * 2)
            self.dark.set_alpha(int(255 * depth))
            surface.blit(self.dark, (0, 0))
        else:
            surface.blit(self.hero(index)["frame"], (0, 0))
        accent = self.hero(index)["accent"]
        w, u = self.w, self.u
        surface.blit(self.band, (0, self.band_y))
        centre_now = self.strip_centres[index][0]
        if changing:
            start = self.strip_centres[previous][0]
            if index < previous and len(self.strip_centres) > 1:  # wrapped around: slide forward anyway
                start = centre_now - (self.strip_centres[1][0] - self.strip_centres[0][0])
            centre_now = start + (centre_now - start) * ease(progress)
        offset = int(w / 2 - centre_now)
        strip_y = self.band_y + (self.band_h - self.strip.get_height()) // 2
        surface.blit(self.strip_dim, (offset, strip_y))
        loop = self.strip.get_width() + self.gap
        if offset + self.strip.get_width() < w:  # seamless loop
            surface.blit(self.strip_dim, (offset + loop, strip_y))
        if offset > 0:
            surface.blit(self.strip_dim, (offset - loop, strip_y))
        centre, width = self.strip_centres[index]
        alpha = 0.0 if changing else 1.0  # lit once the band has stopped
        if alpha > 0:
            bright = self.strip.subsurface((int(centre - width / 2), 0, int(width), self.strip.get_height()))
            if alpha < 1.0:
                bright = bright.copy()
                bright.set_alpha(int(255 * alpha))
            surface.blit(bright, (int(w / 2 - width / 2), strip_y))
            self.draw_shape(surface, (int(w / 2 - width / 2), strip_y + self.strip.get_height() + int(u * 1.2),
                                                int(width), int(u * 0.6)), accent, int(u * 0.3))
        surface.blit(self.fade_left, (0, self.band_y))
        surface.blit(self.fade_right, (w - self.fade_right.get_width(), self.band_y))

    # ---- the top: invitation (pulsing), player, clock (redrawn often, small)
    def top_rect(self):
        return self.pg.Rect(0, 0, self.w, int(self.u * (26 if self.portrait else 15)))

    def top(self, surface, index: int, players: dict, now: float, background: bool = True,
            hint: bool = True, chip: bool = True) -> None:
        pg, u, w = self.pg, self.u, self.w
        rect = self.top_rect()
        if background:
            surface.blit(self.hero(index)["frame"], rect.topleft, rect)
        accent = self.hero(index)["accent"]
        margin = int(u * 5)
        minute = time.strftime("%H:%M")
        if self._clock is None or self._clock[0] != minute:
            self._clock = (minute, self._fast(self.font("Exo2-SemiBoldCondensed.otf", u * 7).render(minute, True, TEXT)))
        clock = self._clock[1]
        surface.blit(clock, (w - margin - clock.get_width(), margin - int(u * 1)))
        if hint:
            image, opacity, index = self.current_hint(time.monotonic(), accent)
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(now * 2.2)) if index % 2 == 0 else 1.0
            image.set_alpha(int(255 * pulse * opacity))
            surface.blit(image, self.hint_position(image))
        player = player_info(players, self.language) if chip else None
        if player:
            self.chip_at(surface, player, accent, clock.get_width())

    def chip_at(self, surface, player, accent, clock_width: int) -> None:
        """The player, left of the clock (under it on a vertical screen)."""
        u, w = self.u, self.w
        margin = int(u * 5)
        if self.portrait:
            self.player_chip(surface, player, accent, w - margin, margin + int(u * 12))
        else:
            self.player_chip(surface, player, accent, w - margin - clock_width - int(u * 3), margin)

    def clock_width(self) -> int:
        minute = time.strftime("%H:%M")
        if self._clock is None or self._clock[0] != minute:
            self._clock = (minute, self._fast(self.font("Exo2-SemiBoldCondensed.otf", self.u * 7).render(minute, True, TEXT)))
        return self._clock[1].get_width()

    def hint_icon(self, kind: str, accent):
        """The icon before the hint line: a card, a message, an "i", a cup."""
        pg, u, k = self.pg, self.u, self.SUPERSAMPLE
        width, height = int(u * 5.4), int(u * 3.6)
        big = pg.Surface((width * k, height * k), pg.SRCALPHA)
        colour = tuple(NOTE_COLOUR if kind == "note" else accent)[:3]
        big.fill(colour + (0,))
        line = max(2, int(u * 0.45)) * k
        rgba = colour + (255,)
        W, H = width * k, height * k
        if kind == "note":
            # A speech bubble with its tail on the bottom left.
            body = pg.Rect(int(W * 0.12), 0, int(W * 0.76), int(H * 0.78))
            pg.draw.rect(big, rgba, body, width=line, border_radius=int(H * 0.22))
            tail = [(body.x + int(W * 0.14), body.bottom - line), (body.x + int(W * 0.06), H - 1),
                    (body.x + int(W * 0.34), body.bottom - line)]
            pg.draw.polygon(big, rgba, tail)
            for number in range(3):
                centre = (body.x + int(body.w * (0.3 + 0.2 * number)), body.centery)
                pg.draw.circle(big, rgba, centre, int(line * 0.75))
        elif kind == "info":
            # A full disc with the "i" cut out: as heavy as the other icons.
            centre = (W // 2, H // 2)
            pg.draw.circle(big, rgba, centre, H // 2)
            hole = colour + (0,)
            stroke = int(H * 0.15)
            pg.draw.circle(big, hole, (centre[0], int(H * 0.27)), int(stroke * 0.62))
            pg.draw.rect(big, hole, (centre[0] - stroke // 2, int(H * 0.42), stroke, int(H * 0.36)), border_radius=stroke // 2)
        elif kind == "trophy":
            cx = W // 2
            cup = [(cx - int(H * 0.42), 0), (cx + int(H * 0.42), 0), (cx + int(H * 0.3), int(H * 0.42)),
                   (cx + int(H * 0.12), int(H * 0.58)), (cx - int(H * 0.12), int(H * 0.58)), (cx - int(H * 0.3), int(H * 0.42))]
            pg.draw.polygon(big, rgba, cup)
            for side in (-1, 1):
                pg.draw.arc(big, rgba, (cx + side * int(H * 0.36) - int(H * 0.2), int(H * 0.04), int(H * 0.4), int(H * 0.36)),
                            -1.6 if side > 0 else 1.5, 1.6 if side > 0 else 4.7, max(1, line // 2))
            pg.draw.rect(big, rgba, (cx - line // 2, int(H * 0.56), line, int(H * 0.24)))
            pg.draw.rect(big, rgba, (cx - int(H * 0.26), int(H * 0.8), int(H * 0.52), H - int(H * 0.8)), border_radius=line // 2)
        else:
            # The card, as before.
            pg.draw.rect(big, rgba, big.get_rect(), width=line, border_radius=int(u * 0.7) * k)
            pg.draw.rect(big, rgba, (int(u * 0.9) * k, int(u * 0.9) * k, int(u * 1.6) * k, int(u * 1.2) * k),
                         border_radius=int(u * 0.25) * k)
        return pg.transform.smoothscale(big, (width, height))

    def hint_image(self, message: str = None, colour=TEXT, kind: str = "card", accent=None):
        """The hint line (or another text in its place) with its icon, cut to fit beside the player."""
        message = message or text("hint", self.language)
        accent = tuple(accent or DEFAULT_ACCENT)[:3]
        key = (message, tuple(colour), kind, accent)
        cache = self.__dict__.setdefault("_hints", {})
        if key not in cache:
            pg, u = self.pg, self.u
            font = self.font("Raleway-SemiBold.ttf", u * 3.6)
            room = int(self.w - self.hint_position_x() - u * (26 if self.portrait else 62))
            shown = message
            while font.size(shown)[0] > room and len(shown) > 4:
                shown = shown[:-2].rstrip() + "…"
            label = font.render(shown, True, tuple(colour))
            icon = self.hint_icon(kind, accent)
            gap = int(u * 1.6)
            height = max(label.get_height(), icon.get_height())
            image = pg.Surface((icon.get_width() + gap + label.get_width(), height), pg.SRCALPHA)
            image.blit(icon, (0, (height - icon.get_height()) // 2))
            image.blit(label, (icon.get_width() + gap, (height - label.get_height()) // 2))
            if len(cache) > 24:
                cache.clear()
            cache[key] = self._fast(image)
        return cache[key]

    def hint_position_x(self) -> int:
        u = self.u
        return int(u * 5) + int(u * 5.4) + int(u * 1.6)

    def current_hint(self, now: float, accent=None):
        """(image, opacity, index) of the hint line at ``now`` (texts set in self.hints)."""
        hints = getattr(self, "hints", None) or [(text("hint", self.language), TEXT, "card")]
        index, opacity = hint_slot(len(hints), now)
        message, colour, kind = (tuple(hints[index]) + ("card",))[:3]
        return self.hint_image(message, colour, kind, accent), opacity, index

    def hint_position(self, image):
        """Top left of the hint line (its icon first)."""
        u = self.u
        margin = int(u * 5)
        centre_y = margin + int(u * 0.6) + int(u * 3.6) // 2
        return margin, centre_y - image.get_height() // 2

    def compose(self, surface, index: int, previous, progress: float, players: dict, now: float) -> None:
        """The whole frame (preview, first frame)."""
        self.shown = index
        self.scene(surface, index, previous, progress)
        self.top(surface, index, players, now)

    def avatar(self, uid, version, size: int, ring: int, accent):
        """The player's picture in a disc with a ring of the accent colour,
        ``size`` px wide (None: show the initial). Drawn 4 times larger then
        shrunk, the ring and the picture in one image: always concentric."""
        if not uid or not self.home:
            return None
        key = (uid, version, size, ring, tuple(accent))
        if key not in self._avatars:
            pg = self.pg
            picture = None
            try:
                from .avatars import path as avatar_path
                image = self._fast(pg.image.load(avatar_path(self.home, uid)))
                side = min(image.get_width(), image.get_height())
                square = image.subsurface(((image.get_width() - side) // 2, (image.get_height() - side) // 2, side, side))
                big_size = size * 4
                inner = big_size - ring * 8
                disc = pg.Surface((big_size, big_size), pg.SRCALPHA)
                pg.draw.circle(disc, tuple(accent) + (255,), (big_size / 2.0, big_size / 2.0), big_size / 2.0)
                photo = pg.Surface((inner, inner), pg.SRCALPHA)  # a JPEG has no alpha
                photo.blit(pg.transform.smoothscale(square, (inner, inner)), (0, 0))
                mask = pg.Surface((inner, inner), pg.SRCALPHA)
                pg.draw.circle(mask, (255, 255, 255, 255), (inner / 2.0, inner / 2.0), inner / 2.0)
                photo.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MIN)
                disc.blit(photo, (ring * 4, ring * 4))
                picture = pg.transform.smoothscale(disc, (size, size))
            except Exception:  # noqa: BLE001 - missing or unreadable: the initial
                picture = None
            self._avatars = {k: v for k, v in self._avatars.items() if k[0] != uid}
            self._avatars[key] = picture
        return self._avatars[key]

    def cover(self, path: str, max_w: int, max_h: int):
        """A game picture fitted in a box (None when missing)."""
        key = ("cover", path, max_w, max_h)
        if key not in self.cache_covers:
            image = None
            try:
                image = self._fast(self.pg.image.load(path)) if path else None
                if image is not None:
                    scale = min(max_w / image.get_width(), max_h / image.get_height())
                    image = self.pg.transform.smoothscale(image, (max(1, int(image.get_width() * scale)),
                                                                  max(1, int(image.get_height() * scale))))
            except Exception:  # noqa: BLE001 - unreadable: a plain box
                image = None
            if len(self.cache_covers) > 24:
                self.cache_covers.clear()
            self.cache_covers[key] = image
        return self.cache_covers[key]

    def backdrop(self, accent):
        pg, w, h = self.pg, self.w, self.h
        frame = pg.Surface((w, h))
        frame.fill(BACKGROUND)
        halo = self.glow(accent, int(min(w, h) * 0.7))
        frame.blit(halo, (w // 2 - halo.get_width() // 2, int(h * 0.42) - halo.get_height() // 2))
        return frame

    def console_accent(self, system: str):
        for number, console in enumerate(self.consoles):
            if console["id"] == system:
                return self.hero(number)["accent"]
        return DEFAULT_ACCENT

    def launch_page(self, info: dict, waiting: bool):
        """The game placed on the reader, before it starts."""
        pg, u, w, h = self.pg, self.u, self.w, self.h
        accent = self.console_accent(info.get("system", ""))
        frame = self.backdrop(accent)
        box_w, box_h = (int(w * 0.7), int(h * 0.42)) if self.portrait else (int(w * 0.36), int(h * 0.62))
        image = self.cover(info.get("image") or "", box_w, box_h)
        title = self.font("Exo2-Bold.ttf", u * 6.5).render(info.get("name") or "", True, TEXT)
        if title.get_width() > w * 0.9:
            title = pg.transform.smoothscale(title, (int(w * 0.9), int(title.get_height() * w * 0.9 / title.get_width())))
        console = self.font("OpenSans-CondLight.ttf", u * 3.8).render(
            next((c["name"] for c in self.consoles if c["id"] == info.get("system")), info.get("system", "")), True, MUTED)
        first = self.font("Raleway-SemiBold.ttf", u * 4).render(text("press" if waiting else "launching", self.language), True, accent if waiting else TEXT)
        second = self.font("Raleway-SemiBold.ttf", u * 2.8).render(text("cancel_hint", self.language), True, MUTED) if waiting else None
        heights = [image.get_height() + int(u * 4) if image is not None else 0, title.get_height(), console.get_height() + int(u * 3),
                   first.get_height(), (second.get_height() + int(u * 1)) if second is not None else 0]
        y = (h - sum(heights)) // 2
        if image is not None:
            frame.blit(image, ((w - image.get_width()) // 2, y))
            y += image.get_height() + int(u * 4)
        for line, gap in ((title, 0), (console, int(u * 3)), (first, int(u * 1)), (second, 0)):
            if line is None:
                continue
            frame.blit(line, ((w - line.get_width()) // 2, y))
            y += line.get_height() + gap
        try:
            frame = frame.convert()
        except Exception:  # noqa: BLE001
            pass
        return frame

    def player_page(self, name: str, games: list, accent):
        """The active player's last games, in place of the consoles."""
        pg, u, w, h = self.pg, self.u, self.w, self.h
        frame = self.backdrop(accent)
        top = int(u * (30 if self.portrait else 19))
        title = self.font("Exo2-Bold.ttf", u * 6).render(text("player_games", self.language, name=name), True, TEXT)
        frame.blit(title, ((w - title.get_width()) // 2, top))
        self.draw_shape(frame, ((w - int(u * 9)) // 2, top + title.get_height() + int(u * 0.6), int(u * 9), int(u * 0.7)),
                        accent, int(u * 0.35))
        area_top = top + title.get_height() + int(u * 5)
        area_bottom = self.band_y - int(u * 3) if self.strip is not None else int(h * 0.82)
        if not games:
            line = self.font("Raleway-SemiBold.ttf", u * 3.6).render(text("no_games", self.language), True, MUTED)
            frame.blit(line, ((w - line.get_width()) // 2, (area_top + area_bottom - line.get_height()) // 2))
            return frame
        columns = min(len(games), 3 if self.portrait else 5)
        rows = (len(games) + columns - 1) // columns
        gap = int(u * 3)
        cell_w = (int(w * 0.92) - gap * (columns - 1)) // columns
        label_h = int(u * 7.5)
        cell_h = max(int(u * 10), (area_bottom - area_top - gap * (rows - 1)) // rows)
        picture_h = cell_h - label_h
        left0 = (w - (cell_w * columns + gap * (columns - 1))) // 2
        name_font = self.font("Exo2-SemiBoldCondensed.otf", u * 3.1)
        time_font = self.font("OpenSans-CondLight.ttf", u * 2.6)
        for number, game in enumerate(games[:columns * rows]):
            row, column = divmod(number, columns)
            x = left0 + column * (cell_w + gap)
            y = area_top + row * (cell_h + gap)
            image = self.cover(game.get("image") or "", cell_w, picture_h)
            if image is not None:
                frame.blit(image, (x + (cell_w - image.get_width()) // 2, y + picture_h - image.get_height()))
            else:
                box = self.shape(cell_w, picture_h, (255, 255, 255, 18), int(u * 1.5))
                frame.blit(box, (x, y))
            label = name_font.render(game["name"], True, TEXT)
            if label.get_width() > cell_w:
                label = label.subsurface((0, 0, cell_w, label.get_height()))
            frame.blit(label, (x + (cell_w - label.get_width()) // 2, y + picture_h + int(u * 1)))
            played = time_font.render(duration(game.get("seconds")), True, MUTED)
            frame.blit(played, (x + (cell_w - played.get_width()) // 2, y + picture_h + int(u * 1) + label.get_height()))
        try:
            frame = frame.convert()
        except Exception:  # noqa: BLE001
            pass
        return frame

    def toast_image(self, message: str, accent):
        """A message of the service, in a dark pill with an accent mark."""
        pg, u = self.pg, self.u
        label = self.font("Raleway-SemiBold.ttf", u * 3.4).render(message, True, TEXT)
        pad_x, pad_y, mark = int(u * 3), int(u * 1.6), int(u * 0.8)
        width = min(self.w - int(u * 8), label.get_width() + pad_x * 2 + mark * 2)
        height = label.get_height() + pad_y * 2
        image = pg.Surface((width, height), pg.SRCALPHA)
        image.blit(self.shape(width, height, (12, 14, 20, 225), height // 2), (0, 0))
        image.blit(self.shape(width, height, tuple(accent), height // 2, max(2, int(u * 0.3))), (0, 0))
        image.blit(self.shape(mark * 2, mark * 2, tuple(accent), ellipse=True), (pad_x - mark, height // 2 - mark))
        image.blit(label, (pad_x + mark * 2, pad_y), (0, 0, width - pad_x * 2 - mark * 2, label.get_height()))
        return image

    def toast_position(self, image):
        return (self.w - image.get_width()) // 2, int(self.u * (28 if self.portrait else 14))

    def power_panel(self, title: str, detail: str, items=(), selected: int = 0, bar: bool = False):
        """The power menu or a countdown, in a panel: (image, bar rect inside it or None)."""
        pg, u = self.pg, self.u
        accent = DEFAULT_ACCENT
        heading = self.font("Exo2-Bold.ttf", u * 5).render(title, True, TEXT)
        note = self.font("OpenSans-CondLight.ttf", u * 3).render(detail, True, MUTED) if detail else None
        rows = [self.font("Raleway-SemiBold.ttf", u * 3.8).render(item, True, TEXT) for item in items]
        pad, gap, row_h, bar_h = int(u * 4), int(u * 2), int(u * 7), max(4, int(u * 1.1))
        inner = max([heading.get_width(), note.get_width() if note else 0, int(u * 44)]
                    + [row.get_width() + int(u * 10) for row in rows])
        width = min(self.w - int(u * 6), inner + pad * 2)
        height = pad + heading.get_height()
        if rows:
            height += gap + len(rows) * row_h
        if bar:
            height += gap + bar_h
        if note:
            height += gap + note.get_height()
        height += pad
        image = pg.Surface((width, height), pg.SRCALPHA)
        radius = int(u * 3)
        image.blit(self.shape(width, height, (16, 19, 27, 255), radius), (0, 0))
        image.blit(self.shape(width, height, accent + (255,), radius, max(2, int(u * 0.3))), (0, 0))
        y = pad
        image.blit(heading, ((width - heading.get_width()) // 2, y), (0, 0, width - pad * 2, heading.get_height()))
        y += heading.get_height()
        if rows:
            y += gap
            for number, row in enumerate(rows):
                if number == selected:
                    image.blit(self.shape(width - pad * 2, row_h, accent + (255,), row_h // 2), (pad, y))
                image.blit(row, ((width - row.get_width()) // 2, y + (row_h - row.get_height()) // 2))
                y += row_h
        bar_rect = None
        if bar:
            y += gap
            bar_rect = pg.Rect(pad, y, width - pad * 2, bar_h)
            y += bar_h
        if note:
            y += gap
            image.blit(note, ((width - note.get_width()) // 2, y), (0, 0, width - pad * 2, note.get_height()))
        return image, bar_rect

    def player_chip(self, surface, player, accent, right: int, top: int):
        pg, u = self.pg, self.u
        name = self.font("Exo2-Bold.ttf", u * 3.6).render(player["name"], True, TEXT)
        detail = self.font("OpenSans-CondLight.ttf", u * 2.9).render(player["detail"], True, MUTED)
        size = int(u * 7)
        width = size + int(u * 2) + max(name.get_width(), detail.get_width(), int(u * 16)) + int(u * 3)
        x = right - width
        chip = self.shape(width, size + int(u * 1.6), (255, 255, 255, 18), (size + int(u * 1.6)) // 2)
        surface.blit(chip, (x, top - int(u * 0.8)))
        centre = (x + int(u * 0.8) + size // 2, top + size // 2)
        picture = self.avatar(player.get("uid"), player.get("avatar"), size, max(1, int(round(u * 0.25))), accent)
        if picture is not None:
            surface.blit(picture, (x + int(u * 0.8), top))
        else:
            self.draw_shape(surface, (centre[0] - size // 2, centre[1] - size // 2, size, size), accent, ellipse=True)
            initial = self.font("Exo2-Bold.ttf", u * 4.2).render((player["name"][:1] or "?").upper(), True, TEXT)
            surface.blit(initial, (centre[0] - initial.get_width() // 2, centre[1] - initial.get_height() // 2))
        tx = x + int(u * 0.8) + size + int(u * 2)
        surface.blit(name, (tx, top - int(u * 0.9)))
        detail_y = top + name.get_height() - int(u * 1.9)
        surface.blit(detail, (tx, detail_y))
        if player.get("ratio") is not None:
            bar_w = max(name.get_width(), detail.get_width(), int(u * 16))
            bar_y = detail_y + detail.get_height() - int(u * 0.1)
            self.draw_shape(surface, (tx, bar_y, bar_w, int(u * 0.6)), (255, 255, 255, 40), int(u * 0.3))
            colour = accent if player["ratio"] > 0.2 else (234, 165, 59)
            self.draw_shape(surface, (tx, bar_y, max(int(u * 0.6), int(bar_w * player["ratio"])), int(u * 0.6)), colour,
                         int(u * 0.3))


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


# ------------------------------------------------------------------ screen
def screen_size(conf: dict, native: bool = False):
    """The resolution of the reader screen, or (0, 0): the screen's own.

    By default the one of Recalbox's interface (``es.videomode``, else
    ``global.videomode`` as Recalbox does): the TV keeps the same mode between
    the reader screen, the interface and the games (no black flash, no TV
    losing the picture). ``native``: the screen's own resolution (sharper,
    the TV changes mode at each game)."""
    keys = ("es.videomode",) if native else ("es.videomode", "global.videomode")
    for key in keys:
        match = re.match(r"^(\d{3,4})x(\d{3,4})$", conf.get(key, ""))
        if match:
            return int(match.group(1)), int(match.group(2))
    return 0, 0


def wants_native(home: str) -> bool:
    """Option ``[display] resolution = native``."""
    try:
        from .config import Config

        return Config(os.path.join(home, "config.ini")).get("display", "resolution", "recalbox").strip().lower() == "native"
    except Exception:  # noqa: BLE001 - unreadable settings: the default
        return False


BOOT_CONF = "/boot/recalbox-boot.conf"


def rotation(path: str = BOOT_CONF) -> int:
    """Clockwise angle of Recalbox's screen rotation (``screen.rotation``:
    0, 1 = 270, 2 = 180, 3 = 90, as Recalbox turns its videos)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip().startswith("screen.rotation="):
                    index = line.split("=", 1)[1].strip()
                    return {"1": 270, "2": 180, "3": 90}.get(index, 0)
    except OSError:
        pass
    return 0


def native_size(pygame):
    try:
        sizes = pygame.display.get_desktop_sizes()
        if sizes and sizes[0][0]:
            return tuple(sizes[0])
    except Exception:  # noqa: BLE001 - older pygame
        pass
    info = pygame.display.Info()
    return info.current_w or 1280, info.current_h or 720


def logical_size(size, angle: int):
    """The page drawn before the rotation: upright on a turned screen."""
    return (size[1], size[0]) if angle in (90, 270) else tuple(size)


def region(conf: dict) -> str:
    language = (conf.get("system.language") or "")[:5].lower()
    if language.startswith("ja"):
        return "jp"
    if language in ("en_us",) or language.startswith("pt_br"):
        return "us"
    return "eu"


class GpuScreen:
    """Drawn by the graphics chip: every frame is a few texture copies."""

    def __init__(self, pygame, painter, window, renderer, angle: int = 0, screen=None):
        from pygame._sdl2.video import Texture

        self.pg = pygame
        self.angle = angle
        self.screen = screen or (painter.w, painter.h)
        self.canvas = None
        if angle:
            # Drawn upright in this texture, then turned onto the screen.
            self.canvas = Texture(renderer, (painter.w, painter.h), target=True)
        self.painter = painter
        self.window = window
        self.renderer = renderer
        self.Texture = Texture
        self.heroes = {}
        self.static = None
        self.top_key = None
        self.top_texture = None
        self.hint_texture = None
        self.toast = None  # (texture, started)
        self.page = None   # (key, texture): the player's games, in place of the consoles
        self.launch = None  # (texture, started): the game placed, before it starts
        self.power = None  # the power menu or a countdown, over everything
        self.dim_alpha = 0  # dark veil when nobody uses the reader (Dimmer)

    def texture(self, surface):
        return self.Texture.from_surface(self.renderer, surface)

    def hero(self, index: int):
        if index not in self.heroes:
            self.heroes[index] = self.texture(self.painter.hero(index)["frame"])
            for key in list(self.heroes):
                if key != index and len(self.heroes) > 3:
                    if key not in (self.painter.shown, (self.painter.shown - 1) % len(self.painter.consoles)):
                        del self.heroes[key]
        return self.heroes[index]

    def build_static(self):
        painter = self.painter
        if painter.strip is None:
            painter.build_strip()
        self.static = {
            "band": self.texture(painter.band),
            "left": self.texture(painter.fade_left),
            "right": self.texture(painter.fade_right),
        }
        for name in ("band", "left", "right"):
            self.static[name].blend_mode = 1  # SDL_BLENDMODE_BLEND
        self.plates = []
        for x, image in painter.plates:
            texture = self.texture(image)
            texture.blend_mode = 1
            self.plates.append((x, image.get_width(), texture))

    def draw(self, index: int, previous, progress: float, players: dict, now: float, highlight: float = 1.0) -> None:
        pg, painter, renderer = self.pg, self.painter, self.renderer
        w, h, u = painter.w, painter.h, painter.u
        if self.static is None:
            self.build_static()
        changing = previous is not None and progress < 1.0
        full = pg.Rect(0, 0, w, h)
        if self.canvas is not None:
            renderer.target = self.canvas
        renderer.draw_color = BACKGROUND + (255,)
        renderer.clear()
        if self.page is not None:
            self.page[1].draw(dstrect=full)
            changing = False
        elif changing:
            first = progress < 0.5
            self.hero(previous if first else index).draw(dstrect=full)
            depth = ease(progress * 2) if first else 1 - ease((progress - 0.5) * 2)
            renderer.draw_blend_mode = 1
            renderer.draw_color = BACKGROUND + (int(255 * depth),)
            renderer.fill_rect(full)
        else:
            self.hero(index).draw(dstrect=full)
        accent = painter.hero(index)["accent"]
        static = self.static
        band_y, band_h = painter.band_y, painter.band_h
        static["band"].draw(dstrect=(0, band_y, w, band_h))
        centre_now = painter.strip_centres[index][0]
        if changing:
            start = painter.strip_centres[previous][0]
            if index < previous and len(painter.strip_centres) > 1:
                start = centre_now - (painter.strip_centres[1][0] - painter.strip_centres[0][0])
            centre_now = start + (centre_now - start) * ease(progress)
        strip_w, strip_h = painter.strip.get_width(), painter.strip.get_height()
        strip_y = band_y + (band_h - strip_h) // 2
        offset = w / 2.0 - centre_now
        loop = strip_w + painter.gap
        centre, width = painter.strip_centres[index]
        alpha = 0.0 if changing else highlight  # lit once the band has stopped
        if self.page is not None:
            alpha = 0.0  # the player's page: no console is chosen
        for shift in (-loop, 0, loop):
            for number, (x, plate_w, texture) in enumerate(self.plates):
                left = offset + shift + x
                if left + plate_w < 0 or left > w:
                    continue
                texture.alpha = 70
                texture.draw(dstrect=(int(left), strip_y, plate_w, strip_h))
        if alpha > 0:
            texture = self.plates[index][2]
            texture.alpha = int(255 * alpha)
            texture.draw(dstrect=(int(w / 2 - width / 2), strip_y, int(width), strip_h))
            bar = self.bar_texture(int(width), int(u * 0.6), accent, int(u * 0.3))
            bar.alpha = int(255 * alpha)
            bar.draw(dstrect=(int(w / 2 - width / 2), strip_y + strip_h + int(u * 1.2), int(width), int(u * 0.6)))
        static["left"].draw(dstrect=(0, band_y, painter.fade_left.get_width(), band_h))
        static["right"].draw(dstrect=(w - painter.fade_right.get_width(), band_y, painter.fade_right.get_width(), band_h))
        # Top: drawn on a transparent surface when it changes (minute, console).
        key = (index, time.strftime("%H:%M"))
        if key != self.top_key:
            self.top_key = key
            layer = pg.Surface(painter.top_rect().size, pg.SRCALPHA)
            painter.top(layer, index, players, now, background=False, hint=False, chip=False)
            self.top_texture = self.texture(layer)
            self.top_texture.blend_mode = 1
        self.top_texture.draw(dstrect=painter.top_rect())
        self.draw_chip(index, players)
        image, opacity, number = painter.current_hint(time.monotonic(), painter.hero(index)["accent"])
        textures = self.__dict__.setdefault("hint_textures", {})
        if id(image) not in textures:
            if len(textures) > 24:
                textures.clear()
            texture = self.texture(image)
            texture.blend_mode = 1
            textures[id(image)] = (image, texture)  # the image is kept: its id stays unique
        hint = textures[id(image)][1]
        # The usual hint pulses; the other texts stay still, easier to read.
        pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(now * 2.2)) if number % 2 == 0 else 1.0
        hint.alpha = int(255 * pulse * opacity)
        x, y = painter.hint_position(image)
        hint.draw(dstrect=(x, y, hint.width, hint.height))
        if self.toast is not None:
            texture, started, position = self.toast
            alpha = toast_alpha(time.monotonic() - started)
            if alpha <= 0:
                self.toast = None
            else:
                texture.alpha = int(255 * alpha)
                texture.draw(dstrect=(position[0], position[1], texture.width, texture.height))
        if self.launch is not None:
            texture, started = self.launch
            texture.alpha = int(255 * ease(min(1.0, (time.monotonic() - started) / 0.35)))
            texture.draw(dstrect=full)
        if self.dim_alpha > 0:
            renderer.draw_blend_mode = 1
            renderer.draw_color = (0, 0, 0, self.dim_alpha)
            renderer.fill_rect(full)
        if self.power is not None:
            self.draw_power(full)
        if self.canvas is not None:
            renderer.target = None
            renderer.draw_color = BACKGROUND + (255,)
            renderer.clear()
            sw, sh = self.screen
            self.canvas.draw(dstrect=((sw - w) // 2, (sh - h) // 2, w, h), angle=self.angle)
        renderer.present()

    #: The player's chip comes in (fades in, slides from the right) and goes out.
    CHIP_IN_S = 0.45
    CHIP_OUT_S = 0.35

    def chip_texture(self, index: int, player):
        painter = self.painter
        layer = self.pg.Surface(painter.top_rect().size, self.pg.SRCALPHA)
        painter.chip_at(layer, player, painter.hero(index)["accent"], painter.clock_width())
        texture = self.texture(layer)
        texture.blend_mode = 1
        return texture

    def draw_chip(self, index: int, players: dict) -> None:
        """The player left of the clock: animated when they come, change or leave."""
        painter = self.painter
        player = player_info(players, painter.language)
        who = (player.get("uid"), player.get("name")) if player else None
        content = (json.dumps(player, sort_keys=True), index, time.strftime("%H:%M")) if player else None
        now = time.monotonic()
        current = getattr(self, "chip", None)  # (who, content, texture, since)
        if who is None:
            if current is not None:
                self.chip_out = (current[2], now)
                self.chip = current = None
        elif current is None or current[0] != who:
            if current is not None:
                self.chip_out = (current[2], now)  # the other player leaves while this one comes
            self.chip = current = (who, content, self.chip_texture(index, player), now)
        elif current[1] != content:
            # Same player, new time (or console colour): no animation.
            self.chip = current = (who, content, self.chip_texture(index, player), current[3])
        rect = painter.top_rect()
        slide = painter.u * 3
        leaving = getattr(self, "chip_out", None)
        if leaving is not None:
            done = (now - leaving[1]) / self.CHIP_OUT_S
            if done >= 1:
                self.chip_out = None
            else:
                texture = leaving[0]
                texture.alpha = int(255 * (1 - ease(done)))
                texture.draw(dstrect=(rect.x + int(slide * ease(done)), rect.y, rect.w, rect.h))
        if current is not None:
            shown = ease((now - current[3]) / self.CHIP_IN_S)
            texture = current[2]
            texture.alpha = int(255 * shown)
            texture.draw(dstrect=(rect.x + int(slide * (1 - shown)), rect.y, rect.w, rect.h))

    def bar_texture(self, width: int, height: int, colour, radius: int):
        key = (width, height, tuple(colour), radius)
        if getattr(self, "_bar", None) is None or self._bar[0] != key:
            texture = self.texture(self.painter.shape(width, height, colour, radius))
            texture.blend_mode = 1
            self._bar = (key, texture)
        return self._bar[1]

    def set_page(self, key, builder) -> None:
        """The player's page (``key`` None: the consoles again)."""
        if key is None:
            self.page = None
        elif self.page is None or self.page[0] != key:
            texture = self.texture(builder())
            self.page = (key, texture)

    def show_launch(self, info, waiting: bool) -> None:
        if info is None:
            self.launch = None
            return
        texture = self.texture(self.painter.launch_page(info, waiting))
        texture.blend_mode = 1
        started = self.launch[1] if self.launch is not None else time.monotonic()
        self.launch = (texture, started)

    def show_power(self, panel, until: float = None, total: float = None) -> None:
        """The power menu or a countdown (``panel`` from Painter.power_panel), None to hide it."""
        if panel is None:
            self.power = None
            return
        image, bar = panel
        texture = self.texture(image)
        texture.blend_mode = 1
        started = self.power["started"] if self.power is not None else time.monotonic()
        position = ((self.painter.w - image.get_width()) // 2, (self.painter.h - image.get_height()) // 2)
        bars = None
        if bar is not None:
            bars = (self.texture(self.painter.shape(bar.w, bar.h, (255, 255, 255, 40), bar.h // 2)),
                    self.texture(self.painter.shape(bar.w, bar.h, DEFAULT_ACCENT + (255,), bar.h // 2)))
            for item in bars:
                item.blend_mode = 1
        self.power = {"texture": texture, "position": position, "bar": bar, "bars": bars, "until": until,
                      "total": total, "started": started}

    def draw_power(self, full) -> None:
        power, renderer = self.power, self.renderer
        shown = ease(min(1.0, (time.monotonic() - power["started"]) / 0.25))
        renderer.draw_blend_mode = 1
        renderer.draw_color = (0, 0, 0, int(160 * shown))
        renderer.fill_rect(full)
        texture, (x, y) = power["texture"], power["position"]
        texture.alpha = int(255 * shown)
        texture.draw(dstrect=(x, y, texture.width, texture.height))
        if power["bars"] is not None and power["until"] and power["total"]:
            bar = power["bar"]
            left = max(0.0, min(1.0, (power["until"] - time.time()) / power["total"]))
            back, front = power["bars"]
            back.alpha = front.alpha = int(255 * shown)
            back.draw(dstrect=(x + bar.x, y + bar.y, bar.w, bar.h))
            filled = int(bar.w * left)
            if filled > 0:
                front.draw(srcrect=(0, 0, filled, bar.h), dstrect=(x + bar.x, y + bar.y, filled, bar.h))

    def show_toast(self, message: str, index: int) -> None:
        painter = self.painter
        if painter.strip is None:
            painter.build_strip()
        image = painter.toast_image(message, painter.hero(index)["accent"])
        texture = self.texture(image)
        texture.blend_mode = 1
        self.toast = (texture, time.monotonic(), painter.toast_position(image))


class Screen:
    def __init__(self, home: str):
        self.home = home
        self.language = recalbox_language()
        self.running = True

    def run(self) -> int:
        os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")  # smooth when the page is turned (vertical screen)
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        import pygame

        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))
        conf = read_conf()
        # At boot the display can stay busy for a while after Recalbox's
        # interface was stopped: wait for it instead of failing.
        deadline = time.monotonic() + DISPLAY_WAIT_S
        while True:
            try:
                pygame.display.init()
                break
            except pygame.error as exc:
                if not self.running or time.monotonic() >= deadline:
                    raise
                print("display busy (%s): retrying" % exc, flush=True)
                pygame.display.quit()
                time.sleep(2.0)
        pygame.font.init()
        if not os.environ.get("RFID_SCREEN_SOFTWARE"):
            try:
                return self.run_gpu(pygame, conf)
            except Exception as exc:  # noqa: BLE001 - drawn by the processor instead
                print("graphics chip not available (%s): software drawing" % exc, flush=True)
        try:
            display = pygame.display.set_mode(screen_size(conf, wants_native(self.home)), pygame.FULLSCREEN)
        except pygame.error:
            display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
        angle = rotation()
        width, height = logical_size(display.get_size(), angle)
        surface = display if not angle else pygame.Surface((width, height)).convert()
        surface.fill(BACKGROUND)
        real_flip, real_update = pygame.display.flip, pygame.display.update

        def flip():
            if angle:
                display.blit(pygame.transform.rotate(surface, -angle), (0, 0))
            real_flip()

        def update(rect):
            if angle:
                flip()
            else:
                real_update(rect)

        flip()
        consoles = count_games()
        if not consoles:
            consoles = [{"id": "", "name": "Recalbox", "count": 0, "maker": "", "year": ""}]
        painter = Painter(pygame, width, height, consoles, self.language, region(conf))
        painter.home = self.home
        index, previous, changed = 0, None, time.monotonic()
        painter.hero(0)
        worker = {"thread": None}

        def prepare(target):
            try:
                painter.hero(target)
            except Exception:  # noqa: BLE001 - drawn when shown instead
                pass

        debug = bool(os.environ.get("RFID_SCREEN_DEBUG")) or os.path.exists("/tmp/rfid-screen-debug")
        frames, slowest, counted = 0, 0.0, time.monotonic()
        players, players_at = {}, 0.0
        messages, messages_at, toast = Messages(), 0.0, None
        launches, launch_page, waiting = Watcher(LAUNCH_FILE, max_age=CONFIRM_MAX_AGE_S), None, False
        pads = Pads(pygame)
        power_ui = PowerControl(self.home, self.language, pads)
        overlay = {"panel": None, "until": None, "total": None}
        dimmer = Dimmer(self.home)
        hints_at = None
        print("screen %dx%d, %d consoles" % (width, height, len(consoles)), flush=True)
        painter.compose(surface, index, None, 1.0, players, time.time())
        flip()
        while self.running:
            started = time.monotonic()
            for event in pygame.event.get():
                if event.type in (getattr(pygame, "JOYDEVICEADDED", -1), getattr(pygame, "JOYDEVICEREMOVED", -1)):
                    pads.open()
                    continue
                if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYHATMOTION, pygame.JOYAXISMOTION):
                    dark = dimmer.dark
                    dimmer.wake()
                    if dark and event.type == pygame.JOYBUTTONDOWN:
                        continue  # this press only wakes the screen up
                if power_ui.handle(event, busy=launch_page is not None):
                    continue
                elif event.type == pygame.JOYBUTTONDOWN and waiting:
                    answer_go()
                    waiting = False
            now = time.monotonic()
            if now - players_at >= 1.0:
                players, players_at = read_players(self.home), now
            launch = launches.poll()
            if launch is not None:
                waiting = bool(launch.get("confirm")) and not launch.get("cancel")
                launch_page = None if launch.get("cancel") else painter.launch_page(launch, waiting)
                if launch_page is None:
                    painter.scene(surface, index, None, 1.0)
                    painter.top(surface, index, players, time.time())
                    flip()
            power_ui.poll(busy=launch_page is not None)
            if power_ui.update(painter, lambda panel, until, total: overlay.update(panel=panel, until=until, total=total)) \
                    and overlay["panel"] is None:
                painter.scene(surface, index, None, 1.0)  # the panel closed: the consoles again
                painter.top(surface, index, players, time.time())
                flip()
            if hints_at is None or now - hints_at >= 10.0:
                hints_at = now
                refresh_hints(painter, self.home, self.language, players, power_ui)
            if launch_page is not None or overlay["panel"] is not None or toast is not None:
                dimmer.wake()
            was_dark = dimmer.dark
            dimmer.step()
            if dimmer.dark:
                painter.scene(surface, index, None, 1.0)
                painter.top(surface, index, players, time.time())
                veil = pygame.Surface((width, height), pygame.SRCALPHA)
                veil.fill((0, 0, 0, dimmer.alpha()))
                surface.blit(veil, (0, 0))
                flip()
                time.sleep(0.2)
                continue
            if was_dark:
                painter.scene(surface, index, None, 1.0)  # awake: the full picture again
                painter.top(surface, index, players, time.time())
                flip()
            if overlay["panel"] is not None:
                if launch_page is not None:
                    surface.blit(launch_page, (0, 0))
                else:
                    painter.scene(surface, index, None, 1.0)
                    painter.top(surface, index, players, time.time())
                dim = pygame.Surface((width, height), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 160))
                surface.blit(dim, (0, 0))
                image, bar = overlay["panel"]
                x, y = (width - image.get_width()) // 2, (height - image.get_height()) // 2
                surface.blit(image, (x, y))
                if bar is not None and overlay["until"] and overlay["total"]:
                    left = max(0.0, min(1.0, (overlay["until"] - time.time()) / overlay["total"]))
                    painter.draw_shape(surface, (x + bar.x, y + bar.y, bar.w, bar.h), (255, 255, 255, 40), bar.h // 2)
                    if int(bar.w * left) > bar.h:
                        painter.draw_shape(surface, (x + bar.x, y + bar.y, int(bar.w * left), bar.h),
                                           DEFAULT_ACCENT + (255,), bar.h // 2)
                flip()
                time.sleep(0.05)
                continue
            if launch_page is not None:
                surface.blit(launch_page, (0, 0))
                flip()
                time.sleep(0.05)
                continue
            if now - messages_at >= 0.25:
                messages_at = now
                message = messages.poll()
                if message:
                    image = painter.toast_image(message, painter.hero(index)["accent"])
                    toast = (image, now)
                    players_at = 0.0
            if toast is not None:
                alpha = toast_alpha(now - toast[1])
                painter.scene(surface, index, previous, min(1.0, (now - changed) / FADE_S) if previous is not None else 1.0)
                painter.top(surface, index, players, time.time())
                if alpha > 0:
                    toast[0].set_alpha(int(255 * alpha))
                    surface.blit(toast[0], painter.toast_position(toast[0]))
                else:
                    toast = None
                flip()
                time.sleep(0.03)
                continue
            following = (index + 1) % len(consoles)
            if now - changed >= HOLD_S and len(consoles) > 1 and painter.cached(following):
                previous, index, changed = index, following, now
                painter.shown = index
            progress = (now - changed) / FADE_S if previous is not None else 1.0
            if progress < 1.0:
                painter.scene(surface, index, previous, progress)
                painter.top(surface, index, players, time.time())
                flip()
            else:
                if previous is not None:  # end of a change: last full frame
                    previous = None
                    painter.scene(surface, index, None, 1.0)
                    painter.top(surface, index, players, time.time())
                    flip()
                else:
                    painter.top(surface, index, players, time.time())
                    update(painter.top_rect())
                # The next console is prepared during the pause, never during a change.
                nxt = (index + 1) % len(consoles)
                thread = worker["thread"]
                if not painter.cached(nxt) and (thread is None or not thread.is_alive()):
                    worker["thread"] = threading.Thread(target=prepare, args=(nxt,), daemon=True)
                    worker["thread"].start()
            if debug:
                frames += 1
                slowest = max(slowest, time.monotonic() - started)
                if time.monotonic() - counted >= 5:
                    print("%.1f fps, slowest %.0f ms" % (frames / (time.monotonic() - counted), slowest * 1000), flush=True)
                    frames, slowest, counted = 0, 0.0, time.monotonic()
            time.sleep(0.004 if progress < 1.0 else 0.08)
        pygame.display.quit()
        return 0


def _consoles():
    consoles = count_games()
    return consoles or [{"id": "", "name": "Recalbox", "count": 0, "maker": "", "year": ""}]


def _run_gpu(self, pygame, conf) -> int:
    from pygame._sdl2.video import Renderer, Window

    size = screen_size(conf, wants_native(self.home))
    if not size[0]:
        size = native_size(pygame)
    window = Window("Recalbox RFID", size=size, fullscreen=True)
    renderer = Renderer(window, accelerated=1, vsync=True)
    pygame.mouse.set_visible(False)
    angle = rotation()
    width, height = logical_size(size, angle)
    renderer.draw_color = BACKGROUND + (255,)
    renderer.clear()
    renderer.present()
    consoles = _consoles()
    painter = Painter(pygame, width, height, consoles, self.language, region(conf))
    painter.home = self.home
    gpu = GpuScreen(pygame, painter, window, renderer, angle=angle, screen=size)
    index, previous, changed = 0, None, time.monotonic()
    painter.hero(0)
    worker = {"thread": None}

    def prepare(target):
        try:
            painter.hero(target)
        except Exception:  # noqa: BLE001 - drawn when shown instead
            pass

    debug = bool(os.environ.get("RFID_SCREEN_DEBUG")) or os.path.exists("/tmp/rfid-screen-debug")
    frames, slowest, counted = 0, 0.0, time.monotonic()
    players, players_at = {}, 0.0
    messages, messages_at = Messages(), 0.0
    launches = Watcher(LAUNCH_FILE, max_age=CONFIRM_MAX_AGE_S)
    shown = {"launch": None, "waiting": False}
    show_player = wants(self.home, "player_games")
    pads = Pads(pygame)
    power_ui = PowerControl(self.home, self.language, pads)
    dimmer = Dimmer(self.home)
    hints_at, who = None, None
    print("screen %dx%d (rotation %d), %d consoles, graphics chip" % (size[0], size[1], angle, len(consoles)), flush=True)
    while self.running:
        started = time.monotonic()
        for event in pygame.event.get():
            if event.type in (getattr(pygame, "JOYDEVICEADDED", -1), getattr(pygame, "JOYDEVICEREMOVED", -1)):
                pads.open()
                continue
            if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYHATMOTION, pygame.JOYAXISMOTION):
                dark = dimmer.dark
                dimmer.wake()
                if dark and event.type == pygame.JOYBUTTONDOWN:
                    continue  # this press only wakes the screen up
            if power_ui.handle(event, busy=shown["launch"] is not None):
                continue
            elif event.type == pygame.JOYBUTTONDOWN and shown["waiting"]:
                answer_go()
                shown["waiting"] = False
                gpu.show_launch(shown["launch"], False)
        now = time.monotonic()
        if now - players_at >= 1.0:
            players, players_at = read_players(self.home), now
            info = player_info(players, self.language) if show_player else None
            if info and info.get("uid"):
                games = player_games(self.home, info["uid"])
                key = (info["uid"], json.dumps(games, sort_keys=True))
                gpu.set_page(key, lambda: painter.player_page(info["name"], games, painter.hero(index)["accent"]))
            else:
                gpu.set_page(None, None)
        launch = launches.poll()
        if launch is not None:
            if launch.get("cancel"):
                shown.update(launch=None, waiting=False)
                gpu.show_launch(None, False)
            else:
                shown.update(launch=launch, waiting=bool(launch.get("confirm")))
                gpu.show_launch(launch, shown["waiting"])
        if now - messages_at >= 0.25:
            messages_at = now
            message = messages.poll()
            if message:
                gpu.show_toast(message, index)
                dimmer.wake()
                players_at = 0.0  # the message often comes with a new player state
        power_ui.poll(busy=shown["launch"] is not None)
        power_ui.update(painter, gpu.show_power)
        if shown["launch"] is not None or power_ui.state is not None or power_ui.menu is not None:
            dimmer.wake()
        current = (player_info(players, self.language) or {}).get("uid")
        if current != who:
            who, hints_at = current, None
            dimmer.wake()
        if hints_at is None or now - hints_at >= 10.0:
            hints_at = now
            refresh_hints(painter, self.home, self.language, players, power_ui)
        dimmer.step()
        gpu.dim_alpha = dimmer.alpha()
        following = (index + 1) % len(consoles)
        if gpu.page is None and now - changed >= HOLD_S and len(consoles) > 1 and painter.cached(following):
            previous, index, changed = index, following, now
            painter.shown = index
            gpu.hero(index)  # sent to the chip before the change starts
        progress = (now - changed) / FADE_S if previous is not None else 1.0
        if progress >= 1.0:
            previous = None
            nxt = (index + 1) % len(consoles)
            thread = worker["thread"]
            if not painter.cached(nxt) and (thread is None or not thread.is_alive()):
                worker["thread"] = threading.Thread(target=prepare, args=(nxt,), daemon=True)
                worker["thread"].start()
        # The chosen logo lights up once the band has stopped moving.
        highlight = ease((now - changed - FADE_S) / HIGHLIGHT_S) if previous is None and now - changed < FADE_S + HIGHLIGHT_S else (0.0 if previous is not None else 1.0)
        gpu.draw(index, previous, progress, players, time.time(), highlight)  # waits for the screen (vsync)
        if debug:
            frames += 1
            slowest = max(slowest, time.monotonic() - started)
            if time.monotonic() - counted >= 5:
                print("%.1f fps, slowest %.0f ms" % (frames / (time.monotonic() - counted), slowest * 1000), flush=True)
                frames, slowest, counted = 0, 0.0, time.monotonic()
        if progress >= 1.0:
            # The pulse only: no need for every screen refresh (even less when dark).
            time.sleep(0.15 if dimmer.level >= 1.0 else 0.02)
    gpu.toast = gpu.page = gpu.launch = gpu.power = None
    gpu._bar = gpu.chip = gpu.chip_out = None
    gpu.canvas = None
    # Textures first, then the renderer and the window: freed in another
    # order, SDL crashes while quitting.
    gpu.heroes.clear()
    gpu.plates = []
    gpu.static = gpu.top_texture = gpu.hint_texture = None
    del gpu
    del renderer
    window.destroy()
    del window
    sys.stdout.flush()
    os._exit(0)


Screen.run_gpu = _run_gpu


def run(home: str) -> int:
    return Screen(home).run()


def preview(output: str, width: int = 1280, height: int = 720, at=(0.0,), players=None, counts=None,
            home: str = None) -> list:
    """Draws frames into PNG files (no screen): output-<n>.png."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    import pygame

    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    consoles = counts if counts is not None else count_games()
    painter = Painter(pygame, width, height, consoles, "fr")
    painter.home = home
    written = []
    for number, (index, previous, progress) in enumerate(at):
        surface = pygame.Surface((width, height))
        painter.compose(surface, index, previous, progress, players or {}, 1.0)
        path = "%s-%d.png" % (output, number)
        pygame.image.save(surface, path)
        written.append(path)
    return written
