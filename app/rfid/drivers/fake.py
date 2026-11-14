"""Simulated reader and button: unit tests and ``simulate`` mode."""

from __future__ import annotations

from collections import deque


class FakeReader:
    """Scriptable reader: UIDs are pushed with ``feed()``."""

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
        """Simulator: a badge is present while the queue is not empty."""
        return bool(self.queue)

    def close(self) -> None:
        self.started = False


class FakeButton:
    """Scriptable button: ``press()`` pushes a gesture ("short" or "hold")."""

    name = "simulateur"

    def __init__(self, log=None):
        self.log = log
        self.queue = deque()
        self.available = True

    def press(self, gesture: str = "short") -> None:
        self.queue.append(gesture if gesture in ("hold", "double") else "short")

    def poll(self):
        if not self.queue:
            return None
        return self.queue.popleft()

    def close(self) -> None:
        self.available = False
