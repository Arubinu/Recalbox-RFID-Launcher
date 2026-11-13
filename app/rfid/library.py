"""Game library: systems, games, pictures and console logos.

Two sources, in this order:

1. the **web API built into the Recalbox 10 frontend** (port 81). It knows
   exactly what the menu shows: active systems, games with their scraped
   name, favourites, scraped pictures, and the theme logo of every console
   (SVG), e.g. ::

       GET /api/systems/getactives
       GET /api/systems/<system>/roms
       GET /api/systems/<system>/roms/metadata/image/<url-encoded full path>
       GET /api/systems/<system>/resource/<region>/svg/logo

2. the ``gamelist.xml`` files of the ROM folders (Recalbox 9, or when the
   API does not answer). No logo in that case.

Everything comes from the standard library; the answers are cached for a
short while so that a search typed letter by letter stays fast.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:  # xml.etree may be missing from a minimal Python build
    import xml.etree.ElementTree as ElementTree
except ImportError:  # pragma: no cover - platform dependent
    ElementTree = None

#: Frontend web API (Recalbox 10).
API_BASE = "http://127.0.0.1:81"

#: ROM folders: writable share first, then the read-only base.
ROMS_DIRS = ("/recalbox/share/roms", "/recalbox/share_init/roms")

#: Systems that are not real game lists.
VIRTUAL_SYSTEMS = ("challenges", "favorites", "lastplayed", "multiplayer", "imageviewer")

#: Pictures and logos larger than this are refused (WebSocket message size).
MAX_MEDIA_BYTES = 3 * 1024 * 1024

#: Cache lifetime (seconds).
CACHE_S = 60.0

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


class LibraryError(Exception):
    """The library could not be read."""


def _http_get(url: str, timeout: float = 4.0):
    """Returns (content type, bytes) or raises LibraryError."""
    request = urllib.request.Request(url, headers={"User-Agent": "recalbox-rfid"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            data = answer.read(MAX_MEDIA_BYTES + 1)
            kind = answer.headers.get("Content-Type", "") or ""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LibraryError("API indisponible : %s" % exc)
    if len(data) > MAX_MEDIA_BYTES:
        raise LibraryError("fichier trop volumineux")
    return kind.split(";")[0].strip().lower(), data


def _text(node, tag: str) -> str:
    child = node.find(tag) if node is not None else None
    return (child.text or "").strip() if child is not None and child.text else ""


class Library:
    """Read access to the games known by the Recalbox."""

    def __init__(self, api_base: str = API_BASE, roms_dirs=ROMS_DIRS, log=None, http_get=None):
        self.api_base = api_base.rstrip("/")
        self.roms_dirs = tuple(roms_dirs)
        self.log = log
        self._http_get = http_get or _http_get
        self._lock = threading.Lock()
        self._systems = None
        self._systems_at = 0.0
        self._games = {}
        self._api_ok = None

    # ------------------------------------------------------------- systems
    def systems(self, force: bool = False) -> list:
        """Active systems: [{"id", "name", "manufacturer"}], menu order."""
        with self._lock:
            if not force and self._systems is not None and time.monotonic() - self._systems_at < CACHE_S:
                return list(self._systems)
        found = None
        try:
            found = self._api_systems()
            self._api_ok = True
        except LibraryError:
            self._api_ok = False
        if found is None:
            found = self._folder_systems()
        with self._lock:
            self._systems = found
            self._systems_at = time.monotonic()
        return list(found)

    def _api_systems(self) -> list:
        kind, data = self._http_get(self.api_base + "/api/systems/getactives")
        try:
            payload = json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            raise LibraryError("reponse illisible")
        result = []
        for item in payload.get("systems") or []:
            name = str(item.get("name") or "").strip()
            if not name or name in VIRTUAL_SYSTEMS:
                continue
            result.append({
                "id": name,
                "name": str(item.get("fullName") or name),
                "manufacturer": str(item.get("manufacturer") or ""),
                "region": str(item.get("themeRegion") or ""),
            })
        return result

    def _folder_systems(self) -> list:
        seen = []
        for base in self.roms_dirs:
            try:
                names = sorted(os.listdir(base))
            except OSError:
                continue
            for name in names:
                if name in seen or name in VIRTUAL_SYSTEMS:
                    continue
                if os.path.isfile(os.path.join(base, name, "gamelist.xml")):
                    seen.append(name)
        return [{"id": name, "name": name, "manufacturer": "", "region": ""} for name in seen]

    # --------------------------------------------------------------- games
    def games(self, system: str, force: bool = False) -> list:
        """Games of one system: [{"system", "path", "name", "favorite", "genre"}]."""
        system = str(system or "").strip()
        if not system or "/" in system or system.startswith("."):
            raise LibraryError("console inconnue")
        with self._lock:
            cached = self._games.get(system)
            if not force and cached and time.monotonic() - cached[0] < CACHE_S:
                return list(cached[1])
        found = None
        if self._api_ok is not False:
            try:
                found = self._api_games(system)
            except LibraryError:
                found = None
        if found is None:
            found = self._gamelist_games(system)
        with self._lock:
            self._games[system] = (time.monotonic(), found)
        return list(found)

    def _api_games(self, system: str) -> list:
        url = "%s/api/systems/%s/roms" % (self.api_base, urllib.parse.quote(system, safe=""))
        kind, data = self._http_get(url)
        try:
            payload = json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            raise LibraryError("reponse illisible")
        result = []
        for item in payload.get("roms") or []:
            path = str(item.get("path") or "")
            if not path:
                continue
            result.append({
                "system": system,
                "path": path,
                "name": str(item.get("name") or os.path.splitext(os.path.basename(path))[0]),
                "favorite": bool(item.get("favorite")),
                "genre": str(item.get("genre") or ""),
            })
        return result

    def _gamelist(self, system: str):
        """Yields (folder, <game> node) for every gamelist.xml of a system."""
        if ElementTree is None:
            return
        for base in self.roms_dirs:
            folder = os.path.join(base, system)
            path = os.path.join(folder, "gamelist.xml")
            if not os.path.isfile(path):
                continue
            try:
                tree = ElementTree.parse(path)
            except (OSError, ElementTree.ParseError) as exc:
                if self.log:
                    self.log.warning("gamelist.xml illisible (%s) : %s" % (path, exc))
                continue
            for node in tree.getroot().iter("game"):
                yield folder, node

    def _gamelist_games(self, system: str) -> list:
        result = []
        seen = set()
        for folder, node in self._gamelist(system):
            relative = _text(node, "path")
            if not relative:
                continue
            full = os.path.normpath(os.path.join(folder, relative)).replace("\\", "/")
            if full in seen or _text(node, "hidden").lower() == "true":
                continue
            seen.add(full)
            result.append({
                "system": system,
                "path": full,
                "name": _text(node, "name") or os.path.splitext(os.path.basename(full))[0],
                "favorite": _text(node, "favorite").lower() == "true",
                "genre": _text(node, "genre"),
            })
        result.sort(key=lambda item: item["name"].lower())
        return result

    def search(self, query: str = "", system: str = "", limit: int = 60) -> list:
        """Games whose name holds every word of ``query`` (accents ignored)."""
        words = [word for word in _fold(query).split() if word]
        systems = [system] if system else [item["id"] for item in self.systems()]
        found = []
        for name in systems:
            try:
                games = self.games(name)
            except LibraryError:
                continue
            for game in games:
                haystack = _fold(game["name"] + " " + os.path.basename(game["path"]))
                if all(word in haystack for word in words):
                    found.append(game)
                    if len(found) >= limit:
                        return found
        return found

    def pick_random(self, system: str = "", favorites_only: bool = False, rng=None):
        """A random game (optionally from one system or among favourites)."""
        rng = rng or random
        systems = [system] if system else [item["id"] for item in self.systems()]
        pool = []
        for name in systems:
            try:
                games = self.games(name)
            except LibraryError:
                continue
            pool.extend(game for game in games if game["favorite"] or not favorites_only)
        return rng.choice(pool) if pool else None

    # --------------------------------------------------------------- media
    def game_image(self, system: str, path: str):
        """Scraped picture of a game: (content type, bytes) or None."""
        if not system or not path:
            return None
        if self._api_ok is not False:
            url = "%s/api/systems/%s/roms/metadata/image/%s" % (
                self.api_base,
                urllib.parse.quote(system, safe=""),
                urllib.parse.quote(path, safe=""),
            )
            try:
                kind, data = self._http_get(url, timeout=6.0)
                if data and kind.startswith("image/"):
                    return kind, data
            except LibraryError:
                pass
        return self._gamelist_image(system, path)

    def _gamelist_image(self, system: str, path: str):
        for folder, node in self._gamelist(system):
            relative = _text(node, "path")
            if not relative:
                continue
            full = os.path.normpath(os.path.join(folder, relative)).replace("\\", "/")
            if full != path.replace("\\", "/"):
                continue
            for tag in ("image", "thumbnail"):
                picture = _text(node, tag)
                if not picture:
                    continue
                picture_path = os.path.normpath(os.path.join(folder, picture))
                kind = MEDIA_TYPES.get(os.path.splitext(picture_path)[1].lower())
                if not kind:
                    continue
                try:
                    if os.path.getsize(picture_path) > MAX_MEDIA_BYTES:
                        continue
                    with open(picture_path, "rb") as handle:
                        return kind, handle.read()
                except OSError:
                    continue
        return None

    def system_logo(self, system: str, kind: str = "logo", region: str = ""):
        """Theme picture of a console (SVG): logo, console, controller."""
        if kind not in ("logo", "console", "controller", "game"):
            raise LibraryError("image inconnue")
        if not system or "/" in system:
            return None
        regions = [region] if region else []
        regions += [item for item in ("eu", "us", "jp", "world") if item not in regions]
        for candidate in regions:
            url = "%s/api/systems/%s/resource/%s/svg/%s" % (
                self.api_base,
                urllib.parse.quote(system, safe=""),
                urllib.parse.quote(candidate, safe=""),
                kind,
            )
            try:
                content_type, data = self._http_get(url)
            except LibraryError:
                return None
            if data and "svg" in content_type:
                return content_type, data
        return None


def _fold(text: str) -> str:
    """Lowercase text without accents (search)."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def relative_to_system(system: str, path: str) -> str:
    """``/recalbox/share/roms/snes/a/b.smc`` -> ``a/b.smc`` (portable reference)."""
    normalized = str(path or "").replace("\\", "/")
    for base in ROMS_DIRS:
        prefix = "%s/%s/" % (base, system)
        if normalized.startswith(prefix):
            return normalized[len(prefix):]
    return os.path.basename(normalized)


def find_rom(system: str, relative: str, roms_dirs=ROMS_DIRS) -> str:
    """Full path of a game on THIS Recalbox (share first), or ""."""
    relative = str(relative or "").lstrip("/")
    if not system or not relative or ".." in relative.split("/"):
        return ""
    for base in roms_dirs:
        candidate = "%s/%s/%s" % (base, system, relative)
        if os.path.isfile(candidate):
            return candidate
    return ""
