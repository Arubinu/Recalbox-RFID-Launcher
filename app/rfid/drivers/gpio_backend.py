"""GPIO pin access: push button and RC522 reader reset.

Three implementations are tried in this order:

1. ``RPi.GPIO`` (shipped with Recalbox, ``rpi-lgpio`` module): reading and
   internal pull-up in one line, the normal mode on a Raspberry Pi 3;
2. ``lgpio`` (low-level library, also present);
3. ``/sys/class/gpio`` (last resort, the internal pull-up cannot be set: an
   external resistor is then needed).

The button is wired between the pin and GND: with the internal pull-up, the
pin reads 1 at rest and 0 when pressed, without any resistor to solder.
"""

from __future__ import annotations

import contextlib
import os
import time


class GpioError(Exception):
    """GPIO pin access error."""


# ---------------------------------------------------------------------------
# Safe working directory (lgpio creates its notification pipes in the
# current directory). On Recalbox, the service starts with PWD=/ which is
# read-only: without this fallback, importing lgpio/RPi.GPIO fails and the
# sysfs backend is used, which recent kernels refuse (error 22 on export).
# ---------------------------------------------------------------------------
def _writable_dir() -> str:
    candidates = [os.environ.get("RFID_GPIO_DIR"), "/tmp", os.environ.get("TMPDIR"), "/run"]
    for folder in candidates:
        if not folder or not os.path.isdir(folder):
            continue
        try:
            probe = os.path.join(folder, ".rfid-gpio-test")
            with open(probe, "w", encoding="ascii") as handle:
                handle.write("ok")
            os.remove(probe)
            return folder
        except OSError:
            continue
    return ""


@contextlib.contextmanager
def _workdir(folder: str):
    """Temporarily changes the directory (and HOME when needed)."""
    try:
        previous_dir = os.getcwd()
    except OSError:
        previous_dir = None  # deleted (program folder replaced by an update)
    previous_home = os.environ.get("HOME", "")
    try:
        if folder:
            os.chdir(folder)
            if not previous_home or not os.access(previous_home, os.W_OK):
                os.environ["HOME"] = folder
        yield
    finally:
        if previous_dir:
            with contextlib.suppress(OSError):
                os.chdir(previous_dir)
        if previous_home:
            os.environ["HOME"] = previous_home


# ---------------------------------------------------------------------------
# RPi.GPIO (rpi-lgpio)
# ---------------------------------------------------------------------------
class RpiGpioBackend:
    name = "RPi.GPIO"

    def __init__(self):
        try:
            # The import itself opens the lgpio notification pipes: it must
            # happen from a writable directory.
            with _workdir(_writable_dir()):
                import RPi.GPIO as GPIO  # type: ignore
        except ImportError as exc:
            raise GpioError("module RPi.GPIO absent : %s" % exc)
        self._gpio = GPIO
        with contextlib.suppress(Exception):
            GPIO.setwarnings(False)
        with _workdir(_writable_dir()):
            GPIO.setmode(GPIO.BCM)
        self._claimed = set()

    def setup_input(self, pin: int, pull_up: bool = True) -> None:
        pull = self._gpio.PUD_UP if pull_up else self._gpio.PUD_OFF
        self._gpio.setup(pin, self._gpio.IN, pull_up_down=pull)
        self._claimed.add(pin)

    def setup_output(self, pin: int, value: int = 0) -> None:
        self._gpio.setup(pin, self._gpio.OUT, initial=value)
        self._claimed.add(pin)

    def write(self, pin: int, value: int) -> None:
        self._gpio.output(pin, 1 if value else 0)

    def read(self, pin: int) -> int:
        return int(self._gpio.input(pin))

    def close(self) -> None:
        for pin in list(self._claimed):
            try:
                self._gpio.cleanup(pin)
            except Exception:  # noqa: BLE001
                pass
        self._claimed.clear()


# ---------------------------------------------------------------------------
# lgpio
# ---------------------------------------------------------------------------
class LgpioBackend:
    name = "lgpio"

    def __init__(self, chip: int = 0):
        try:
            with _workdir(_writable_dir()):
                import lgpio  # type: ignore
        except ImportError as exc:
            raise GpioError("module lgpio absent : %s" % exc)
        self._lgpio = lgpio
        try:
            with _workdir(_writable_dir()):
                self._handle = lgpio.gpiochip_open(chip)
        except Exception as exc:  # noqa: BLE001
            raise GpioError("ouverture de gpiochip%d impossible : %s" % (chip, exc))

    def setup_input(self, pin: int, pull_up: bool = True) -> None:
        flags = 0
        if pull_up:
            flags = getattr(self._lgpio, "SET_BIAS_PULL_UP", 32)
        self._lgpio.gpio_claim_input(self._handle, pin, flags)

    def setup_output(self, pin: int, value: int = 0) -> None:
        self._lgpio.gpio_claim_output(self._handle, pin, 1 if value else 0)

    def write(self, pin: int, value: int) -> None:
        self._lgpio.gpio_write(self._handle, pin, 1 if value else 0)

    def read(self, pin: int) -> int:
        return int(self._lgpio.gpio_read(self._handle, pin))

    def close(self) -> None:
        try:
            self._lgpio.gpiochip_close(self._handle)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# sysfs (last resort)
# ---------------------------------------------------------------------------
def chip_base(root: str = "/sys/class/gpio") -> int:
    """Number of BCM pin 0 in /sys/class/gpio: 0 on old kernels, 512 on recent
    ones (gpiochip512). The chip of the Pi's pins is the "pinctrl-bcm..." one,
    else the lowest."""
    chips = []
    try:
        names = os.listdir(root)
    except OSError:
        return 0
    for name in names:
        if not name.startswith("gpiochip"):
            continue
        try:
            with open(os.path.join(root, name, "base"), encoding="ascii") as handle:
                base = int(handle.read().strip())
        except (OSError, ValueError):
            continue
        try:
            with open(os.path.join(root, name, "label"), encoding="ascii", errors="replace") as handle:
                label = handle.read().strip()
        except OSError:
            label = ""
        chips.append((not label.startswith("pinctrl-bcm"), base))
    return min(chips)[1] if chips else 0


class SysfsBackend:
    name = "/sys/class/gpio"

    def __init__(self, root: str = "/sys/class/gpio"):
        self.root = root
        if not os.path.isfile(os.path.join(root, "export")):
            raise GpioError("interface /sys/class/gpio absente")
        self._claimed = set()
        self._cached_value = {}
        self.base = chip_base(root)

    def _path(self, pin: int, leaf: str) -> str:
        return os.path.join(self.root, "gpio%d" % (self.base + pin), leaf)

    def _export(self, pin: int) -> None:
        if os.path.isdir(os.path.join(self.root, "gpio%d" % (self.base + pin))):
            return
        try:
            with open(os.path.join(self.root, "export"), "w", encoding="ascii") as handle:
                handle.write(str(self.base + pin))
            time.sleep(0.05)
        except OSError as exc:
            raise GpioError("export de la broche %d impossible : %s" % (pin, exc))

    def setup_input(self, pin: int, pull_up: bool = True) -> None:
        self._export(pin)
        try:
            with open(self._path(pin, "direction"), "w", encoding="ascii") as handle:
                handle.write("in")
        except OSError as exc:
            raise GpioError("configuration de la broche %d impossible : %s" % (pin, exc))
        self._claimed.add(pin)

    def setup_output(self, pin: int, value: int = 0) -> None:
        self._export(pin)
        try:
            with open(self._path(pin, "direction"), "w", encoding="ascii") as handle:
                handle.write("high" if value else "low")
        except OSError as exc:
            raise GpioError("configuration de la broche %d impossible : %s" % (pin, exc))
        self._claimed.add(pin)

    def write(self, pin: int, value: int) -> None:
        try:
            with open(self._path(pin, "value"), "w", encoding="ascii") as handle:
                handle.write("1" if value else "0")
        except OSError as exc:
            raise GpioError("ecriture de la broche %d impossible : %s" % (pin, exc))

    def read(self, pin: int) -> int:
        path = self._path(pin, "value")
        try:
            handle = self._cached_value.get(pin)
            if handle is None:
                handle = open(path, "r", encoding="ascii")
                self._cached_value[pin] = handle
            handle.seek(0)
            return 1 if handle.read(1).strip() == "1" else 0
        except OSError as exc:
            raise GpioError("lecture de la broche %d impossible : %s" % (pin, exc))

    def close(self) -> None:
        for handle in self._cached_value.values():
            try:
                handle.close()
            except OSError:
                pass
        self._cached_value.clear()
        for pin in list(self._claimed):
            try:
                with open(os.path.join(self.root, "unexport"), "w", encoding="ascii") as handle:
                    handle.write(str(self.base + pin))
            except OSError:
                pass
        self._claimed.clear()


class NullBackend:
    """No pin available (button disabled)."""

    name = "aucune"

    def setup_input(self, pin: int, pull_up: bool = True) -> None:
        raise GpioError("GPIO indisponible")

    def setup_output(self, pin: int, value: int = 0) -> None:
        raise GpioError("GPIO indisponible")

    def write(self, pin: int, value: int) -> None:
        raise GpioError("GPIO indisponible")

    def read(self, pin: int) -> int:
        raise GpioError("GPIO indisponible")

    def close(self) -> None:
        pass


BACKENDS = ("rpi", "lgpio", "sysfs")


def open_gpio(prefer: str = "auto", log=None):
    """Opens the first available GPIO backend."""
    order = list(BACKENDS)
    prefer = (prefer or "auto").lower()
    if prefer in order:
        order.remove(prefer)
        order.insert(0, prefer)

    errors = []
    for candidate in order:
        try:
            if candidate == "rpi":
                backend = RpiGpioBackend()
            elif candidate == "lgpio":
                backend = LgpioBackend()
            else:
                backend = SysfsBackend()
            if log:
                log.info("GPIO : backend %s%s" % (backend.name, (" (%s)" % " ; ".join(errors)) if errors else ""))
            return backend
        except (GpioError, OSError) as exc:
            errors.append("%s: %s" % (candidate, exc))
            continue
    if log:
        log.warning("Aucun backend GPIO disponible (%s)" % " ; ".join(errors))
    return NullBackend()
