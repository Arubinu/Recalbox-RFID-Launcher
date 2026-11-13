"""Builds the hardware objects from the configuration."""

from __future__ import annotations

import time

from .config import Config
from .drivers.button import Button
from .drivers.gpio_backend import NullBackend, open_gpio
from .drivers.rc522 import Rc522Reader
from .drivers.spi_port import open_spi
from .pairing import CONFIRM_HOLD_S


def build_gpio(cfg: Config, log=None):
    """Opens the GPIO backend (RPi.GPIO, lgpio then sysfs)."""
    return open_gpio("auto", log)


def build_reset_hook(cfg: Config, gpio, log=None):
    """Returns a hardware reset function for the RC522 (or None)."""
    pin = cfg.get_int("rfid", "reset_pin", 25)
    if pin < 0 or gpio is None or isinstance(gpio, NullBackend):
        return None

    claimed = {"done": False}

    def reset() -> None:
        if not claimed["done"]:
            gpio.setup_output(pin, 1)
            claimed["done"] = True
        gpio.write(pin, 0)
        time.sleep(0.05)
        gpio.write(pin, 1)
        time.sleep(0.05)

    return reset


def build_reader(cfg: Config, log=None, gpio=None):
    """Opens the SPI port and returns a ready-to-use RC522 reader."""
    device = cfg.get("rfid", "spi_device", "/dev/spidev0.0")
    speed = cfg.get_int("rfid", "spi_speed_hz", 1000000)
    spi = open_spi(device, speed)
    if log:
        log.info("SPI ouvert : %s (%s, %d Hz)" % (device, getattr(spi, "backend", "?"), speed))

    reset = build_reset_hook(cfg, gpio, log)
    if reset is not None:
        try:
            reset()
        except Exception as exc:  # noqa: BLE001 - the reset is not essential
            if log:
                log.warning("Reset materiel du RC522 ignore : %s" % exc)

    return Rc522Reader(
        spi,
        log=log,
        cooldown_s=cfg.get_float("rfid", "same_tag_cooldown_s", 2.5),
        on_reset=reset,
    )


def build_button(cfg: Config, log=None, gpio=None):
    """Returns the push button, or None if it is disabled."""
    if not cfg.get_bool("button", "enabled", True):
        if log:
            log.info("Bouton d'association desactive dans la configuration")
        return None
    pin = cfg.get_int("button", "pin", 17)
    return Button(
        gpio,
        pin,
        active_low=True,
        debounce_s=cfg.get_int("button", "debounce_ms", 40) / 1000.0,
        hold_press_s=cfg.get_float("button", "hold_press_s", CONFIRM_HOLD_S),
        log=log,
    )
