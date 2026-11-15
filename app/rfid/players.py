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
{"YYYY-MM-DD": seconds}}}``, kept 60 days. The same time per game feeds the
statistics: ``{"games": {uid: {"YYYY-MM-DD": {"system|game": seconds}}}}``
(never cleared by a reset: it is what was really played). Without a battery the Recalbox
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


#: Days a week can start on (option ``[players] week_start``).
WEEK_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _day_key(stamp: float, reset_hour: int = 0) -> str:
    """The play day of a moment: it starts at ``reset_hour`` (0 = midnight)."""
    return time.strftime("%Y-%m-%d", time.localtime(stamp - reset_hour * 3600))


def period_days(period: str, now: float, reset_hour: int = 0, week_start: int = 0) -> list:
    """Day keys of the current period ("day": today, "week": since the first
    day of the week, ``week_start`` 0 = Monday), days starting at ``reset_hour``."""
    today = datetime.date.fromtimestamp(now - reset_hour * 3600)
    count = (today.weekday() - week_start) % 7 + 1 if period == "week" else 1
    return [(today - datetime.timedelta(days=offset)).isoformat() for offset in range(count)]


def _minutes(clock: str) -> int:
    hours, minutes = clock.split(":")
    return int(hours) * 60 + int(minutes)


def schedule_left(params: dict, now: float):
    """Time slots of a player card: None (no slot), 0 (not now) or the
    seconds left in the current slot."""
    params = params or {}
    days = params.get("days")
    start, end = params.get("from"), params.get("to")
    if not days and not start:
        return None
    moment = time.localtime(now)
    if days and moment.tm_wday not in days:
        return 0.0
    current = moment.tm_hour * 60 + moment.tm_min + moment.tm_sec / 60.0
    first, last = (_minutes(start), _minutes(end)) if start else (0, 24 * 60)
    if not first <= current < last:
        return 0.0
    return (last - current) * 60.0


def game_allowed(params: dict, system: str, path: str = "") -> bool:
    """The game is among the player's allowed games (all when none is set)."""
    params = params or {}
    systems, games = params.get("systems") or [], params.get("games") or []
    if not systems and not games:
        return True
    if system in systems:
        return True
    return bool(path) and any(game.get("path") == path for game in games)


def game_key(game) -> str:
    """"system|name" of a game ("" when unknown)."""
    if not isinstance(game, dict):
        return ""
    system = str(game.get("system") or "").replace("|", " ").strip()
    name = str(game.get("name") or "").replace("|", " ").strip()
    return "%s|%s" % (system, name) if system and name else ""


def read_file(path: str):
    """(usage, games) of a players.json file (empty when unreadable)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}, {}
    if not isinstance(data, dict):
        return {}, {}
    usage = {}
    for uid, days in (data.get("usage") or {}).items() if isinstance(data.get("usage"), dict) else ():
        if isinstance(days, dict):
            usage[str(uid)] = {str(day): float(seconds) for day, seconds in days.items()
                               if isinstance(seconds, (int, float)) and seconds >= 0}
    games = {}
    for uid, days in (data.get("games") or {}).items() if isinstance(data.get("games"), dict) else ():
        if not isinstance(days, dict):
            continue
        clean = {}
        for day, played in days.items():
            if isinstance(played, dict):
                clean[str(day)] = {str(key): float(seconds) for key, seconds in played.items()
                                   if isinstance(seconds, (int, float)) and seconds >= 0 and "|" in str(key)}
        games[str(uid)] = clean
    return usage, games


def stats_rows(home: str) -> list:
    """Time played per day, player and game: the statistics of the page.

    [{"date", "uid", "system", "game", "seconds"}], newest first.
    """
    _usage, games = read_file(os.path.join(home, PLAYERS_FILENAME))
    rows = []
    for uid, days in games.items():
        for day, played in days.items():
            for key, seconds in played.items():
                system, name = key.split("|", 1)
                if seconds >= 1:
                    rows.append({"date": day, "uid": uid, "system": system, "game": name,
                                 "seconds": int(round(seconds))})
    rows.sort(key=lambda row: (row["date"], row["uid"], row["system"], row["game"]), reverse=True)
    return rows


class Players:
    def __init__(self, home: str = None, wall=None, clock=None, log=None):
        self.home = home
        self.wall = wall or time.time
        self.clock = clock or time.monotonic
        self.log = log
        self._lock = threading.Lock()
        self.usage, self.games = self._load()
        #: Play time given by reward cards: {uid: {"d:<day>" or "w:<first day>": minutes}}.
        self.extra = self._load_extra()
        #: Last game of each player, for the "continue" card:
        #: {uid: {"system", "name", "path", "at"}} ("guest" without a card).
        self.last_games = self._load_last_games()
        #: Player card placed, waiting for its game: {"uid", "entry", "until"}.
        self.pending = None
        #: Game being counted: {"uid", "entry", "via", "since", "saved_at"}.
        self.current = None
        #: Last game counted (a bonus card restarts it for the same player).
        self.last = None
        #: Option "keep the player active": the player of the last game stays
        #: active for the next ones ({"uid", "entry"}), until their time is up,
        #: another player card or the unlock card.
        self.keep = False
        self.kept = None
        #: Time counters restart at this hour, and the week on this day (0 = Monday).
        self.reset_hour = 0
        self.week_start = 0

    # ------------------------------------------------------------ persistence
    def _path(self) -> str:
        return os.path.join(self.home, PLAYERS_FILENAME) if self.home else ""

    def _load(self):
        path = self._path()
        if not path:
            return {}, {}
        return read_file(path)

    def _load_extra(self) -> dict:
        path = self._path()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle).get("extra") or {}
        except (OSError, ValueError, AttributeError, TypeError):
            return {}
        extra = {}
        for uid, keys in data.items() if isinstance(data, dict) else ():
            if isinstance(keys, dict):
                extra[str(uid)] = {str(key): float(value) for key, value in keys.items()
                                   if isinstance(value, (int, float)) and value > 0}
        return extra

    def _load_last_games(self) -> dict:
        path = self._path()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle).get("last_games") or {}
        except (OSError, ValueError, AttributeError, TypeError):
            return {}
        return {str(uid): dict(game) for uid, game in data.items()
                if isinstance(game, dict) and game.get("path") and game.get("system")} if isinstance(data, dict) else {}

    def remember(self, uid: str, system: str, name: str, path: str) -> None:
        """The game a player just started (the "continue" card starts it again)."""
        if not system or not path:
            return
        with self._lock:
            self.last_games[uid or GUEST] = {"system": system, "name": name or "", "path": path, "at": int(self.wall())}
            self._save()

    def last_game(self, uid=None):
        """The last game of this player, or of anyone (uid None)."""
        if uid is not None:
            return self.last_games.get(uid or GUEST)
        games = sorted(self.last_games.values(), key=lambda game: game.get("at", 0), reverse=True)
        return games[0] if games else None

    def _period_key(self, period: str) -> str:
        days = period_days(period, self.wall(), self.reset_hour, self.week_start)
        return ("w:" + days[-1]) if period == "week" else ("d:" + days[0])

    def add_extra(self, uid: str, minutes: float, period: str = "day") -> None:
        """A reward card: more play time for this player in the current period."""
        with self._lock:
            table = self.extra.setdefault(uid or GUEST, {})
            key = self._period_key(period)
            table[key] = table.get(key, 0.0) + float(minutes)
            self._save()

    def extra_s(self, uid: str, period: str = "day") -> float:
        return self.extra.get(uid or GUEST, {}).get(self._period_key(period), 0.0) * 60.0

    def _save(self) -> None:
        path = self._path()
        if not path:
            return
        limit = _day_key(self.wall() - KEEP_DAYS * 86400)
        for table in (self.usage, self.games):
            for uid in list(table):
                table[uid] = {day: value for day, value in table[uid].items() if day >= limit}
                if not table[uid]:
                    del table[uid]
        temporary = path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                limit_extra = _day_key(self.wall() - 14 * 86400)
                extra = {uid: {key: value for key, value in keys.items() if key[2:] >= limit_extra}
                         for uid, keys in self.extra.items()}
                json.dump({"usage": self.usage, "games": self.games,
                           "extra": {uid: keys for uid, keys in extra.items() if keys},
                           "last_games": self.last_games}, handle)
            os.replace(temporary, path)
        except OSError as exc:
            if self.log:
                self.log.warning("Temps des joueurs non enregistre : %s" % exc)

    # -------------------------------------------------------------- counting
    def used_s(self, uid: str, period: str = "day") -> float:
        """Seconds played in the current period, the running game included."""
        uid = uid or GUEST
        days = self.usage.get(uid, {})
        total = sum(days.get(day, 0.0) for day in period_days(period, self.wall(), self.reset_hour, self.week_start))
        current = self.current
        if current is not None and current["uid"] == uid and not current.get("paused"):
            total += max(0.0, self.clock() - current["saved_at"])
        return total

    def pause(self) -> None:
        """The game is paused: its time is no longer counted."""
        self.checkpoint()
        if self.current is not None:
            self.current["paused"] = True

    def resume(self) -> None:
        if self.current is not None and self.current.get("paused"):
            self.current["saved_at"] = self.clock()
            self.current["paused"] = False

    def remaining_s(self, uid: str, quota_min: int, period: str = "day"):
        """Seconds left (None = no limit)."""
        if not quota_min or quota_min <= 0:
            return None
        return max(0.0, quota_min * 60.0 + self.extra_s(uid, period) - self.used_s(uid, period))

    def checkpoint(self) -> None:
        """Adds the time played since the last checkpoint to today's count."""
        with self._lock:
            current = self.current
            if current is None:
                return
            now = self.clock()
            elapsed = max(0.0, now - current["saved_at"])
            current["saved_at"] = now
            if elapsed <= 0 or current.get("paused"):
                return
            days = self.usage.setdefault(current["uid"], {})
            key = _day_key(self.wall(), self.reset_hour)
            days[key] = days.get(key, 0.0) + elapsed
            game = game_key(current.get("game"))
            if game:
                played = self.games.setdefault(current["uid"], {}).setdefault(key, {})
                played[game] = played.get(game, 0.0) + elapsed
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
        if self.keep:
            self.kept = {"uid": uid, "entry": dict(entry)}  # replaces the previous player

    def take_pending(self):
        """The waiting player card, if still valid (it is used only once),
        or the player kept active (option)."""
        pending = self.pending
        self.pending = None
        if pending is None or self.clock() > pending["until"]:
            if self.keep and self.kept is not None:
                return {"uid": self.kept["uid"], "entry": self.kept["entry"], "until": self.clock(), "kept": True}
            return None
        if self.keep:
            self.kept = {"uid": pending["uid"], "entry": pending["entry"]}
        return pending

    def release(self, reason: str = "") -> bool:
        """The kept player is no longer active. True if there was one."""
        kept, self.kept = self.kept, None
        if kept is not None and self.log:
            self.log.info("%s n'est plus le joueur actif%s" % (self.player_name(kept["entry"]),
                                                               (" (%s)" % reason) if reason else ""))
        return kept is not None

    def begin(self, uid: str, entry: dict, via: str = "card", game=None) -> None:
        """A game starts for this player ("" = guest). via: "card", "reader" or "menu".

        game: {"system", "name"} of the game played (for the statistics).
        """
        self.finish()
        now = self.clock()
        self.current = {"uid": uid or GUEST, "entry": dict(entry or {}), "via": via,
                        "since": now, "saved_at": now, "game": dict(game) if game else None}
        if self.log:
            self.log.info("Partie de %s" % (self.player_name(entry) if uid else "l'invite"))

    def finish(self) -> None:
        """The game is over: its time is saved, the next game needs a card."""
        if self.current is None:
            return
        self.checkpoint()
        self.last = {"uid": self.current["uid"], "entry": self.current["entry"], "ended": self.clock()}
        if self.keep and self.current["uid"] != GUEST:
            self.kept = {"uid": self.current["uid"], "entry": self.current["entry"]}
        self.current = None

    def give_back(self):
        """The game never started (shown, then given up): its player is the
        one of the next game again. Returns the entry of that player, or None."""
        current = self.current
        if current is None:
            return None
        self.checkpoint()
        self.current = None
        if current["uid"] == GUEST:
            return None
        self.pending = {"uid": current["uid"], "entry": current["entry"], "until": self.clock() + ARM_WINDOW_S}
        return current["entry"]

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
        waiting = self.pending if self.pending is not None and self.clock() <= self.pending["until"] else None
        if waiting is None and self.keep and self.kept is not None:
            waiting = self.kept
        return {
            "players": result,
            "current": None if current is None else {"uid": current["uid"], "name": self.player_name(current["entry"]) if current["uid"] != GUEST else "", "via": current["via"]},
            "pending": None if waiting is None else self.player_name(waiting["entry"]),
            "pending_uid": None if waiting is None else waiting["uid"],
            "kept": bool(self.keep and self.kept is not None),
        }

    def reset(self, uid: str) -> None:
        """Forgets the time played today and this week (parent's gift)."""
        uid = uid or GUEST
        days = set(period_days("week", self.wall(), self.reset_hour, self.week_start))
        with self._lock:
            if uid in self.usage:
                self.usage[uid] = {day: seconds for day, seconds in self.usage[uid].items() if day not in days}
            if self.current is not None and self.current["uid"] == uid:
                self.current["saved_at"] = self.clock()
            self._save()
