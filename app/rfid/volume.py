"""The volume of the Recalbox (every sound: games, music, cartridge sounds).

Recalbox keeps it in ``audio.volume`` (recalbox.conf, 0-100) and applies it
to the PulseAudio output; its interface changes both. The reader screen does
the same from its START + SELECT menu: the output at once, recalbox.conf
when the menu closes (it is read again at the next boot and by Recalbox's
interface).
"""

from __future__ import annotations

import os
import re
import subprocess

from .audio import ENV
from .frontend_lock import RECALBOX_CONF, read_values, write_values

KEY = "audio.volume"
STEP = 5


def _pactl(args, run=None):
    env = dict(os.environ)
    env.update(ENV)
    return (run or subprocess.run)(["pactl"] + list(args), env=env, capture_output=True, text=True, timeout=5)


def read_saved(conf: str = RECALBOX_CONF):
    try:
        with open(conf, "r", encoding="utf-8") as handle:
            value = read_values(handle.read(), [KEY])[KEY]
        return max(0, min(100, int(float(value))))
    except (OSError, TypeError, ValueError):
        return None


def current(run=None, conf: str = RECALBOX_CONF) -> int:
    """The volume now (percent): the sound output, else recalbox.conf, else 100."""
    try:
        reply = _pactl(["get-sink-volume", "@DEFAULT_SINK@"], run)
        found = re.search(r"(\d+)%", reply.stdout or "")
        if reply.returncode == 0 and found:
            return max(0, min(100, int(found.group(1))))
    except (OSError, subprocess.SubprocessError):
        pass
    saved = read_saved(conf)
    return 100 if saved is None else saved


def apply(percent: int, run=None) -> bool:
    """Sets the sound output (at once)."""
    percent = max(0, min(100, int(percent)))
    try:
        return _pactl(["set-sink-volume", "@DEFAULT_SINK@", "%d%%" % percent], run).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def save(percent: int, conf: str = RECALBOX_CONF) -> bool:
    """Writes audio.volume in recalbox.conf (when it changed)."""
    percent = max(0, min(100, int(percent)))
    try:
        with open(conf, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    if read_values(text, [KEY])[KEY] == str(percent):
        return False
    temporary = conf + ".rfid-tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(write_values(text, {KEY: str(percent)}))
    os.replace(temporary, conf)
    return True
