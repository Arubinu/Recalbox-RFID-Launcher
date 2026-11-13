"""Locks the Recalbox menu: only the favourite games are shown, no START menu.

Optional ("Settings > Player cards"). Two settings of ``recalbox.conf``:

* ``emulationstation.favoritesonly=1``: the game lists show the favourites
  only (the parent marks the allowed games as favourites);
* ``emulationstation.menu=none``: no START menu, so the lock cannot be
  removed from the TV.

The previous values are kept in ``frontend-lock.json`` and put back when the
option is turned off (and by the uninstaller). The frontend only reads these
settings when it starts: it is stopped, the file is changed, then it is
started again -- never while a game runs (stopping the frontend would close
the game).
"""

from __future__ import annotations

import json
import os
import subprocess

RECALBOX_CONF = "/recalbox/share/system/recalbox.conf"
ES_SERVICE = "/etc/init.d/S31emulationstation"
LOCK_FILENAME = "frontend-lock.json"
LOCKED = {"emulationstation.menu": "none", "emulationstation.favoritesonly": "1"}
#: Values put back when no copy was kept (Recalbox defaults).
DEFAULTS = {"emulationstation.menu": "default", "emulationstation.favoritesonly": "0"}


class LockError(Exception):
    pass


def read_values(text: str, keys) -> dict:
    """Active values of ``keys`` (None when absent or commented out)."""
    values = {key: None for key in keys}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#")) or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() in values:
            values[key.strip()] = value.strip()
    return values


def write_values(text: str, values: dict) -> str:
    """Sets ``key=value`` lines; None removes the active line of a key.

    An active line is changed in place, a missing one is added at the end:
    unlocking with the values kept before gives back the very same file.
    """
    lines = []
    done = set()
    for line in text.splitlines():
        raw = line.strip()
        stripped = raw.lstrip(";#").strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        # Only active lines change: a commented example stays untouched, so
        # that unlocking gives back the very same file.
        if key in values and key not in done and not raw.startswith((";", "#")):
            if values[key] is None:
                continue
            lines.append("%s=%s" % (key, values[key]))
            done.add(key)
            continue
        lines.append(line)
    for key, value in values.items():
        if key not in done and value is not None:
            lines.append("%s=%s" % (key, value))
    # The end of the file stays as it was (with or without a last newline).
    return "\n".join(lines) + ("\n" if text.endswith("\n") or not text else "")


def _lock_path(home: str) -> str:
    return os.path.join(home, LOCK_FILENAME)


def is_locked(conf: str = RECALBOX_CONF) -> bool:
    try:
        with open(conf, "r", encoding="utf-8") as handle:
            current = read_values(handle.read(), LOCKED)
    except OSError:
        return False
    return all(current[key] == value for key, value in LOCKED.items())


def apply(home: str, enabled: bool, conf: str = RECALBOX_CONF, run=None, game_running=None,
          restart: bool = True) -> dict:
    """Locks or unlocks the menu. Returns {"changed": bool}.

    restart=False only edits the file: used by the uninstaller, which may
    itself run from the menu. Recalbox notices the change of recalbox.conf and
    offers to restart its menu.
    """
    run = run or (lambda args: subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60))
    try:
        with open(conf, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise LockError("recalbox.conf illisible : %s" % exc)
    current = read_values(text, LOCKED)
    if enabled:
        target = dict(LOCKED)
    else:
        saved = None
        try:
            with open(_lock_path(home), "r", encoding="utf-8") as handle:
                saved = json.load(handle)
        except (OSError, ValueError):
            saved = None
        if not isinstance(saved, dict):
            # Nothing kept: nothing to undo unless the menu is locked.
            if not all(current[key] == value for key, value in LOCKED.items()):
                return {"changed": False}
            saved = {}
        # The values kept before the lock (None: the setting was absent and
        # is removed again); without a copy, the Recalbox defaults.
        target = {key: saved[key] for key in LOCKED} if all(key in saved for key in LOCKED) else dict(DEFAULTS)
    if all(current[key] == value for key, value in target.items()):
        if not enabled:
            _forget(home)
        return {"changed": False}
    if restart and game_running is not None and game_running():
        raise LockError("quittez d'abord le jeu en cours : la Recalbox doit redemarrer son menu")
    if enabled and not os.path.exists(_lock_path(home)):
        with open(_lock_path(home), "w", encoding="utf-8") as handle:
            json.dump(current, handle)
    if restart:
        run([ES_SERVICE, "stop"])
    try:
        temporary = conf + ".rfid-tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(write_values(text, target))
        os.replace(temporary, conf)
    finally:
        if restart:
            run([ES_SERVICE, "start"])
    if not enabled:
        _forget(home)
    return {"changed": True}


def _forget(home: str) -> None:
    try:
        os.remove(_lock_path(home))
    except OSError:
        pass
