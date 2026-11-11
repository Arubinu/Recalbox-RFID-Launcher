"""Fabrication du materiel a partir de la configuration."""

from __future__ import annotations

import time

from .config import Config
from .drivers.button import Button
from .drivers.gpio_backend import NullBackend, open_gpio
from .drivers.rc522 import Rc522Reader
from .drivers.spi_port import open_spi


def build_gpio(cfg: Config, log=None):
    """Ouvre le backend GPIO (RPi.GPIO, lgpio puis sysfs)."""
    return open_gpio("auto", log)


def build_reset_hook(cfg: Config, gpio, log=None):
    """Retourne une fonction de reset materiel du RC522 (ou None)."""
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
    """Ouvre le port SPI et retourne un lecteur RC522 pret a l'emploi."""
    device = cfg.get("rfid", "spi_device", "/dev/spidev0.0")
    speed = cfg.get_int("rfid", "spi_speed_hz", 1000000)
    spi = open_spi(device, speed)
    if log:
        log.info("SPI ouvert : %s (%s, %d Hz)" % (device, getattr(spi, "backend", "?"), speed))

    reset = build_reset_hook(cfg, gpio, log)
    if reset is not None:
        try:
            reset()
        except Exception as exc:  # noqa: BLE001 - le reset n'est pas indispensable
            if log:
                log.warning("Reset materiel du RC522 ignore : %s" % exc)

    return Rc522Reader(
        spi,
        log=log,
        cooldown_s=cfg.get_float("rfid", "same_tag_cooldown_s", 2.5),
        on_reset=reset,
    )


def build_button(cfg: Config, log=None, gpio=None):
    """Retourne le bouton poussoir, ou None s'il est desactive."""
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
        long_press_s=cfg.get_float("button", "long_press_s", 2.0),
        log=log,
    )
