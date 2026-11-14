"""Player avatars: one small JPEG picture per player card.

Stored as ``avatars/<UID>.jpg`` in the home folder (not in the badge
database: it stays small and readable). The page crops and shrinks the
picture before sending it; the reader screen shows it instead of the
initial, and the full backup saves the folder.
"""

from __future__ import annotations

import os

from .storage import normalize_uid

AVATARS_DIR = "avatars"
MAX_BYTES = 512 * 1024


class AvatarError(ValueError):
    pass


def path(home: str, uid: str) -> str:
    return os.path.join(home, AVATARS_DIR, normalize_uid(uid) + ".jpg")


def save(home: str, uid: str, data: bytes) -> str:
    """Writes the avatar of a player card (JPEG only)."""
    if not data or not data.startswith(b"\xff\xd8\xff"):
        raise AvatarError("image JPEG attendue")
    if len(data) > MAX_BYTES:
        raise AvatarError("image trop grande (512 Ko au plus)")
    target = path(home, uid)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target + ".tmp"
    with open(temporary, "wb") as handle:
        handle.write(data)
    os.replace(temporary, target)
    return target


def load(home: str, uid: str):
    try:
        with open(path(home, uid), "rb") as handle:
            return handle.read()
    except (OSError, ValueError):
        return None


def delete(home: str, uid: str) -> bool:
    try:
        os.remove(path(home, uid))
        return True
    except (OSError, ValueError):
        return False


def versions(home: str) -> dict:
    """{UID: modification time} of the stored avatars (to refresh the pictures)."""
    folder = os.path.join(home, AVATARS_DIR)
    found = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return found
    for name in names:
        if name.lower().endswith(".jpg"):
            try:
                found[name[:-4].upper()] = int(os.path.getmtime(os.path.join(folder, name)))
            except OSError:
                pass
    return found
