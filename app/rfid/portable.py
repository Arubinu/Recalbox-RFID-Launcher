"""Portable cards: the game is written in the badge memory.

A badge paired on one Recalbox only works there: the pairing lives in its
``tags.json``. Once the game is written in the badge itself, any Recalbox
running this program starts it, provided the game is installed there too
(same console folder, same file name).

Format (UTF-8, at the start of the user memory, ended by a zero byte)::

    RL1|<system>|<path relative to the system folder>

For example ``RL1|snes|Super Mario World (USA).sfc``. Short on purpose: an
Ultralight badge offers 48 bytes, a MIFARE Classic or an NTAG213 more (96 are
used at most). No NDEF record: phones ignore it, which is fine.
"""

from __future__ import annotations

from .library import find_rom, relative_to_system

MAGIC = "RL1"
MAX_BYTES = 96


class PortableError(Exception):
    """The game cannot be written in a badge."""


def encode(system: str, path: str) -> bytes:
    """Bytes to write in the badge for a game."""
    system = str(system or "").strip()
    relative = relative_to_system(system, path)
    if not system or not relative:
        raise PortableError("jeu incomplet")
    if "|" in system or "|" in relative:
        raise PortableError("le caractere '|' n'est pas accepte")
    data = ("%s|%s|%s" % (MAGIC, system, relative)).encode("utf-8") + b"\x00"
    if len(data) > MAX_BYTES:
        raise PortableError("chemin du jeu trop long pour un badge (%d octets, %d au plus)"
                            % (len(data), MAX_BYTES))
    return data


def decode(data):
    """(system, relative path) written in a badge, or None."""
    if not data:
        return None
    raw = bytes(data).split(b"\x00", 1)[0]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    parts = text.split("|")
    if len(parts) != 3 or parts[0] != MAGIC or not parts[1] or not parts[2]:
        return None
    if "/" in parts[1] or ".." in parts[2].split("/"):
        return None
    return parts[1], parts[2]


def entry_from(data, roms_dirs=None):
    """Store-like entry for the game of a portable card, or None.

    ``missing`` is set when the game is not installed on this Recalbox.
    """
    found = decode(data)
    if found is None:
        return None
    system, relative = found
    path = find_rom(system, relative) if roms_dirs is None else find_rom(system, relative, roms_dirs)
    name = relative.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return {
        "kind": "game",
        "system": system,
        "game": relative,
        "path": path,
        "name": name,
        "limit_min": None,
        "missing": not path,
    }
