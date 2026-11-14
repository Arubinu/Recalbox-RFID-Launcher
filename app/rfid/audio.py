"""Sound of the Recalbox (PulseAudio): the "sound" card mutes it, or not."""

from __future__ import annotations

import os
import subprocess

#: PulseAudio of Recalbox runs as root: its socket is found with this.
ENV = {"XDG_RUNTIME_DIR": "/run/user/0", "HOME": "/recalbox/share/system"}


def _pactl(args, run=None):
    env = dict(os.environ)
    env.update(ENV)
    run = run or subprocess.run
    return run(["pactl"] + list(args), env=env, capture_output=True, text=True, timeout=5)


def toggle_mute(run=None):
    """Mutes or unmutes the Recalbox. Returns True (muted), False (sound
    back) or None (PulseAudio unreachable)."""
    try:
        _pactl(["set-sink-mute", "@DEFAULT_SINK@", "toggle"], run)
        reply = _pactl(["get-sink-mute", "@DEFAULT_SINK@"], run)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (getattr(reply, "stdout", "") or "").lower()
    if "yes" in text:
        return True
    if "no" in text:
        return False
    return None
