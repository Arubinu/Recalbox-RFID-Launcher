"""Turning the Recalbox off or restarting it, after a countdown that can be cancelled.

Three ways start a countdown:

* the "turn off" card (10 s: removing the card cancels);
* the reader screen's power menu (START + SELECT, 5 s: a controller button cancels);
* nobody playing for a while on the reader screen (30 s: a button or a card cancels).

The service owns the countdown. The reader screen only shows it: the service
writes ``STATE_FILE`` while a countdown runs, and the screen writes its
requests (``poweroff``, ``reboot``, ``cancel``, ``activity``) to
``REQUEST_FILE``. Both files are in RAM (/tmp).
"""

from __future__ import annotations

import json
import os
import time

STATE_FILE = "/tmp/rfid-screen-power.json"
REQUEST_FILE = "/tmp/rfid-screen-power-request.json"

ACTIONS = ("poweroff", "reboot")
#: Seconds before acting, per source.
DELAYS = {"card": 10.0, "menu": 5.0, "idle": 30.0, "curfew": 60.0}
#: A request older than this is ignored (written before a restart of the service).
REQUEST_MAX_AGE_S = 10.0

COMMANDS = {
    "poweroff": "sleep 2; sync; shutdown -h now || poweroff",
    "reboot": "sleep 2; sync; shutdown -r now || reboot",
}

#: Power menu setting (display.power_menu) -> the actions it allows.
MENU_CHOICES = {"both": ("poweroff", "reboot"), "poweroff": ("poweroff",), "off": ()}


def menu_actions(value: str) -> tuple:
    return MENU_CHOICES.get(str(value or "").strip().lower(), MENU_CHOICES["both"])


def write_json(path: str, data: dict) -> None:
    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(temporary, path)
    except OSError:
        pass


def remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def request(action: str, path: str = REQUEST_FILE) -> None:
    """Written by the reader screen."""
    write_json(path, {"action": action, "at": time.time()})


def read_state(path: str = STATE_FILE, wall=None):
    """The countdown running, for the reader screen: {"action", "until", "source"} or None."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("action") not in ACTIONS:
        return None
    if float(data.get("until") or 0) < (wall or time.time)() - 2:
        return None  # left over (service stopped meanwhile)
    return data


class Power:
    """The countdown of the service (one at a time)."""

    def __init__(self, log=None, run=None, wall=None, state_path: str = STATE_FILE,
                 request_path: str = REQUEST_FILE, prepare=None):
        self.log = log
        self.prepare = prepare  # called just before acting (a game running is quit)
        self.run = run or self._run
        self.wall = wall or time.time
        self.state_path = state_path
        self.request_path = request_path
        self.pending = None  # {"action", "until", "source", "uid"}
        self.done = None
        remove(state_path)
        remove(request_path)

    @staticmethod
    def _run(action: str) -> None:
        import subprocess

        subprocess.Popen(["sh", "-c", COMMANDS[action]], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    def _info(self, text: str) -> None:
        if self.log is not None:
            self.log.info(text)

    def begin(self, action: str, source: str, uid: str = None, delay: float = None) -> None:
        if action not in ACTIONS or self.done is not None:
            return
        delay = DELAYS.get(source, 10.0) if delay is None else delay
        self.pending = {"action": action, "until": self.wall() + delay, "source": source, "uid": uid}
        write_json(self.state_path, {"action": action, "until": self.pending["until"], "source": source,
                                     "at": self.wall()})
        self._info("%s dans %d s (%s)" % ("Extinction" if action == "poweroff" else "Redemarrage", delay, source))

    def cancel(self, reason: str = "") -> bool:
        if self.pending is None:
            return False
        self.pending = None
        remove(self.state_path)
        self._info("Extinction annulee%s" % (" (%s)" % reason if reason else ""))
        return True

    def now(self, action: str) -> None:
        """Acts at once (no countdown)."""
        if action not in ACTIONS or self.done is not None:
            return
        self.pending = None
        self.done = action
        remove(self.state_path)
        self._info("%s de la Recalbox" % ("Arret" if action == "poweroff" else "Redemarrage"))
        if self.prepare is not None:
            try:
                self.prepare(action)
            except Exception:  # noqa: BLE001 - turned off all the same
                pass
        try:
            self.run(action)
        except OSError as exc:
            self.done = None
            if self.log is not None:
                self.log.error("Arret impossible : %s" % exc)

    def take_request(self):
        """The reader screen's request, once (or None)."""
        try:
            with open(self.request_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        finally:
            remove(self.request_path)
        if not isinstance(data, dict) or abs(self.wall() - float(data.get("at") or 0)) > REQUEST_MAX_AGE_S:
            return None
        return str(data.get("action") or "")

    def step(self, card_uid=None) -> str:
        """Called by the service loop: "" or the action started."""
        pending = self.pending
        if pending is None:
            return ""
        if pending["source"] == "card" and card_uid != pending["uid"]:
            self.cancel("carte retiree")
            return ""
        if self.wall() >= pending["until"]:
            self.now(pending["action"])
            return pending["action"]
        return ""
