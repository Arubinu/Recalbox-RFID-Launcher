"""The games refused (card or Recalbox menu): who tried what, and why.

Kept in ``refusals.json`` (the last ``KEEP`` ones), shown in the Statistics
tab of the page.
"""

from __future__ import annotations

import json
import os
import threading
import time

FILENAME = "refusals.json"
KEEP = 200

_lock = threading.Lock()


def path(home: str) -> str:
    return os.path.join(home, FILENAME)


def read(home: str) -> list:
    """[{"at", "reason", "player", "game", "system", "card", "via"}], newest first."""
    try:
        with open(path(home), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = data.get("refusals") if isinstance(data, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def record(home: str, reason: str, player: str = "", game: str = "", system: str = "", card: str = "",
           via: str = "card", wall=None) -> None:
    if not home:
        return
    row = {"at": int((wall or time.time)()), "reason": str(reason), "player": str(player or ""),
           "game": str(game or ""), "system": str(system or ""), "card": str(card or ""), "via": via}
    with _lock:
        rows = [row] + read(home)
        target = path(home)
        temporary = target + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"refusals": rows[:KEEP]}, handle)
            os.replace(temporary, target)
        except OSError:
            pass


def clear(home: str) -> None:
    try:
        os.remove(path(home))
    except OSError:
        pass
