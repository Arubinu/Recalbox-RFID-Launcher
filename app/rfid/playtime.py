"""Play time: time-limited games and bonus cards.

* A game card (or a "random game" card) may carry a limit in minutes; the
  general setting ``[time] default_limit_min`` applies to the cards without
  their own limit. When the time is up, the game is quit.
* A **bonus card** adds minutes:

  - to the running time-limited game;
  - or, when that game has just ended (time up, card removed, quit), it
    starts it again with the bonus time: in "cartridge" mode, the bonus card
    is inserted in the slot instead of the game card.

  Each bonus card has a quota: ``uses`` per ``period_h`` hours (0 = no
  quota). The uses are saved in ``playtime.json``.

Without a battery, the Recalbox clock may restart in 1980 until the network
gives the time: uses dated "in the future" are then forgotten (the quota is
not reliable without network, which is acceptable for a family feature).
"""

from __future__ import annotations

import json
import os
import time

#: A game that ended less than this ago can be continued by a bonus card.
RESUME_WINDOW_S = 15 * 60

#: Warnings before the end (seconds).
WARN_STEPS_S = (300, 60)

PLAYTIME_FILENAME = "playtime.json"


class PlayTimer:
    """Time-limited session in progress and bonus quotas."""

    def __init__(self, home: str = None, clock=None, wall=None, log=None):
        self.home = home
        self.clock = clock or time.monotonic
        self.wall = wall or time.time
        self.log = log
        self.session = None          # running time-limited game
        self.last = None             # last ended session (for a bonus card)
        self._usage = self._load()

    # ------------------------------------------------------------ persistence
    def _path(self) -> str:
        return os.path.join(self.home, PLAYTIME_FILENAME) if self.home else ""

    def _load(self) -> dict:
        path = self._path()
        if not path:
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        usage = data.get("bonus") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return {}
        return {str(uid): [float(stamp) for stamp in stamps if isinstance(stamp, (int, float))]
                for uid, stamps in usage.items() if isinstance(stamps, list)}

    def _save(self) -> None:
        path = self._path()
        if not path:
            return
        temporary = path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"bonus": self._usage}, handle)
            os.replace(temporary, path)
        except OSError as exc:
            if self.log:
                self.log.warning("Temps de jeu non enregistre : %s" % exc)

    # ---------------------------------------------------------------- session
    def start(self, uid: str, entry: dict, minutes: int) -> None:
        """A game has just been started from a card (minutes <= 0: no limit)."""
        if not minutes or minutes <= 0:
            self.session = None
            return
        now = self.clock()
        self.session = {
            "uid": uid,
            "entry": dict(entry),
            "started": now,
            "deadline": now + minutes * 60.0,
            "minutes": minutes,
            "warned": [],
        }
        if self.log:
            self.log.info("Temps de jeu limite a %d min (%s)" % (minutes, entry.get("name") or ""))

    def end(self, reason: str) -> None:
        """The limited game is over (time up, card removed, quit)."""
        if self.session is None:
            return
        remaining = max(0.0, self.session["deadline"] - self.clock())
        self.last = dict(self.session, ended=self.clock(), reason=reason, remaining=remaining)
        self.session = None

    def remaining_s(self):
        if self.session is None:
            return None
        return max(0.0, self.session["deadline"] - self.clock())

    def tick(self) -> str:
        """Returns "warn300", "warn60", "expired" or "" (call it often)."""
        if self.session is None:
            return ""
        left = self.session["deadline"] - self.clock()
        if left <= 0:
            self.end("time")
            return "expired"
        for step in WARN_STEPS_S:
            if left <= step and step not in self.session["warned"]:
                # A short session skips the warnings that were already due.
                self.session["warned"].extend(s for s in WARN_STEPS_S if s >= step)
                if self.session["minutes"] * 60 > step:
                    return "warn%d" % step
        return ""

    # ------------------------------------------------------------------ bonus
    def _prune(self, uid: str, period_s: float) -> list:
        now = self.wall()
        stamps = [stamp for stamp in self._usage.get(uid, []) if now - period_s < stamp <= now + 60]
        self._usage[uid] = stamps
        return stamps

    def bonus_left(self, uid: str, params: dict):
        """Remaining uses of a bonus card in the current period (None = no quota)."""
        uses = int(params.get("uses") or 0)
        if uses <= 0:
            return None
        stamps = self._prune(uid, float(params.get("period_h") or 24) * 3600.0)
        return max(0, uses - len(stamps))

    def bonus(self, uid: str, params: dict) -> dict:
        """Applies a bonus card.

        Returns ``{"result": ...}``:

        * ``extended``  -- minutes added to the running game;
        * ``resume``    -- the game of ``entry`` must be started again for ``minutes``;
        * ``nothing``   -- no limited game running or recently ended;
        * ``exhausted`` -- quota used up for this period.
        """
        minutes = int(params.get("minutes") or 10)
        left = self.bonus_left(uid, params)
        if left is not None and left <= 0:
            return {"result": "exhausted", "minutes": minutes}
        if self.session is not None:
            self.session["deadline"] += minutes * 60.0
            self.session["minutes"] += minutes
            self.session["warned"] = [step for step in self.session["warned"]
                                      if self.session["deadline"] - self.clock() <= step]
            self._use(uid)
            return {"result": "extended", "minutes": minutes, "left": self._left_after(uid, params)}
        last = self.last
        if last is not None and self.clock() - last["ended"] <= RESUME_WINDOW_S:
            self._use(uid)
            total = minutes + int(round(last.get("remaining", 0.0) / 60.0))
            self.last = None
            return {"result": "resume", "minutes": total, "entry": last["entry"],
                    "game_uid": last["uid"], "left": self._left_after(uid, params)}
        return {"result": "nothing", "minutes": minutes}

    def _use(self, uid: str) -> None:
        self._usage.setdefault(uid, []).append(self.wall())
        self._save()

    def _left_after(self, uid: str, params: dict):
        return self.bonus_left(uid, params)

    def status(self) -> dict:
        """Summary for status.json (shown by the page)."""
        if self.session is None:
            return {}
        return {
            "name": self.session["entry"].get("name") or "",
            "remaining_s": int(self.remaining_s() or 0),
            "minutes": self.session["minutes"],
        }
