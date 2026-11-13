"""Automatic reader tuning.

The service measures the hardware (supported SPI speed, duration of a read,
badge behaviour, removal latency) then derives three settings from it:

* ``rfid.spi_speed_hz`` - the fastest bus speed that really works on this
  Raspberry Pi and this module;
* ``rfid.poll_interval_ms`` - the read rate, based on the real duration of a
  read (no point asking faster than the reader answers);
* ``rfid.rearm_absent_ms`` - the absence delay, based on the latency measured
  when the badge is removed.

This module only holds computations: no hardware read, no disk access. It can
therefore be tested on a PC, and the service keeps control of the reader.
"""

from __future__ import annotations

#: Speeds tried, from fastest to slowest. The RC522 accepts up to 10 MHz,
#: but above 4 MHz many clone modules become unstable: the first one that
#: answers perfectly is kept.
SPEEDS = (8000000, 4000000, 2000000, 1000000, 500000)

#: Fallback speed if the measurement is wrong (the original shipped value).
SPEED_FALLBACK = 1000000

#: Steps of the sequence, in order. Used by the page counter.
STEPS = ("speed", "read", "presence", "remove", "reinsert")

#: Original values, used by the "Reset" button.
DEFAULTS = {
    "rfid.spi_speed_hz": str(SPEED_FALLBACK),
    "rfid.poll_interval_ms": "150",
    "rfid.rearm_absent_ms": "1200",
}

#: Bounds of the computed settings.
POLL_MIN_MS = 60
POLL_MAX_MS = 500
ABSENCE_MIN_MS = 1000
ABSENCE_MAX_MS = 4000

#: Margin added to the duration of a read to set the rate.
POLL_MARGIN_MS = 30

#: Safety factor applied to the measured removal latency.
ABSENCE_FACTOR = 1.5


def clamp(valeur: float, mini: float, maxi: float) -> float:
    return max(mini, min(maxi, valeur))


def poll_interval_ms(read_ms) -> int:
    """Read rate derived from the measured duration of a read."""
    try:
        duree = float(read_ms or 0)
    except (TypeError, ValueError):
        duree = 0.0
    return int(round(clamp(duree + POLL_MARGIN_MS, POLL_MIN_MS, POLL_MAX_MS)))


def absence_ms(measured_ms) -> int:
    """Absence delay derived from the measured removal latency."""
    try:
        latence = float(measured_ms or 0)
    except (TypeError, ValueError):
        latence = 0.0
    return int(round(clamp(latence * ABSENCE_FACTOR, ABSENCE_MIN_MS, ABSENCE_MAX_MS)))


def settings_from(measures: dict) -> dict:
    """Turns the measures into configuration values (section.key -> text)."""
    measures = measures or {}
    vitesse = measures.get("best_speed") or SPEED_FALLBACK
    try:
        vitesse = int(vitesse)
    except (TypeError, ValueError):
        vitesse = SPEED_FALLBACK
    if vitesse not in SPEEDS:
        vitesse = SPEED_FALLBACK
    return {
        "rfid.spi_speed_hz": str(vitesse),
        "rfid.poll_interval_ms": str(poll_interval_ms(measures.get("read_ms"))),
        "rfid.rearm_absent_ms": str(absence_ms(measures.get("absence_ms"))),
    }


def speed_label(hz) -> str:
    """"4 MHz", "500 kHz": readable on the page as in the log."""
    try:
        valeur = float(hz)
    except (TypeError, ValueError):
        return "?"
    if valeur >= 1000000:
        return ("%g MHz" % (valeur / 1000000.0)).replace(".", ",")
    return ("%g kHz" % (valeur / 1000.0)).replace(".", ",")


def presence_verdict(measures: dict) -> str:
    """Quel dialogue de presence a fonctionne (« reqa », « wupa », « muet »)."""
    measures = measures or {}
    reqa = int(measures.get("reqa_ok") or 0)
    wupa = int(measures.get("wupa_ok") or 0)
    if reqa and wupa:
        return "reqa+wupa"
    if reqa:
        return "reqa"
    if wupa:
        return "wupa"
    return "muet"


#: Error codes -> sentence for the log (the page translates the same codes).
ERROR_TEXT = {
    "no_reader": "le lecteur RC522 ne repond pas (cablage, 3,3 V ou bus SPI)",
    "spi_failed": "aucune vitesse de bus n'a donne de lecture fiable",
    "no_badge": "aucun badge n'a ete pose sur le lecteur",
    "timeout_pose": "aucun badge n'a ete pose a temps",
    "badge_unreadable": "un badge est pose mais son UID n'a pas pu etre lu",
    "timeout_remove": "le badge n'a pas ete retire a temps",
    "timeout_replace": "le badge n'a pas ete repose a temps",
    "cancelled": "mesure annulee",
}


def error_text(code: str) -> str:
    return ERROR_TEXT.get(code, code or "erreur inconnue")
