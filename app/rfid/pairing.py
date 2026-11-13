"""Pairing confirmed physically.

Principle (suggested by the user, and it is the right security model):

1. the web page drops a pairing **request** - a single one at a time, valid
   for ``PAIRING_WINDOW_S`` seconds;
2. on the Recalbox, the service waits for a **long press** on the physical
   button (``CONFIRM_HOLD_S`` seconds): that is the proof of presence;
3. the service writes a **grant** carrying the exact id of the request;
4. the page exchanges this grant for the token, only once.

The tricky part is the race between two requests: a grant given for request
A can never validate a request B, because the id and the deadline of the
request are copied into the grant. A press started before the request was
created (or while it was expiring) does not count: it must start
``MIN_GAP_S`` after the creation of the request it validates.
"""

from __future__ import annotations

import json
import os
import secrets
import time

# Validity of a pairing request (seconds).
PAIRING_WINDOW_S = 30.0
# Continuous press required to confirm (seconds).
CONFIRM_HOLD_S = 3.0
# The press must start after the request was created (anti-replay margin).
MIN_GAP_S = 0.25

REQUEST_FILENAME = "pair-pending.json"
GRANT_FILENAME = "pair-grant.json"


class PairingError(Exception):
    """Request refused (already pending, or delay expired)."""


# ---------------------------------------------------------------------------
# Fichiers d'etat
# ---------------------------------------------------------------------------
# Pairing states must not be written to the Samba share: it is reachable
# as a guest, so any computer on the network could drop a grant there and
# authorize itself without pressing the button. They are therefore kept in
# a private folder (tmpfs), outside the share. ``RFID_STATE_DIR`` forces a path.
STATE_DIR_ENV = "RFID_STATE_DIR"
DEFAULT_STATE_DIR = "/tmp/rfid-launcher-pairing"


def state_dir(home: str) -> str:
    """Folder of the pairing states: private, and never the Samba share."""
    forced = os.environ.get(STATE_DIR_ENV, "").strip()
    if forced:
        try:
            os.makedirs(forced, exist_ok=True)
        except OSError:
            pass
        return forced
    # Comparison made on a normalized form: the same function is used on
    # Windows (tests, simulation mode) and on the Recalbox.
    normalise = os.path.abspath(str(home or "")).replace("\\", "/")
    if "/recalbox/share" in normalise:
        try:
            os.makedirs(DEFAULT_STATE_DIR, exist_ok=True)
            try:
                # Private folder: the service and the agent run as root.
                os.chmod(DEFAULT_STATE_DIR, 0o700)
            except OSError:
                pass
            probe = os.path.join(DEFAULT_STATE_DIR, ".probe")
            with open(probe, "w", encoding="ascii") as handle:
                handle.write("ok")
            os.remove(probe)
            return DEFAULT_STATE_DIR
        except OSError:
            pass
    return home


def request_path(home: str) -> str:
    return os.path.join(state_dir(home), REQUEST_FILENAME)


def grant_path(home: str) -> str:
    return os.path.join(state_dir(home), GRANT_FILENAME)


def _read(path: str):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _write(path: str, data: dict) -> None:
    """Atomic write: temporary file, then replacement."""
    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Demande
# ---------------------------------------------------------------------------
def pending(home: str):
    """Pending request, or ``None`` (an expired request is deleted)."""
    data = _read(request_path(home))
    if not data:
        return None
    try:
        until = float(data.get("until") or 0)
    except (TypeError, ValueError):
        _remove(request_path(home))
        return None
    if until <= time.time():
        _remove(request_path(home))
        return None
    return data


def create_request(home: str, source: str = "") -> dict:
    """Creates the request; raises ``PairingError`` if another one is pending."""
    current = pending(home)
    if current:
        remaining = max(0.0, float(current.get("until", 0)) - time.time())
        raise PairingError(
            "une demande d'appairage est deja en attente (%.0f s)" % remaining
        )
    now = time.time()
    request = {
        "id": secrets.token_hex(4).upper(),
        "created": now,
        "until": now + PAIRING_WINDOW_S,
        "source": str(source or ""),
    }
    # A previous grant must never be usable for this request.
    _remove(grant_path(home))
    _write(request_path(home), request)
    return request


def cancel(home: str) -> None:
    """Drops the request and the grant, if any."""
    _remove(request_path(home))
    _remove(grant_path(home))


# ---------------------------------------------------------------------------
# Grant (service side, after a long press)
# ---------------------------------------------------------------------------
def grant(home: str, request: dict, press_started: float) -> bool:
    """Saves the button grant for *this* request.

    Refuses a press that started before the request was created: otherwise,
    someone keeping a finger on the button could validate a request that
    arrived meanwhile.
    """
    if not request:
        return False
    try:
        created = float(request.get("created") or 0)
    except (TypeError, ValueError):
        return False
    if press_started < created + MIN_GAP_S:
        return False
    _write(grant_path(home), {
        "request_id": str(request.get("id") or ""),
        "request_until": float(request.get("until") or 0),
        "press_started": press_started,
        "granted": time.time(),
    })
    return True


def take_grant(home: str, request_id: str) -> bool:
    """Checks and consumes the grant (only once).

    The grant is only valid for the given id and as long as the matching
    request has not expired: a later request therefore cannot be validated by
    the press meant for the previous one.
    """
    data = _read(grant_path(home))
    if not data:
        return False
    _remove(grant_path(home))
    if str(data.get("request_id") or "") != str(request_id or ""):
        return False
    try:
        still_valid = float(data.get("request_until") or 0) > time.time()
    except (TypeError, ValueError):
        return False
    return still_valid
