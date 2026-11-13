"""Optional password, asked after the 3 s press on the button.

The button proves that someone stands next to the Recalbox. In a family, that
someone may be the child whose play time is limited: a password, set from the
page once connected, is then asked after the press as well.

Only a salted PBKDF2-SHA256 hash is stored (``access.json`` in the install
folder); the password itself is never written anywhere.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets

ACCESS_FILENAME = "access.json"
ITERATIONS = 120000
MIN_LENGTH = 4
MAX_LENGTH = 128


class AccessError(Exception):
    """Refused password change."""


def _path(home: str) -> str:
    return os.path.join(home, ACCESS_FILENAME)


def _read(home: str) -> dict:
    try:
        with open(_path(home), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def has_password(home: str) -> bool:
    entry = _read(home).get("password")
    return isinstance(entry, dict) and bool(entry.get("hash"))


def _digest(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def check(home: str, password: str) -> bool:
    """True if ``password`` is right (always True when there is none)."""
    entry = _read(home).get("password")
    if not isinstance(entry, dict) or not entry.get("hash"):
        return True
    try:
        salt = bytes.fromhex(entry["salt"])
        expected = bytes.fromhex(entry["hash"])
        iterations = int(entry.get("iterations") or ITERATIONS)
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(_digest(str(password or ""), salt, iterations), expected)


def set_password(home: str, password: str) -> None:
    password = str(password or "")
    if len(password) < MIN_LENGTH:
        raise AccessError("mot de passe trop court (%d caracteres au moins)" % MIN_LENGTH)
    if len(password) > MAX_LENGTH:
        raise AccessError("mot de passe trop long")
    salt = secrets.token_bytes(16)
    data = _read(home)
    data["password"] = {"salt": salt.hex(), "hash": _digest(password, salt, ITERATIONS).hex(),
                        "iterations": ITERATIONS}
    _write(home, data)


def clear_password(home: str) -> None:
    data = _read(home)
    data.pop("password", None)
    _write(home, data)


def _write(home: str, data: dict) -> None:
    path = _path(home)
    temporary = path + ".tmp"
    os.makedirs(home, exist_ok=True)
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(temporary, path)
