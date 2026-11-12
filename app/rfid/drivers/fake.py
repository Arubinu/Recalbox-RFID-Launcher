"""Lecteur et bouton simules : tests unitaires et mode ``simulate``."""

from __future__ import annotations

from collections import deque


class FakeReader:
    """Lecteur scriptable : les UID sont pousses par ``feed()``."""

    backend = "simulateur"

    def __init__(self, log=None, cooldown_s: float = 0.0):
        self.log = log
        self.cooldown_s = cooldown_s
        self.queue = deque()
        self.started = False
        self.version = 0x91

    def feed(self, uid: str) -> None:
        self.queue.append(str(uid).replace(":", "").replace(" ", "").upper())

    def start(self) -> int:
        self.started = True
        return self.version

    def read_uid(self):
        if not self.started:
            self.start()
        if not self.queue:
            return None
        return self.queue.popleft()

    def tag_present(self) -> bool:
        """Simulateur : un badge est present si la file n'est pas vide."""
        return bool(self.queue)

    def close(self) -> None:
        self.started = False


class FakeButton:
    """Bouton scriptable : ``press()`` pousse un geste ("short" ou "long")."""

    name = "simulateur"

    def __init__(self, log=None):
        self.log = log
        self.queue = deque()
        self.available = True

    def press(self, gesture: str = "short") -> None:
        self.queue.append("long" if gesture == "long" else "short")

    def poll(self):
        if not self.queue:
            return None
        return self.queue.popleft()

    def close(self) -> None:
        self.available = False
