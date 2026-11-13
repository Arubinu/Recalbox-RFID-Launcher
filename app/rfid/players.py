"""Player cards: who plays, and for how long per day or week.

A player card is a special card (action "player") with a time quota per
calendar day or week (0 = no limit). Games played without a player card are
counted for the "guest", with its own optional quota (settings).

One card per game:

* placed before a game card, the player card counts for the next game started
  within ``ARM_WINDOW_S``; the game ends -> the next one needs the card again;
* left on the reader while a game is started from the Recalbox menu, the game
  is the player's; removing the card then ends the game (the service does it).

The time played is saved in ``players.json`` per day: ``{"usage": {uid:
{"YYYY-MM-DD": seconds}}}``, kept 60 days. Without a battery the Recalbox
clock is only right once the network gave the time (same limit as the bonus
quotas).
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import time

PLAYERS_FILENAME = "players.json"
GUEST = "guest"
ARM_WINDOW_S = 90.0
KEEP_DAYS = 60
#: Played time is written to the disk at least this often during a game.
SAVE_EVERY_S = 30.0
#: A bonus card may start the last game again within this delay.
RESUME_WINDOW_S = 15 * 60


def _day_key(stamp: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(stamp))


def period_days(period: str, now: float) -> list:
    """Day keys of the current period ("day": today, "week": since Monday)."""
    today = datetime.date.fromtimestamp(now)
    count = today.weekday() + 1 if period == "week" else 1
    return [(today - datetime.timedelta(days=offset)).isoformat() for offset in range(count)]


class Players:
    def __init__(self, home: str = None, wall=None, clock=None, log=None):
        self.home = home
        self.wall = wall or time.time
        self.clock = clock or time.monotonic
        self.log = log
        self._lock = threading.Lock()
        self.usage = self._load()
        #: Player card placed, waiting for its game: {"uid", "entry", "until"}.
        self.pending = None
        #: Game being counted: {"uid", "entry", "via", "since", "saved_at"}.
        self.current = None
        #: Last game counted (a bonus card restarts it for the same player).
        self.last = None

    # ------------------------------------------------------------ persistence
    def _path(self) -> str:
        return os.path.join(self.home, PLAYERS_FILENAME) if self.home else ""

    def _load(self) -> dict:
        path = self._path()
        if not path:
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return {}
        clean = {}
        for uid, days in usage.items():
            if isinstance(days, dict):
                clean[str(uid)] = {str(day): float(seconds) for day, seconds in days.items()
                                   if isinstance(seconds, (int, float)) and seconds >= 0}
        return clean

    def _save(self) -> None:
        path = self._path()
        if not path:
            return
        limit = _day_key(self.wall() - KEEP_DAYS * 86400)
        for uid in list(self.usage):
            self.usage[uid] = {day: seconds for day, seconds in self.usage[uid].items() if day >= limit}
            if not self.usage[uid]:
                del self.usage[uid]
        temporary = path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"usage": self.usage}, handle)
            os.replace(temporary, path)
        except OSError as exc:
            if self.log:
                self.log.warning("Temps des joueurs non enregistre : %s" % exc)

    # -------------------------------------------------------------- counting
    def used_s(self, uid: str, period: str = "day") -> float:
        """Seconds played in the current period, the running game included."""
        uid = uid or GUEST
        days = self.usage.get(uid, {})
        total = sum(days.get(day, 0.0) for day in period_days(period, self.wall()))
        current = self.current
        if current is not None and current["uid"] == uid:
            total += max(0.0, self.clock() - current["saved_at"])
        return total

    def remaining_s(self, uid: str, quota_min: int, period: str = "day"):
        """Seconds left (None = no limit)."""
        if not quota_min or quota_min <= 0:
            return None
        return max(0.0, quota_min * 60.0 - self.used_s(uid, period))

    def checkpoint(self) -> None:
        """Adds the time played since the last checkpoint to today's count."""
        with self._lock:
            current = self.current
            if current is None:
                return
            now = self.clock()
            elapsed = max(0.0, now - current["saved_at"])
            current["saved_at"] = now
            if elapsed <= 0:
                return
            days = self.usage.setdefault(current["uid"], {})
            key = _day_key(self.wall())
            days[key] = days.get(key, 0.0) + elapsed
            self._save()

    def tick(self) -> None:
        """To call often: saves the running game every ``SAVE_EVERY_S``."""
        current = self.current
        if current is not None and self.clock() - current["saved_at"] >= SAVE_EVERY_S:
            self.checkpoint()

    # -------------------------------------------------------------- sessions
    def arm(self, uid: str, entry: dict) -> None:
        """A player card was placed: it counts for the next game."""
        self.pending = {"uid": uid, "entry": dict(entry), "until": self.clock() + ARM_WINDOW_S}

    def take_pending(self):
        """The waiting player card, if still valid (it is used only once)."""
        pending = self.pending
        self.pending = None
        if pending is None or self.clock() > pending["until"]:
            return None
        return pending

    def begin(self, uid: str, entry: dict, via: str = "card") -> None:
        """A game starts for this player ("" = guest). via: "card" or "reader"."""
        self.finish()
        now = self.clock()
        self.current = {"uid": uid or GUEST, "entry": dict(entry or {}), "via": via,
                        "since": now, "saved_at": now}
        if self.log:
            self.log.info("Partie de %s" % (self.player_name(entry) if uid else "l'invite"))

    def finish(self) -> None:
        """The game is over: its time is saved, the next game needs a card."""
        if self.current is None:
            return
        self.checkpoint()
        self.last = {"uid": self.current["uid"], "entry": self.current["entry"], "ended": self.clock()}
        self.current = None

    def resume_player(self):
        """(uid, entry) of the game that just ended (a bonus card starts it
        again for the same player), or the guest."""
        last = self.last
        if last is None or self.clock() - last["ended"] > RESUME_WINDOW_S or last["uid"] == GUEST:
            return ("", {})
        return (last["uid"], last["entry"])

    @staticmethod
    def player_name(entry) -> str:
        return str((entry or {}).get("name") or "").strip() or "joueur"

    def status(self, players: list) -> dict:
        """Time played and left for each player card (for the page)."""
        result = []
        for uid, entry in players:
            params = entry.get("params") or {}
            period = params.get("period") or "day"
            quota = int(params.get("quota_min") or 0)
            result.append({
                "uid": uid,
                "name": self.player_name(entry),
                "period": period,
                "quota_min": quota,
                "used_s": int(self.used_s(uid, period)),
                "remaining_s": None if not quota else int(self.remaining_s(uid, quota, period)),
                "playing": self.current is not None and self.current["uid"] == uid,
            })
        current = self.current
        return {
            "players": result,
            "current": None if current is None else {"uid": current["uid"], "name": self.player_name(current["entry"]) if current["uid"] != GUEST else "", "via": current["via"]},
            "pending": None if self.pending is None or self.clock() > self.pending["until"] else self.player_name(self.pending["entry"]),
        }

    def reset(self, uid: str) -> None:
        """Forgets the time played today and this week (parent's gift)."""
        uid = uid or GUEST
        days = set(period_days("week", self.wall()))
        with self._lock:
            if uid in self.usage:
                self.usage[uid] = {day: seconds for day, seconds in self.usage[uid].items() if day not in days}
            if self.current is not None and self.current["uid"] == uid:
                self.current["saved_at"] = self.clock()
            self._save()
