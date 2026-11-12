"""Outils communs aux tests (aucun materiel, aucune dependance)."""

from __future__ import annotations

import os
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class FakeClock:
    """Horloge controlee par le test."""

    def __init__(self, start: float = 1000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


class FakeLauncher:
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.calls = []

    def start_game(self, system: str, game: str) -> bool:
        self.calls.append((system, game))
        return self.ok


class RecordingLog:
    """Journal en memoire : (niveau, message) pour les assertions."""

    def __init__(self):
        self.messages = []

    def _add(self, level):
        def recorder(message):
            self.messages.append((level, str(message)))
        return recorder

    def debug(self, message):
        self._add("debug")(message)

    def info(self, message):
        self._add("info")(message)

    def warning(self, message):
        self._add("warning")(message)

    def error(self, message):
        self._add("error")(message)


class FakeFeedback:
    """Enregistre les signaux envoyes a l'utilisateur."""

    def __init__(self):
        self.events = []

    def _add(self, name):
        self.events.append(name)

    def ok(self):
        self._add("ok")

    def armed(self):
        self._add("armed")

    def armed_delete(self):
        self._add("armed_delete")

    def error(self):
        self._add("error")

    def recognized(self):
        self._add("recognized")

    def removed(self):
        self._add("removed")

    def timeout(self):
        self._add("timeout")

    def timeout(self):
        self._add("timeout")


class FakeGpio:
    """Backend GPIO scriptable (niveau haut = relache)."""

    name = "fake"

    def __init__(self):
        self.levels = {}
        self.outputs = {}

    def setup_input(self, pin, pull_up=True):
        self.levels.setdefault(pin, 1)

    def setup_output(self, pin, value=0):
        self.outputs[pin] = value

    def write(self, pin, value):
        self.outputs[pin] = value

    def read(self, pin):
        return self.levels.get(pin, 1)

    def close(self):
        pass
