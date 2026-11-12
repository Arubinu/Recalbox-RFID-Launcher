"""Bouton poussoir avec pull-up interne et anti-rebond logiciel."""

from __future__ import annotations

import time

from .gpio_backend import GpioError


class Button:
    """Bouton entre une broche GPIO et GND (appui = niveau bas).

    ``poll()`` doit etre appele regulierement (toutes les 10 a 50 ms) et retourne
    le geste **au relachement** (jamais au contact, sinon un appui maintenu
    declencherait aussi l'appui court) :

    * ``"short"`` : appui plus court que ``hold_press_s`` ;
    * ``"hold"`` : appui d'au moins ``hold_press_s`` (confirmation d'appairage) ;
    * ``None`` sinon.

    Il n'y a plus de geste "long" : l'effacement d'un badge se fait depuis
    l'interface web, et reassocier un badge existant ecrase l'ancienne
    association.
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
    ):
        self.backend = backend
        self.pin = int(pin)
        self.active_low = bool(active_low)
        self.debounce_s = max(0.005, float(debounce_s))
        self.hold_press_s = max(0.3, float(hold_press_s))
        self.log = log
        self.clock = clock or time.monotonic
        self.available = False

        self._raw_state = False
        self._stable = False
        self._changed_at = self.clock()
        self._pressed_at = None

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
        """Etat courant du bouton (utile au diagnostic)."""
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
        if pressed != self._raw_state:
            # Transition brutale : on attend que l'etat soit stable (anti-rebond).
            self._raw_state = pressed
            self._changed_at = now
            self._stable = False
            return None

        if self._stable or (now - self._changed_at) < self.debounce_s:
            return None

        self._stable = True
        if self._raw_state:  # appui confirme
            self._pressed_at = now
            if self.log:
                self.log.debug("Bouton appuye")
            return None

        # relachement confirme
        if self._pressed_at is None:
            return None
        duration = now - self._pressed_at
        self._pressed_at = None
        if self.log:
            self.log.info("Bouton relache apres %.2f s" % duration)
        return "hold" if duration >= self.hold_press_s else "short"

    def close(self) -> None:
        if self.backend is not None and self.available:
            try:
                self.backend.close()
            except Exception:  # noqa: BLE001
                pass
            self.available = False
