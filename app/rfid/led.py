"""Status light: an RGB LED or a strip of programmable LEDs (WS2812).

Two kinds of hardware:

* **RGB LED** (4 legs): one GPIO pin per colour, shared leg on GND (common
  cathode) or on 3.3 V (common anode). Colours are on/off: red, green, blue,
  yellow, cyan, magenta, white. A resistor is needed on each colour leg,
  unless the LED is soldered on a small board that already has them (KY-016
  module and the like): see docs/WIRING.md.
* **Programmable LEDs** (WS2812, WS2812B, SK6812, "NeoPixel"): a single data
  wire, driven by the second SPI bus of the Raspberry Pi (``/dev/spidev1.0``,
  data on GPIO20 = physical pin 38). Each data bit is sent as one SPI byte at
  6.4 MHz, which gives the timing these LEDs expect without any library. The
  first SPI bus cannot be used: its data line is shared with the RC522.

The service tells the light what is going on (``set_state``) and which
event just happened (``flash``); ``update`` is called at each loop turn and
writes the colour only when it changes.
"""

from __future__ import annotations

import time

OFF = (0, 0, 0)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
BLUE = (0, 80, 255)
WHITE = (255, 255, 255)
YELLOW = (255, 190, 0)
ORANGE = (255, 90, 0)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 200)
PURPLE = (90, 0, 255)

#: Lasting states: (colour, blink period in seconds or 0 for steady).
STATES = {
    "off": (OFF, 0.0),
    "idle": (GREEN, 0.0),
    "playing": (GREEN, 0.0),
    "noreader": (RED, 2.0),
    "pairing": (WHITE, 0.5),
    "associate": (BLUE, 0.6),
    "delete": (ORANGE, 0.6),
    "warning": (YELLOW, 0.8),
    #: Bedtime: no games now (option [led] signals).
    "bedtime": (PURPLE, 0.0),
    #: The active player has no time left today (option [led] signals).
    "exhausted": (ORANGE, 0.0),
}

#: Short events: (colour, duration, blink period).
EVENTS = {
    "ok": (GREEN, 0.9, 0.0),
    "launch": (WHITE, 0.7, 0.0),
    "error": (RED, 0.9, 0.3),
    "bonus": (MAGENTA, 1.2, 0.0),
    "timeup": (ORANGE, 2.0, 0.25),
}


class NullLight:
    name = "none"

    def write(self, colour) -> None:
        pass

    def close(self) -> None:
        pass


class RgbLight:
    """Three GPIO pins (on/off per colour)."""

    name = "rgb"

    def __init__(self, gpio, pins, common_anode: bool = False):
        self.gpio = gpio
        self.pins = [int(pin) for pin in pins]
        self.common_anode = bool(common_anode)
        for pin in self.pins:
            gpio.setup_output(pin, 1 if self.common_anode else 0)

    def write(self, colour) -> None:
        for pin, value in zip(self.pins, colour):
            on = value >= 96
            self.gpio.write(pin, (0 if on else 1) if self.common_anode else (1 if on else 0))

    def close(self) -> None:
        try:
            self.write(OFF)
        except Exception:  # noqa: BLE001 - closing must never fail
            pass


#: One SPI byte per LED bit, at 6.4 MHz (156 ns per SPI bit):
#: 0 -> 2 high bits (312 ns), 1 -> 5 high bits (780 ns), 1.25 us per bit.
#: Every byte ends low: a pause of the SPI controller between two bytes only
#: lengthens a low phase, which these LEDs tolerate.
WS_ZERO = 0xC0
WS_ONE = 0xF8


def ws2812_frame(colours, brightness: float = 1.0) -> bytes:
    """SPI bytes for WS2812 LEDs (GRB order), followed by the reset pause."""
    data = bytearray()
    for red, green, blue in colours:
        for value in (green, red, blue):
            value = max(0, min(255, int(round(value * brightness))))
            for shift in range(7, -1, -1):
                data.append(WS_ONE if (value >> shift) & 1 else WS_ZERO)
    # Reset: the line stays low for more than 280 us (WS2812B V5).
    return b"\x00" + bytes(data) + b"\x00" * 240


class Ws2812Light:
    """Programmable LEDs on the second SPI bus."""

    name = "ws2812"
    SPEED_HZ = 6400000

    def __init__(self, spi, count: int = 1, brightness: float = 0.4):
        self.spi = spi
        # 150 LEDs = 3600 bytes + reset: under the 4096 byte spidev buffer.
        self.count = max(1, min(150, int(count)))
        self.brightness = max(0.02, min(1.0, float(brightness)))

    def write(self, colour) -> None:
        self.spi.transfer(ws2812_frame([colour] * self.count, self.brightness))

    def close(self) -> None:
        try:
            self.write(OFF)
            self.spi.close()
        except Exception:  # noqa: BLE001
            pass


class StatusLight:
    """Chooses the colour from the service state and the recent events."""

    def __init__(self, output=None, idle_on: bool = True, clock=None, log=None):
        self.output = output or NullLight()
        self.idle_on = bool(idle_on)
        self.clock = clock or time.monotonic
        self.log = log
        self.state = "idle"
        self._event = None
        self._written = None
        self._failures = 0

    @property
    def enabled(self) -> bool:
        return not isinstance(self.output, NullLight)

    def set_state(self, state: str) -> None:
        self.state = state if state in STATES else "idle"

    def flash(self, event: str) -> None:
        if event in EVENTS:
            colour, duration, period = EVENTS[event]
            self._event = (colour, self.clock() + duration, period, self.clock())

    def colour(self):
        now = self.clock()
        if self._event is not None:
            colour, until, period, since = self._event
            if now < until:
                return _blink(colour, period, now - since)
            self._event = None
        colour, period = STATES.get(self.state, STATES["idle"])
        if self.state in ("idle", "playing") and not self.idle_on:
            return OFF
        return _blink(colour, period, now)

    def update(self) -> None:
        if not self.enabled or self._failures >= 5:
            return
        colour = self.colour()
        if colour == self._written:
            return
        try:
            self.output.write(colour)
            self._written = colour
        except Exception as exc:  # noqa: BLE001 - a light must never stop the service
            self._failures += 1
            if self.log:
                self.log.warning("Voyant : ecriture impossible (%s)" % exc)

    def close(self) -> None:
        self.output.close()


def _blink(colour, period: float, elapsed: float):
    if not period:
        return colour
    return colour if (elapsed % period) < period / 2.0 else OFF


def build_light(cfg, gpio=None, log=None, open_spi=None) -> StatusLight:
    """Builds the light described by the ``[led]`` section (or a silent one)."""
    kind = (cfg.get("led", "type", "none") or "none").strip().lower()
    idle_on = cfg.get_bool("led", "idle", True)
    output = NullLight()
    try:
        if kind == "rgb":
            if gpio is None:
                raise RuntimeError("GPIO indisponible")
            pins = (cfg.get_int("led", "pin_red", 22), cfg.get_int("led", "pin_green", 23),
                    cfg.get_int("led", "pin_blue", 24))
            output = RgbLight(gpio, pins, cfg.get("led", "common", "cathode").lower() == "anode")
        elif kind == "ws2812":
            if open_spi is None:
                from .drivers.spi_port import open_spi as open_spi  # noqa: PLW0127
            spi = open_spi(cfg.get("led", "spi_device", "/dev/spidev1.0"), Ws2812Light.SPEED_HZ)
            output = Ws2812Light(spi, cfg.get_int("led", "count", 1),
                                 cfg.get_int("led", "brightness", 40) / 100.0)
    except Exception as exc:  # noqa: BLE001 - no light rather than no service
        if log:
            log.warning("Voyant %s indisponible : %s" % (kind, exc))
        output = NullLight()
    if log and not isinstance(output, NullLight):
        log.info("Voyant actif (%s)" % output.name)
    return StatusLight(output, idle_on=idle_on, log=log)
