"""Trophies of the players: consoles and games discovered, days in a row, hours.

Worked out from the time played (players.json, the last 60 days) and kept in
``trophies.json`` once earned: {uid: {"<kind>:<level>": "YYYY-MM-DD"}}.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import time

FILENAME = "trophies.json"

#: Levels of each kind of trophy.
LEVELS = {
    "consoles": (3, 10, 20),
    "games": (10, 25, 50),
    "streak": (3, 7, 14),
    "hours": (5, 20, 50),
}
#: A day counts for a streak from this many seconds of play.
STREAK_MIN_S = 60

_lock = threading.Lock()


def path(home: str) -> str:
    return os.path.join(home, FILENAME)


def read(home: str) -> dict:
    try:
        with open(path(home), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(uid): {str(key): str(day) for key, day in earned.items()}
            for uid, earned in data.items() if isinstance(earned, dict)}


def measures(days: dict) -> dict:
    """{"consoles", "games", "streak", "hours"} of one player's {day: {"system|name": seconds}}."""
    systems, games, total = set(), set(), 0.0
    played_days = []
    for day, played in (days or {}).items():
        seconds = sum(played.values())
        total += seconds
        if seconds >= STREAK_MIN_S:
            played_days.append(day)
        for key, value in played.items():
            if value >= STREAK_MIN_S:
                games.add(key)
                systems.add(key.split("|", 1)[0])
    best = run = 0
    previous = None
    for day in sorted(played_days):
        try:
            current = datetime.date.fromisoformat(day)
        except ValueError:
            continue
        run = run + 1 if previous is not None and (current - previous).days == 1 else 1
        best = max(best, run)
        previous = current
    return {"consoles": len(systems), "games": len(games), "streak": best, "hours": int(total // 3600)}


def earned(values: dict) -> list:
    """["kind:level"] reached by these measures."""
    return ["%s:%d" % (kind, level) for kind, levels in LEVELS.items() for level in levels
            if values.get(kind, 0) >= level]


def update(home: str, games: dict, wall=None) -> list:
    """Adds the new trophies of every player: [(uid, kind, level)].

    The first time (no trophies.json yet), the trophies already earned are
    saved without being announced: returns [].
    """
    if not home:
        return []
    with _lock:
        first = not os.path.exists(path(home))
        table = read(home)
        today = time.strftime("%Y-%m-%d", time.localtime((wall or time.time)()))
        new = []
        for uid, days in (games or {}).items():
            if uid == "guest":
                continue
            mine = table.setdefault(uid, {})
            for key in earned(measures(days)):
                if key not in mine:
                    mine[key] = today
                    kind, level = key.split(":")
                    new.append((uid, kind, int(level)))
        if new or first:
            temporary = path(home) + ".tmp"
            try:
                with open(temporary, "w", encoding="utf-8") as handle:
                    json.dump({uid: keys for uid, keys in table.items() if keys}, handle)
                os.replace(temporary, path(home))
            except OSError:
                return []
        return [] if first else new


def latest(keys: dict):
    """(kind, level) of the last trophy earned (the highest that day), or None."""
    if not keys:
        return None
    key = max(keys, key=lambda item: (keys[item], int(item.split(":")[1]) if ":" in item else 0))
    kind, _sep, level = key.partition(":")
    return kind, int(level or 0)
