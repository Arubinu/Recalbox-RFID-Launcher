"""How many controllers RetroArch games accept (option "one per active player").

A block of the RetroArch overrides file (read last) sets ``input_max_users``.
Recalbox writes 8 there itself; without the block, every controller plays.
Stand-alone emulators ignore it.
"""

from __future__ import annotations

import os

OVERRIDES = "/recalbox/share/system/configs/retroarch/retroarchcustom.cfg.overrides.cfg"
BEGIN = "# --- rfid-reader: controllers allowed (begin) ---"
END = "# --- rfid-reader: controllers allowed (end) ---"


def set_block(lines, begin: str, end: str, path: str) -> bool:
    """Writes (lines) or removes (None) a marked block of a config file. True if changed."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    kept = []
    inside = False
    for line in text.splitlines():
        if line.strip() == begin:
            inside = True
            continue
        if line.strip() == end:
            inside = False
            continue
        if not inside:
            kept.append(line)
    if lines:
        kept += [begin] + list(lines) + [end]
    result = "\n".join(kept) + ("\n" if kept else "")
    if result == text or (not kept and not text):
        return False
    if not os.path.isdir(os.path.dirname(path) or "."):
        return False  # not a Recalbox (tests, computer)
    temporary = path + ".rfid-tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(result)
    os.replace(temporary, path)
    return True


def set_max_users(count, path: str = OVERRIDES) -> bool:
    """``count`` controllers in RetroArch games (None: all of them). True if changed."""
    lines = None if not count else ['input_max_users = "%d"' % max(1, int(count))]
    try:
        return set_block(lines, BEGIN, END, path)
    except OSError:
        return False
