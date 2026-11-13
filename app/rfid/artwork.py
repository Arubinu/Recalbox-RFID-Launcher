"""Game pictures from the libretro thumbnail server (no account needed).

https://thumbnails.libretro.com/<system>/<folder>/<game>.png, the database used
by RetroArch: box art, in-game screenshot, title screen and game logo. Names
follow No-Intro ("Tetris (World) (Rev 1)"), so a game is matched from its file
name first, then from its gamelist name.

The folder listings (one per system and kind) are cached on disk for two
weeks: one download per system, then only the chosen picture is fetched.
Everything is the standard library; nothing is sent but the system and game
names, in the URL.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://thumbnails.libretro.com"
USER_AGENT = "recalbox-rfid-launcher"
INDEX_TTL_S = 14 * 24 * 3600
#: A failed listing is tried again after this delay (no internet, server down).
FAILURE_TTL_S = 10 * 60
MAX_PICTURE_BYTES = 8 * 1024 * 1024

#: kind -> folder on the server.
KINDS = {
    "boxart": "Named_Boxarts",
    "snap": "Named_Snaps",
    "title": "Named_Titles",
    "logo": "Named_Logos",
}

#: Recalbox system -> libretro system name (unknown systems: no picture).
SYSTEMS = {
    "nes": "Nintendo - Nintendo Entertainment System",
    "fds": "Nintendo - Family Computer Disk System",
    "snes": "Nintendo - Super Nintendo Entertainment System",
    "satellaview": "Nintendo - Satellaview",
    "sufami": "Nintendo - Sufami Turbo",
    "n64": "Nintendo - Nintendo 64",
    "64dd": "Nintendo - Nintendo 64DD",
    "gb": "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
    "gba": "Nintendo - Game Boy Advance",
    "nds": "Nintendo - Nintendo DS",
    "virtualboy": "Nintendo - Virtual Boy",
    "gamecube": "Nintendo - GameCube",
    "wii": "Nintendo - Wii",
    "pokemini": "Nintendo - Pokemon Mini",
    "gw": "Handheld Electronic Game",
    "sg1000": "Sega - SG-1000",
    "mastersystem": "Sega - Master System - Mark III",
    "megadrive": "Sega - Mega Drive - Genesis",
    "segacd": "Sega - Mega-CD - Sega CD",
    "sega32x": "Sega - 32X",
    "gamegear": "Sega - Game Gear",
    "saturn": "Sega - Saturn",
    "dreamcast": "Sega - Dreamcast",
    "naomi": "Sega - Naomi",
    "naomigd": "Sega - Naomi",
    "atomiswave": "Atomiswave",
    "psx": "Sony - PlayStation",
    "ps2": "Sony - PlayStation 2",
    "psp": "Sony - PlayStation Portable",
    "pcengine": "NEC - PC Engine - TurboGrafx 16",
    "pcenginecd": "NEC - PC Engine CD - TurboGrafx-CD",
    "supergrafx": "NEC - PC Engine SuperGrafx",
    "pcfx": "NEC - PC-FX",
    "neogeo": "SNK - Neo Geo",
    "neogeocd": "SNK - Neo Geo CD",
    "ngp": "SNK - Neo Geo Pocket",
    "ngpc": "SNK - Neo Geo Pocket Color",
    "fbneo": "FBNeo - Arcade Games",
    "mame": "MAME",
    "atari2600": "Atari - 2600",
    "atari5200": "Atari - 5200",
    "atari7800": "Atari - 7800",
    "atari800": "Atari - 8-bit",
    "lynx": "Atari - Lynx",
    "jaguar": "Atari - Jaguar",
    "atarist": "Atari - ST",
    "colecovision": "Coleco - ColecoVision",
    "intellivision": "Mattel - Intellivision",
    "vectrex": "GCE - Vectrex",
    "o2em": "Magnavox - Odyssey2",
    "videopac": "Magnavox - Odyssey2",
    "channelf": "Fairchild - Channel F",
    "wswan": "Bandai - WonderSwan",
    "wswanc": "Bandai - WonderSwan Color",
    "3do": "The 3DO Company - 3DO",
    "msx1": "Microsoft - MSX",
    "msx2": "Microsoft - MSX2",
    "amstradcpc": "Amstrad - CPC",
    "gx4000": "Amstrad - GX4000",
    "c64": "Commodore - 64",
    "amiga600": "Commodore - Amiga",
    "amiga1200": "Commodore - Amiga",
    "amigacd32": "Commodore - CD32",
    "amigacdtv": "Commodore - CDTV",
    "zxspectrum": "Sinclair - ZX Spectrum",
    "zx81": "Sinclair - ZX 81",
    "x68000": "Sharp - X68000",
    "dos": "DOS",
    "scummvm": "ScummVM",
    "arduboy": "Arduboy Inc - Arduboy",
    "uzebox": "Uzebox",
    "lutro": "Lutro",
    "tic80": "TIC-80",
    "wasm4": "WASM-4",
}

#: Characters the server replaces with "_" in file names.
_FORBIDDEN = re.compile(r'[&*/:`<>?\\|"]')
_TAGS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_REGIONS = ("world", "usa", "europe", "japan")
_PLAIN_TAGS = re.compile(r"^(world|usa|europe|japan|france|germany|spain|italy|brazil|korea|australia|asia|"
                         r"canada|netherlands|sweden|[a-z]{2}|rev \w+|v\d[\w.]*)$")
_BAD_TAGS = ("beta", "proto", "demo", "sample", "pirate", "hack", "unl")


class ArtworkError(Exception):
    pass


def server_name(name: str) -> str:
    """Name as the server stores it (forbidden characters become "_")."""
    return _FORBIDDEN.sub("_", name)


def title_key(name: str) -> str:
    """Comparison key: no tags, accents, articles or punctuation.

    "Legend of Zelda, The - Link's Awakening (USA)" and
    "The Legend of Zelda: Link's Awakening" give the same key.
    """
    text = _TAGS.sub("", str(name or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ").replace("_", " ")
    text = re.sub(r",\s*(the|a|an|le|la|les)\b", " ", text)
    text = re.sub(r"^(the|a|an|le|la|les)\s+", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tags(name: str) -> set:
    return {tag.strip().lower() for group in re.findall(r"[\(\[]([^\)\]]*)[\)\]]", name or "")
            for tag in group.split(",") if tag.strip()}


def _score(candidate: str, wanted_tags: set) -> tuple:
    tags = _tags(candidate)
    shared = len(tags & wanted_tags)
    bad = sum(1 for tag in tags if any(tag.startswith(b) for b in _BAD_TAGS))
    # Compilations, re-releases...: tags that are neither a region, a
    # language nor a revision, and that the ROM name does not have.
    extra = sum(1 for tag in tags - wanted_tags if not _PLAIN_TAGS.match(tag))
    region = min((_REGIONS.index(tag) for tag in tags if tag in _REGIONS), default=len(_REGIONS))
    return (-shared, bad, extra, region, len(candidate), candidate)


def match(names, rom_path: str, game_name: str = "") -> str:
    """Best server name for a game, or ""."""
    if not names:
        return ""
    base = os.path.splitext(os.path.basename(str(rom_path or "").replace("\\", "/")))[0]
    exact = {server_name(item).lower(): item for item in names}
    for wanted in (base, game_name):
        if wanted and server_name(wanted).lower() in exact:
            return exact[server_name(wanted).lower()]
    by_key = {}
    for item in names:
        by_key.setdefault(title_key(item), []).append(item)
    wanted_tags = _tags(base)
    for wanted in (base, game_name):
        key = title_key(wanted)
        if key and key in by_key:
            return sorted(by_key[key], key=lambda item: _score(item, wanted_tags))[0]
    return ""


def _parse_listing(html: str) -> list:
    names = []
    for href in re.findall(r'href="([^"]+\.png)"', html, flags=re.I):
        name = urllib.parse.unquote(href.rsplit("/", 1)[-1])
        names.append(name[:-4])
    return names


def _http_get(url: str, timeout: float = 15.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            data = answer.read(MAX_PICTURE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return b""
        raise ArtworkError("serveur d'images : erreur %s" % exc.code)
    except (urllib.error.URLError, OSError) as exc:
        raise ArtworkError("serveur d'images injoignable (%s)" % getattr(exc, "reason", exc))
    if len(data) > MAX_PICTURE_BYTES:
        raise ArtworkError("image trop grande")
    return data


class Artwork:
    """Lists and downloads the libretro pictures of a game."""

    def __init__(self, cache_dir: str, http_get=None, log=None, now=None):
        self.cache_dir = cache_dir
        self._http_get = http_get or _http_get
        self.log = log
        self._now = now or time.time
        self._indexes = {}
        self._failures = {}
        self._lock = threading.Lock()

    # -------------------------------------------------------------- indexes
    def _cache_path(self, system_name: str, kind: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", system_name).strip("_")
        return os.path.join(self.cache_dir, "%s.%s.json" % (safe, kind))

    def index(self, system: str, kind: str) -> list:
        """Picture names of a system for one kind (cached)."""
        system_name = SYSTEMS.get(system)
        if not system_name or kind not in KINDS:
            return []
        key = (system_name, kind)
        now = self._now()
        with self._lock:
            cached = self._indexes.get(key)
            if cached and now - cached[0] < INDEX_TTL_S:
                return cached[1]
            failed = self._failures.get(key)
            if failed and now - failed < FAILURE_TTL_S:
                raise ArtworkError("serveur d'images injoignable")
        path = self._cache_path(system_name, kind)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if now - float(stored.get("time", 0)) < INDEX_TTL_S and isinstance(stored.get("names"), list):
                with self._lock:
                    self._indexes[key] = (float(stored["time"]), stored["names"])
                return stored["names"]
        except (OSError, ValueError, TypeError):
            pass
        url = "%s/%s/%s/" % (BASE_URL, urllib.parse.quote(system_name), KINDS[kind])
        try:
            html = self._http_get(url).decode("utf-8", "replace")
        except ArtworkError:
            with self._lock:
                self._failures[key] = now
            raise
        names = _parse_listing(html)
        with self._lock:
            self._indexes[key] = (now, names)
            self._failures.pop(key, None)
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            temporary = path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"time": now, "names": names}, handle)
            os.replace(temporary, path)
        except OSError as exc:
            if self.log:
                self.log.warning("Cache des images libretro non ecrit : %s" % exc)
        return names

    # ------------------------------------------------------------- pictures
    def available(self, system: str, rom_path: str, game_name: str = "") -> dict:
        """kind -> server name, for the kinds that exist for this game."""
        found = {}
        for kind in KINDS:
            name = match(self.index(system, kind), rom_path, game_name)
            if name:
                found[kind] = name
        return found

    def picture(self, system: str, kind: str, name: str):
        """(content type, bytes) of one picture, or None."""
        system_name = SYSTEMS.get(system)
        if not system_name or kind not in KINDS or not name:
            return None
        if name not in self.index(system, kind):
            return None
        url = "%s/%s/%s/%s.png" % (BASE_URL, urllib.parse.quote(system_name), KINDS[kind],
                                   urllib.parse.quote(server_name(name)))
        data = self._http_get(url)
        if not data or not data.startswith(b"\x89PNG"):
            return None
        return "image/png", data
