"""Full backup of the reader data, in one ZIP file.

What is saved: the badges, the settings, the card templates and frames, the
play time counters, the players and their avatars, and the reader calibration. Never saved: the
page password, the session secret, the pairing state and the logs (they
belong to this Recalbox, or are secrets).

A restore checks the whole archive first (known names only, sizes, readable
JSON and INI), keeps a copy of the current files in ``backups/`` (the last
five), then writes the files. The service is restarted by the caller.
"""

from __future__ import annotations

import configparser
import io
import json
import os
import re
import shutil
import time
import zipfile

from . import __version__

MANIFEST = "rfid-backup.json"
FORMAT = 1

#: Files saved from the home folder, and how they are checked.
FILES = {
    "tags.json": "json",
    "config.ini": "ini",
    "card-templates.json": "json",
    "playtime.json": "json",
    "players.json": "json",
    "calibration.json": "json",
}
#: Folders saved with their files (only these extensions).
FOLDERS = {
    "frames": (".png", ".svg", ".json", ".webp", ".jpg", ".jpeg"),
    "avatars": (".jpg",),
}
#: Readable copy of the statistics (players.json holds the data): written in
#: the archive, never restored.
STATS_CSV = "statistics.csv"
BACKUPS_DIR = "backups"
KEEP_BACKUPS = 5
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 60 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,120}$")


class BackupError(Exception):
    pass


def _folder_files(home: str, folder: str):
    path = os.path.join(home, folder)
    if not os.path.isdir(path):
        return []
    names = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if os.path.isfile(full) and _SAFE_NAME.match(name) and name.lower().endswith(FOLDERS[folder]):
            names.append(name)
    return names


def create(home: str, now=None) -> bytes:
    """ZIP archive of the saved data (bytes)."""
    stamp = (now or time.time)()
    buffer = io.BytesIO()
    contents = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            path = os.path.join(home, name)
            if os.path.isfile(path):
                archive.write(path, name)
                contents.append(name)
        for folder in FOLDERS:
            for name in _folder_files(home, folder):
                archive.write(os.path.join(home, folder, name), folder + "/" + name)
                contents.append(folder + "/" + name)
        stats = statistics_csv(home)
        if stats:
            archive.writestr(STATS_CSV, stats)
        archive.writestr(MANIFEST, json.dumps({
            "format": FORMAT,
            "app_version": __version__,
            "created": int(stamp),
            "files": contents,
        }, indent=2))
    return buffer.getvalue()


def statistics_csv(home: str) -> str:
    """Time played per day, player and game, as in the page export ("" if none)."""
    from .players import stats_rows
    from .storage import TagStore

    rows = stats_rows(home)
    if not rows:
        return ""
    names = {"guest": "guest"}
    try:
        store = TagStore(os.path.join(home, "tags.json"))
        store.load()
        for uid, entry in store.items():
            names[uid] = entry.get("name") or uid
    except Exception:  # noqa: BLE001 - names are a convenience only
        pass

    def quote(value) -> str:
        text = str(value)
        return '"%s"' % text.replace('"', '""') if any(c in text for c in ';"\r\n') else text

    lines = ["date;player;console;game;minutes;seconds"]
    for row in rows:
        lines.append(";".join(quote(value) for value in (
            row["date"], names.get(row["uid"], row["uid"]), row["system"], row["game"],
            ("%.1f" % (row["seconds"] / 60.0)).replace(".", ","), row["seconds"])))
    return "\ufeff" + "\r\n".join(lines) + "\r\n"


def _check_entry(name: str, data: bytes) -> None:
    kind = FILES.get(name)
    text = None
    if kind in ("json", "ini") or name.endswith((".json", ".svg")):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise BackupError("%s : texte illisible" % name)
    if kind == "json" or name.endswith(".json"):
        try:
            json.loads(text)
        except ValueError:
            raise BackupError("%s : JSON invalide" % name)
    elif kind == "ini":
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(text)
        except configparser.Error:
            raise BackupError("%s : fichier de reglages invalide" % name)


def read(data: bytes) -> dict:
    """Checks an archive; returns {name: bytes} of the files to restore."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BackupError("ce fichier n'est pas une sauvegarde (ZIP illisible)")
    with archive:
        names = archive.namelist()
        if MANIFEST not in names:
            raise BackupError("ce fichier n'est pas une sauvegarde du lecteur")
        try:
            manifest = json.loads(archive.read(MANIFEST).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BackupError("sauvegarde abimee (manifeste illisible)")
        if not isinstance(manifest, dict) or int(manifest.get("format") or 0) > FORMAT:
            raise BackupError("sauvegarde d'une version plus recente : mettez le lecteur a jour")
        files = {}
        total = 0
        for info in archive.infolist():
            name = info.filename
            if name in (MANIFEST, STATS_CSV) or name.endswith("/"):
                continue
            if name in FILES:
                pass
            else:
                folder, _, base = name.partition("/")
                if folder not in FOLDERS or not _SAFE_NAME.match(base) or not base.lower().endswith(FOLDERS[folder]):
                    raise BackupError("fichier inattendu dans la sauvegarde : %s" % name)
            if info.file_size > MAX_FILE_BYTES:
                raise BackupError("%s : fichier trop volumineux" % name)
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise BackupError("sauvegarde trop volumineuse")
            payload = archive.read(info)
            _check_entry(name, payload)
            files[name] = payload
        if not files:
            raise BackupError("la sauvegarde est vide")
        return files


def _keep_copy(home: str, now: float) -> str:
    """Copy of the current files before a restore; the oldest copies go."""
    root = os.path.join(home, BACKUPS_DIR)
    target = os.path.join(root, time.strftime("before-restore-%Y%m%d-%H%M%S", time.localtime(now)))
    os.makedirs(target, exist_ok=True)
    for name in FILES:
        path = os.path.join(home, name)
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(target, name))
    for folder in FOLDERS:
        if os.path.isdir(os.path.join(home, folder)):
            shutil.copytree(os.path.join(home, folder), os.path.join(target, folder), dirs_exist_ok=True)
    copies = sorted(name for name in os.listdir(root) if name.startswith("before-restore-"))
    for old in copies[:-KEEP_BACKUPS]:
        shutil.rmtree(os.path.join(root, old), ignore_errors=True)
    return target


def restore(home: str, data: bytes, now=None) -> dict:
    """Restores an archive in ``home``. Returns what was written."""
    files = read(data)
    stamp = (now or time.time)()
    copy = _keep_copy(home, stamp)
    # A folder in the archive replaces the current one (frames deleted since
    # the backup must not stay); a folder absent from the archive is kept.
    for folder in FOLDERS:
        if any(name.startswith(folder + "/") for name in files):
            shutil.rmtree(os.path.join(home, folder), ignore_errors=True)
    for name, payload in files.items():
        path = os.path.join(home, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + ".restore"
        with open(temporary, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    return {"files": sorted(files), "copy": os.path.relpath(copy, home).replace("\\", "/")}
