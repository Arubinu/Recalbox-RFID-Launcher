"""Push button with internal pull-up and software debounce."""

from __future__ import annotations

import time

from .gpio_backend import GpioError


class Button:
    """Button between a GPIO pin and GND (pressed = low level).

    ``poll()`` must be called regularly (every 10 to 50 ms) and returns:

    * ``"hold"`` **as soon as the press reaches ``hold_press_s``**, without
      waiting for the release (pairing confirmation: the finger may stay);
    * ``"short"`` on release, if the press is shorter than ``hold_press_s``
      (and if ``"hold"`` has not been sent already), once ``double_s`` passed
      without a second press;
    * ``"double"`` on the release of a second short press started within
      ``double_s`` of the first one;
    * ``None`` otherwise.

    The short press is never sent on contact: a held press would then trigger
    both gestures.

    There is no "long" gesture any more: a badge is erased from the web
    interface, and pairing an existing badge again overwrites the old pairing.
    """

    def __init__(
        self,
        backend,
        pin: int,
        active_low: bool = True,
        debounce_s: float = 0.04,
        hold_press_s: float = 3.0,
        log=None,
        clock=None,
        double_s: float = 0.4,
    ):
        self.backend = backend
        self.pin = int(pin)
        self.active_low = bool(active_low)
        self.debounce_s = max(0.005, float(debounce_s))
        self.hold_press_s = max(0.3, float(hold_press_s))
        #: Second press within this delay: a double press.
        self.double_s = max(0.0, float(double_s))
        self.log = log
        self.clock = clock or time.monotonic
        self.available = False

        self._raw_state = False
        self._stable = False
        self._changed_at = self.clock()
        self._pressed_at = None
        self._hold_fired = False
        #: Release of a short press waiting to know whether a second one comes.
        self._short_at = None
        #: The press in progress is the second one of a double press.
        self._second = False

        if backend is None:
            return
        try:
            backend.setup_input(self.pin, pull_up=self.active_low)
            self.available = True
            self._raw_state = self._is_pressed()
        except (GpioError, OSError) as exc:
            if self.log:
                self.log.warning("Bouton indisponible sur la broche %d : %s" % (self.pin, exc))

    # ------------------------------------------------------------------ interne
    def _is_pressed(self) -> bool:
        level = int(self.backend.read(self.pin))
        return (level == 0) if self.active_low else (level == 1)

    # ------------------------------------------------------------------- public
    def is_pressed(self) -> bool:
        """Current button state (useful for diagnostics)."""
        if not self.available:
            return False
        try:
            return self._is_pressed()
        except (GpioError, OSError):
            return False

    def poll(self):
        if not self.available:
            return None
        try:
            pressed = self._is_pressed()
        except (GpioError, OSError) as exc:
            self.available = False
            if self.log:
                self.log.warning("Lecture du bouton impossible : %s" % exc)
            return None

        now = self.clock()

        # 0. a short press without a second one is sent once the delay passed
        if (self._short_at is not None and not self._raw_state and not pressed
                and now - self._short_at >= self.double_s):
            self._short_at = None
            return "short"

        # 1. raw transition: wait for the state to be stable (debounce)
        if pressed != self._raw_state:
            self._raw_state = pressed
            self._changed_at = now
            self._stable = False
            return None
        if not self._stable:
            if (now - self._changed_at) < self.debounce_s:
                return None
            self._stable = True
            if self._raw_state:
                self._pressed_at = now
                self._hold_fired = False
                self._second = self._short_at is not None
                self._short_at = None
                if self.log:
                    self.log.debug("Bouton appuye")
                return None
            # relachement confirme
            if self._pressed_at is None:
                return None
            duree = now - self._pressed_at
            self._pressed_at = None
            if self.log:
                self.log.info("Bouton relache apres %.2f s" % duree)
            second = self._second
            self._second = False
            if self._hold_fired:
                self._hold_fired = False
                return None               # validation already done during the press
            if duree >= self.hold_press_s:
                return "hold"
            if second:
                return "double"
            if self.double_s <= 0:
                return "short"
            self._short_at = now
            return None

        # 2. stable state: the held press is validated as soon as the duration is reached
        if self._raw_state and not self._hold_fired and self._pressed_at is not None:
            if (now - self._pressed_at) >= self.hold_press_s:
                self._hold_fired = True
                if self.log:
                    self.log.info(
                        "Bouton maintenu %.2f s : validation" % (now - self._pressed_at)
                    )
                return "hold"
        return None

    def close(self) -> None:
        if self.backend is not None and self.available:
            try:
                self.backend.close()
            except Exception:  # noqa: BLE001
                pass
            self.available = False
