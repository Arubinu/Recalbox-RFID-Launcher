"""Badge database: a plain JSON file.

Why JSON rather than SQLite?

* the ``sqlite3`` module is not guaranteed in the Recalbox image (Buildroot
  only builds the Python modules explicitly requested);
* a JSON file can be read and edited by hand, is copied like any file
  (backup) and can be edited in a spreadsheet through the CSV export;
* writes are atomic (temporary file + ``os.replace``): a power cut cannot
  leave a half-written file.

File structure ::

    {
      "schema": 1,
      "updated": "2026-01-01T12:00:00",
      "tags": {
        "A1B2C3D4": {
          "system": "snes",
          "game": "Super Mario World.smc",
          "name": "Super Mario World",
          "path": "/recalbox/share/roms/snes/Super Mario World.smc",
          "created": "2026-01-01T12:00:00",
          "last_used": null,
          "hits": 0
        }
      }
    }
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import shutil
import tempfile
import time

SCHEMA_VERSION = 1

CSV_FIELDS = ("uid", "system", "game", "name", "kind", "action", "params", "limit_min")

#: Kinds of entries: a game, or a special card (action).
KIND_GAME = "game"
KIND_ACTION = "action"

#: Special cards.
#:   random   = starts a random game (all consoles, one console, favourites)
#:   quit     = quits the running game
#:   bonus    = extra play time for a time-limited game
#:   poweroff = turns the Recalbox off
#:   player   = player card (time counted per person)
#:   unlock   = opens the locked Recalbox menu, and locks it again
#:   pause    = pauses the game (and the time), or resumes it
#:   save     = saves the game now (resumed at the next start)
#:   sound    = mutes the Recalbox, or brings the sound back
#:   time     = shows the time left to the active player
#:   reward   = more play time for a player, today or this week
#:   continue = starts again the last game of the active player (or the last one)
ACTIONS = ("random", "quit", "bonus", "poweroff", "player", "unlock", "pause", "save", "sound", "time", "reward",
           "continue")

#: Games of a "collection" card (a random game among a chosen list).
MAX_COLLECTION = 200

#: Play time periods of a player card.
PLAYER_PERIODS = ("day", "week")


def clean_limit(value):
    """Time limit of a card: None = the general setting, 0 = no limit."""
    if value is None or value == "":
        return None
    try:
        minutes = int(float(value))
    except (TypeError, ValueError):
        raise StorageError("limite de temps invalide : %r" % (value,))
    if minutes < 0 or minutes > 24 * 60:
        raise StorageError("limite de temps hors bornes (0 a 1440 minutes)")
    return minutes


def _clock_time(value) -> str:
    """"HH:MM" (24 h), or "" when empty."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        hours, minutes = (int(part) for part in text.split(":", 1))
    except (TypeError, ValueError):
        raise StorageError("heure invalide : %r (HH:MM attendu)" % (value,))
    if not (0 <= hours <= 24 and 0 <= minutes <= 59) or (hours == 24 and minutes):
        raise StorageError("heure invalide : %r" % (value,))
    return "%02d:%02d" % (hours, minutes)


def _games_list(items, limit: int = 200) -> list:
    """[{"system", "path", "name"}] of a list sent by the page (bad items skipped)."""
    games = []
    for item in list(items or [])[:limit]:
        if not isinstance(item, dict):
            continue
        game_system = str(item.get("system") or "").strip()
        game_path = str(item.get("path") or "").strip()
        if not game_system or "/" in game_system or not (game_path.startswith("/") or os.path.isabs(game_path)):
            continue
        name = str(item.get("name") or "").strip()[:120]
        games.append({"system": game_system, "path": game_path,
                      "name": name or os.path.splitext(os.path.basename(game_path))[0]})
    return games


def clean_params(action: str, params) -> dict:
    """Checks the parameters of a special card and returns a clean copy."""
    params = dict(params or {})
    if action == "random":
        system = str(params.get("system") or "").strip()
        if "/" in system:
            raise StorageError("console invalide")
        result = {"system": system, "favorites": bool(params.get("favorites"))}
        games = _games_list(params.get("games"), MAX_COLLECTION)
        if games:
            result["games"] = games
        return result
    if action == "bonus":
        try:
            minutes = int(float(params.get("minutes") or 10))
            uses_raw = params.get("uses")
            uses = int(float(uses_raw if uses_raw not in (None, "") else 1))
            period_h = int(float(params.get("period_h") or 24))
        except (TypeError, ValueError):
            raise StorageError("parametres de la carte bonus invalides")
        if not 1 <= minutes <= 240:
            raise StorageError("temps bonus : 1 a 240 minutes")
        if not 0 <= uses <= 50:
            raise StorageError("nombre d'utilisations : 0 a 50 (0 = illimite)")
        if not 1 <= period_h <= 24 * 31:
            raise StorageError("periode : 1 heure a 31 jours")
        return {"minutes": minutes, "uses": uses, "period_h": period_h}
    if action == "player":
        # Play time allowed to this person per day or week (0 = no limit).
        try:
            quota = int(float(params.get("quota_min") or 0))
        except (TypeError, ValueError):
            raise StorageError("parametres de la carte joueur invalides")
        if not 0 <= quota <= 24 * 60 * 7:
            raise StorageError("temps du joueur : 0 a 10080 minutes (0 = illimite)")
        period = str(params.get("period") or "day")
        if period not in PLAYER_PERIODS:
            raise StorageError("periode du joueur : jour ou semaine")
        result = {"quota_min": quota, "period": period}
        # Another time per day on some days (the weekend by default) and in the holidays.
        alt = params.get("alt_min")
        if alt not in (None, "") and period == "day":
            try:
                alt = int(float(alt))
            except (TypeError, ValueError):
                raise StorageError("autre temps du joueur invalide")
            if not 0 <= alt <= 24 * 60:
                raise StorageError("autre temps du joueur : 0 a 1440 minutes (0 = illimite)")
            result["alt_min"] = alt
            alt_days = sorted({int(day) for day in (params.get("alt_days") or []) if str(day).isdigit() and 0 <= int(day) <= 6})
            if alt_days and alt_days != [5, 6]:
                result["alt_days"] = alt_days
        # Guest card: for a friend passing by, until a day (included).
        if params.get("guest"):
            result["guest"] = True
            until = str(params.get("until") or "").strip()
            if until:
                try:
                    datetime.date.fromisoformat(until)
                except ValueError:
                    raise StorageError("carte invite : date de fin invalide")
                result["until"] = until
        # Time slots: the days (0 = Monday) and the hours the player may play.
        days = sorted({int(day) for day in (params.get("days") or []) if str(day).isdigit() and 0 <= int(day) <= 6})
        if days and len(days) < 7:
            result["days"] = days
        start, end = _clock_time(params.get("from")), _clock_time(params.get("to"))
        if start or end:
            start, end = start or "00:00", end or "24:00"
            if start >= end:
                raise StorageError("plage horaire : l'heure de fin doit suivre l'heure de debut")
            result["from"], result["to"] = start, end
        # Allowed games: some consoles and/or some games (nothing = every game).
        systems = sorted({str(name).strip() for name in (params.get("systems") or [])
                          if str(name).strip() and "/" not in str(name)})
        games = _games_list(params.get("games"))
        if systems:
            result["systems"] = systems
        if games:
            result["games"] = games
        return result
    if action == "reward":
        try:
            minutes = int(float(params.get("minutes") or 15))
            uses_raw = params.get("uses")
            uses = int(float(uses_raw if uses_raw not in (None, "") else 1))
            period_h = int(float(params.get("period_h") or 24))
        except (TypeError, ValueError):
            raise StorageError("parametres de la carte recompense invalides")
        if not 1 <= minutes <= 600:
            raise StorageError("recompense : 1 a 600 minutes")
        if not 0 <= uses <= 50:
            raise StorageError("nombre d'utilisations : 0 a 50 (0 = illimite)")
        if not 1 <= period_h <= 24 * 31:
            raise StorageError("periode : 1 heure a 31 jours")
        player = str(params.get("player") or "").strip().upper()
        if player and any(char not in "0123456789ABCDEF" for char in player):
            raise StorageError("joueur invalide")
        return {"player": player, "minutes": minutes, "uses": uses, "period_h": period_h}
    return {}


class StorageError(Exception):
    """Database read/write error."""


def normalize_uid(raw) -> str:
    """Normalizes a badge UID: ``a1:b2:c3:d4`` -> ``A1B2C3D4``.

    Accepts the usual separators (spaces, colons, dashes) and lowercase, to
    tolerate UIDs copied from a terminal or a CSV file.
    """
    if raw is None:
        raise StorageError("UID vide")
    text = str(raw)
    for separator in (":", "-", " ", "_", "."):
        text = text.replace(separator, "")
    text = text.upper()
    if not text:
        raise StorageError("UID vide")
    if any(char not in "0123456789ABCDEF" for char in text):
        raise StorageError("UID invalide (hexadecimal attendu) : %r" % (raw,))
    if len(text) < 4 or len(text) % 2 != 0:
        raise StorageError("UID de longueur invalide : %r" % (raw,))
    return text


def pretty_uid(uid: str) -> str:
    """Returns the UID as ``A1:B2:C3:D4`` (display only)."""
    return ":".join(uid[i:i + 2] for i in range(0, len(uid), 2))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class TagStore:
    """Badge <-> game mappings, persisted in a JSON file."""

    def __init__(self, path: str, log=None):
        self.path = os.path.abspath(path)
        self.log = log
        self._data = self._empty()
        self._mtime = 0.0
        self._loaded = False

    # ------------------------------------------------------------------ interne
    @staticmethod
    def _empty() -> dict:
        return {"schema": SCHEMA_VERSION, "updated": _now(), "tags": {}}

    def _stat_mtime(self) -> float:
        try:
            return os.stat(self.path).st_mtime
        except OSError:
            return 0.0

    @property
    def tags(self) -> dict:
        return self._data["tags"]

    # ------------------------------------------------------------------ lecture
    def load(self) -> None:
        """Loads the file (or creates an empty database if missing)."""
        self._data = self._empty()
        self._mtime = self._stat_mtime()
        self._loaded = True
        if not os.path.isfile(self.path):
            return

        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            # An unreadable database is never destroyed: it is kept for analysis
            # and the service starts again from an empty copy.
            backup = self.path + ".corrupt-%s" % time.strftime("%Y%m%d-%H%M%S")
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                backup = "(sauvegarde impossible)"
            if self.log:
                self.log.error("Base illisible (%s) : %s ; copie dans %s" % (exc, self.path, backup))
            return

        if not isinstance(raw, dict) or not isinstance(raw.get("tags"), dict):
            if self.log:
                self.log.error("Format de base inattendu dans %s (ignore)" % self.path)
            return

        tags = {}
        for uid, entry in raw["tags"].items():
            try:
                normalized = normalize_uid(uid)
            except StorageError:
                if self.log:
                    self.log.warning("Badge ignore (UID invalide) : %r" % (uid,))
                continue
            if not isinstance(entry, dict):
                continue
            try:
                tags[normalized] = self._clean_entry(entry)
            except StorageError as exc:
                if self.log:
                    self.log.warning("Badge %s ignore (%s)" % (pretty_uid(normalized), exc))

        self._data = {
            "schema": int(raw.get("schema") or SCHEMA_VERSION),
            "updated": str(raw.get("updated") or _now()),
            "tags": tags,
        }

    @staticmethod
    def _clean_entry(entry: dict) -> dict:
        """Checks a stored entry and fills in the missing fields."""
        kind = str(entry.get("kind") or KIND_GAME).strip().lower()
        try:
            hits = int(entry.get("hits") or 0)
        except (TypeError, ValueError):
            hits = 0
        common = {
            "created": str(entry.get("created") or _now()),
            "last_used": entry.get("last_used"),
            "hits": hits,
        }
        if kind == KIND_ACTION:
            action = str(entry.get("action") or "").strip().lower()
            if action not in ACTIONS:
                raise StorageError("carte speciale inconnue : %r" % (action,))
            result = {
                "kind": KIND_ACTION,
                "action": action,
                "params": clean_params(action, entry.get("params")),
                "system": "",
                "game": "",
                "path": "",
                "name": str(entry.get("name") or action).strip() or action,
                "limit_min": clean_limit(entry.get("limit_min")),
            }
            result.update(common)
            return result
        system = str(entry.get("system", "")).strip()
        game = str(entry.get("game", "")).strip()
        if not system or not game:
            raise StorageError("entree incomplete")
        result = {
            "kind": KIND_GAME,
            "system": system,
            "game": game,
            "name": str(entry.get("name") or os.path.basename(game)),
            "path": str(entry.get("path") or ""),
            "limit_min": clean_limit(entry.get("limit_min")),
        }
        result.update(common)
        return result

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def reload_if_changed(self) -> bool:
        """Reloads if the file was edited by hand. True if reloaded."""
        self.ensure_loaded()
        mtime = self._stat_mtime()
        if mtime and abs(mtime - self._mtime) > 1e-6:
            self.load()
            return True
        return False

    def get(self, uid: str):
        self.ensure_loaded()
        return self.tags.get(normalize_uid(uid))

    def items(self):
        self.ensure_loaded()
        return sorted(self.tags.items(), key=lambda item: (item[1]["name"].lower(), item[0]))

    def count(self) -> int:
        return len(self.tags)

    # ---------------------------------------------------------------- ecriture
    def save(self, backup: bool = True) -> None:
        self.ensure_loaded()
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        self._data["schema"] = SCHEMA_VERSION
        self._data["updated"] = _now()

        handle, tmp_path = tempfile.mkstemp(prefix=".tags-", suffix=".json", dir=directory)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(self._data, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if backup and os.path.isfile(self.path):
                try:
                    shutil.copy2(self.path, self.path + ".bak")
                except OSError:
                    pass
            os.replace(tmp_path, self.path)
        except OSError as exc:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise StorageError("Ecrasement de %s impossible : %s" % (self.path, exc))
        self._mtime = self._stat_mtime()

    def put(self, uid: str, system: str, game: str, name: str = "", path: str = "") -> dict:
        """Cree ou remplace l'association d'un badge."""
        self.ensure_loaded()
        normalized = normalize_uid(uid)
        system = str(system).strip()
        game = str(game).strip()
        if not system or not game:
            raise StorageError("Systeme ou jeu manquant")
        entry = self._clean_entry({
            "system": system,
            "game": game,
            "name": (str(name).strip() or os.path.basename(game)),
            "path": str(path or ""),
            "created": _now(),
            "last_used": None,
            "hits": 0,
        })
        self.tags[normalized] = entry
        self.save()
        return entry

    def put_entry(self, uid: str, entry: dict) -> dict:
        """Creates or replaces any entry (game or special card)."""
        self.ensure_loaded()
        normalized = normalize_uid(uid)
        cleaned = self._clean_entry(dict(entry, created=_now(), last_used=None, hits=0))
        self.tags[normalized] = cleaned
        self.save()
        return cleaned

    def update(self, uid: str, changes: dict) -> dict:
        """Changes the name, time limit or parameters of an existing entry."""
        self.ensure_loaded()
        normalized = normalize_uid(uid)
        current = self.tags.get(normalized)
        if current is None:
            raise StorageError("badge inconnu")
        merged = dict(current)
        for key in ("name", "limit_min", "params"):
            if key in changes:
                merged[key] = changes[key]
        if not str(merged.get("name") or "").strip():
            merged["name"] = current["name"]
        cleaned = self._clean_entry(merged)
        self.tags[normalized] = cleaned
        self.save()
        return cleaned

    def delete(self, uid: str) -> bool:
        self.ensure_loaded()
        normalized = normalize_uid(uid)
        if normalized in self.tags:
            del self.tags[normalized]
            self.save()
            return True
        return False

    def touch(self, uid: str) -> None:
        """Increments the use counter (without blocking on failure)."""
        entry = self.get(uid)
        if not entry:
            return
        entry["hits"] = int(entry.get("hits") or 0) + 1
        entry["last_used"] = _now()
        try:
            self.save(backup=False)
        except StorageError as exc:  # disk full: do not break the service
            if self.log:
                self.log.warning("Statistiques non enregistrees : %s" % exc)

    # -------------------------------------------------------------- import/export
    def export_csv(self, destination: str) -> int:
        """Exports the mappings as CSV (semicolon separated)."""
        self.ensure_loaded()
        directory = os.path.dirname(os.path.abspath(destination))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(destination, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(CSV_FIELDS)
            for uid, entry in self.items():
                limit = entry.get("limit_min")
                params = entry.get("params") or {}
                writer.writerow([
                    pretty_uid(uid), entry["system"], entry["game"], entry["name"],
                    entry.get("kind") or KIND_GAME, entry.get("action") or "",
                    json.dumps(params, ensure_ascii=False, sort_keys=True) if params else "",
                    "" if limit is None else str(limit),
                ])
        return self.count()

    def import_csv(self, source: str, overwrite: bool = True) -> dict:
        """Imports a CSV; returns {"ajoutes", "mis_a_jour", "ignores"}."""
        self.ensure_loaded()
        stats = {"ajoutes": 0, "mis_a_jour": 0, "ignores": 0}
        with open(source, "r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.readline()
            handle.seek(0)
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            for row in reader:
                row = {(key or "").strip().lower(): (value or "").strip() for key, value in row.items()}
                if not row.get("uid"):
                    stats["ignores"] += 1
                    continue
                try:
                    uid = normalize_uid(row["uid"])
                except StorageError:
                    stats["ignores"] += 1
                    continue
                exists = uid in self.tags
                if exists and not overwrite:
                    stats["ignores"] += 1
                    continue
                previous = self.tags.get(uid, {}) or {}
                try:
                    params = json.loads(row["params"]) if row.get("params") else {}
                except ValueError:
                    params = {}
                candidate = {
                    "kind": row.get("kind") or KIND_GAME,
                    "action": row.get("action", ""),
                    "params": params if isinstance(params, dict) else {},
                    "system": row.get("system", ""),
                    "game": row.get("game", ""),
                    "name": row.get("name") or os.path.basename(row.get("game", "")),
                    "path": row.get("path", ""),
                    "limit_min": row.get("limit_min") or None,
                    "created": previous.get("created") or _now(),
                    "last_used": previous.get("last_used"),
                    "hits": int(previous.get("hits") or 0),
                }
                try:
                    self.tags[uid] = self._clean_entry(candidate)
                except StorageError:
                    stats["ignores"] += 1
                    continue
                stats["mis_a_jour" if exists else "ajoutes"] += 1
        self.save()
        return stats
