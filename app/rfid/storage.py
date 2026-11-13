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
import json
import os
import shutil
import tempfile
import time

SCHEMA_VERSION = 1

CSV_FIELDS = ("uid", "system", "game", "name")


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
            system = str(entry.get("system", "")).strip()
            game = str(entry.get("game", "")).strip()
            if not system or not game:
                if self.log:
                    self.log.warning("Badge %s ignore (entree incomplete)" % pretty_uid(normalized))
                continue
            tags[normalized] = {
                "system": system,
                "game": game,
                "name": str(entry.get("name") or os.path.basename(game)),
                "path": str(entry.get("path") or ""),
                "created": str(entry.get("created") or _now()),
                "last_used": entry.get("last_used"),
                "hits": int(entry.get("hits") or 0),
            }

        self._data = {
            "schema": int(raw.get("schema") or SCHEMA_VERSION),
            "updated": str(raw.get("updated") or _now()),
            "tags": tags,
        }

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
        entry = {
            "system": system,
            "game": game,
            "name": (str(name).strip() or os.path.basename(game)),
            "path": str(path or ""),
            "created": _now(),
            "last_used": None,
            "hits": 0,
        }
        self.tags[normalized] = entry
        self.save()
        return entry

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
                writer.writerow([pretty_uid(uid), entry["system"], entry["game"], entry["name"]])
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
                if not row.get("uid") or not row.get("system") or not row.get("game"):
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
                self.tags[uid] = {
                    "system": row["system"],
                    "game": row["game"],
                    "name": row.get("name") or os.path.basename(row["game"]),
                    "path": row.get("path", ""),
                    "created": (self.tags.get(uid, {}) or {}).get("created") or _now(),
                    "last_used": (self.tags.get(uid, {}) or {}).get("last_used"),
                    "hits": int((self.tags.get(uid, {}) or {}).get("hits") or 0),
                }
                stats["mis_a_jour" if exists else "ajoutes"] += 1
        self.save()
        return stats
