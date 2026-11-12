"""Reglage automatique du lecteur.

Le service mesure le materiel (vitesse SPI supportee, duree d'une lecture,
comportement du badge, latence de retrait) puis en deduit trois reglages :

* ``rfid.spi_speed_hz`` — la vitesse de bus la plus rapide qui fonctionne
  reellement sur ce Raspberry Pi et ce module ;
* ``rfid.poll_interval_ms`` — la cadence de lecture, calee sur la duree reelle
  d'une lecture (inutile d'interroger plus vite que le lecteur ne repond) ;
* ``rfid.rearm_absent_ms`` — le delai d'absence, cale sur la latence mesuree
  quand on retire le badge.

Ce module ne contient que des calculs : aucune lecture du materiel, aucun acces
disque. Il est donc testable sur un PC, et le service garde la main sur le
lecteur.
"""

from __future__ import annotations

#: Vitesses essayees, de la plus rapide a la plus lente. Le RC522 accepte
#: jusqu'a 10 MHz, mais au-dela de 4 MHz beaucoup de modules clones deviennent
#: instables : on garde la premiere qui repond parfaitement.
SPEEDS = (8000000, 4000000, 2000000, 1000000, 500000)

#: Vitesse de repli si la mesure se trompe (la valeur livree d'origine).
SPEED_FALLBACK = 1000000

#: Etapes de la sequence, dans l'ordre. Sert au compteur de la page.
STEPS = ("speed", "read", "presence", "remove", "reinsert")

#: Valeurs d'origine, utilisees par le bouton « Reinitialiser ».
DEFAULTS = {
    "rfid.spi_speed_hz": str(SPEED_FALLBACK),
    "rfid.poll_interval_ms": "150",
    "rfid.rearm_absent_ms": "1200",
}

#: Bornes des reglages calcules.
POLL_MIN_MS = 60
POLL_MAX_MS = 500
ABSENCE_MIN_MS = 1000
ABSENCE_MAX_MS = 4000

#: Marge ajoutee a la duree d'une lecture pour fixer la cadence.
POLL_MARGIN_MS = 30

#: Facteur de securite applique a la latence de retrait mesuree.
ABSENCE_FACTOR = 1.5


def clamp(valeur: float, mini: float, maxi: float) -> float:
    return max(mini, min(maxi, valeur))


def poll_interval_ms(read_ms) -> int:
    """Cadence de lecture deduite de la duree mesuree d'une lecture."""
    try:
        duree = float(read_ms or 0)
    except (TypeError, ValueError):
        duree = 0.0
    return int(round(clamp(duree + POLL_MARGIN_MS, POLL_MIN_MS, POLL_MAX_MS)))


def absence_ms(measured_ms) -> int:
    """Delai d'absence deduit de la latence de retrait mesuree."""
    try:
        latence = float(measured_ms or 0)
    except (TypeError, ValueError):
        latence = 0.0
    return int(round(clamp(latence * ABSENCE_FACTOR, ABSENCE_MIN_MS, ABSENCE_MAX_MS)))


def settings_from(measures: dict) -> dict:
    """Traduit les mesures en valeurs de configuration (section.cle -> texte)."""
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
    """« 4 MHz », « 500 kHz » : lisible sur la page comme dans le journal."""
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


#: Codes d'erreur -> phrase pour le journal (la page traduit les memes codes).
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
