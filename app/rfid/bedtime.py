"""Bedtime: no games between two hours (settings time.curfew_from / curfew_to).

The window may cross midnight (21:00 - 07:00). The unlock card ignores it.
"""

from __future__ import annotations

import re
import time

#: Minutes before bedtime when the players are warned.
WARN_MIN = 5


def parse(clock: str):
    """Minutes after midnight of "HH:MM", or None (empty or invalid)."""
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", str(clock or ""))
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        return None
    return hours * 60 + minutes


def window(cfg):
    """(start, end) in minutes after midnight, or None (bedtime off)."""
    if cfg is None:
        return None
    start = parse(cfg.get("time", "curfew_from", ""))
    end = parse(cfg.get("time", "curfew_to", ""))
    if start is None or end is None or start == end:
        return None
    return start, end


def _minute(now: float) -> float:
    moment = time.localtime(now)
    return moment.tm_hour * 60 + moment.tm_min + moment.tm_sec / 60.0


def active(span, now: float) -> bool:
    if span is None:
        return False
    start, end = span
    minute = _minute(now)
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def minutes_to_start(span, now: float):
    """Minutes until bedtime starts (0 when it is bedtime), or None."""
    if span is None:
        return None
    if active(span, now):
        return 0.0
    return (span[0] - _minute(now)) % 1440


def clock_text(minutes: int) -> str:
    return "%02d:%02d" % (minutes // 60, minutes % 60)
