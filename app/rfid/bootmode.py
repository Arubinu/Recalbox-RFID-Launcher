"""The reader screen straight at boot, without Recalbox's interface first.

Recalbox starts its interface (S31emulationstation) only when
``system.es.atstartup`` is not 0 in recalbox.conf, and it is the interface
that starts the "(permanent)" userscripts, so our service. With the reader
screen on:

* ``system.es.atstartup=0`` (the value before is kept in ``es-atstartup.json``
  and given back when the reader screen is left, before the interface is
  started again);
* a block in ``/recalbox/share/system/custom.sh`` (run by S99custom at the end
  of the boot) starts the service and the page agent instead. If the service
  is not running two minutes later, the block brings the interface back on its
  own (``atstartup=1``, S31 start): a broken install never leaves a black TV.
"""

from __future__ import annotations

import json
import os

from .frontend_lock import RECALBOX_CONF, read_values, write_values

KEY = "system.es.atstartup"
SAVED_FILENAME = "es-atstartup.json"
CUSTOM_SH = "/recalbox/share/system/custom.sh"
USERSCRIPTS = "/recalbox/share/userscripts"
SCRIPTS = ("recalbox-rfid(permanent).py3", "recalbox-rfid-agent(permanent).py3")
BEGIN = "# --- rfid-reader: reader screen at boot (begin) ---"
END = "# --- rfid-reader: reader screen at boot (end) ---"
#: Seconds after the boot when the block checks that the service runs.
GUARD_S = 120


def boot_lines(userscripts: str = USERSCRIPTS, conf: str = RECALBOX_CONF) -> list:
    scripts = " ".join('"%s/%s"' % (userscripts, name) for name in SCRIPTS)
    return [
        'if [ "$1" = "start" ]; then',
        "  # Recalbox's interface does not start (system.es.atstartup=0): the",
        "  # reader service and its page agent start here instead.",
        "  export HOME=/recalbox/share/system",
        "  for script in %s; do" % scripts,
        '    [ -f "$script" ] && python3 "$script" >/dev/null 2>&1 &',
        "  done",
        "  # Safety: no reader service two minutes later, the interface comes back.",
        "  ( sleep %d" % GUARD_S,
        "    if ! ps | grep -v grep | grep -q 'main.py daemon'; then",
        "      sed -i 's/^%s=0$/%s=1/' %s" % (KEY, KEY, conf),
        "      /etc/init.d/S31emulationstation start",
        "    fi ) >/dev/null 2>&1 &",
        "fi",
    ]


def set_custom_block(lines, path: str = CUSTOM_SH) -> bool:
    """Writes (lines) or removes (None) our block of custom.sh. True if changed."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    kept, inside, found = [], False, False
    for line in text.splitlines():
        if line.strip() == BEGIN:
            inside = found = True
            continue
        if line.strip() == END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    if lines:
        if not kept:
            kept = ["#!/bin/bash"]
        kept += [BEGIN] + list(lines) + [END]
    elif not found:
        return False
    elif all(not line.strip() or line.startswith("#!") for line in kept):
        # Nothing of the user's: the file goes away (it did not exist before).
        os.remove(path)
        return True
    result = "\n".join(kept) + "\n"
    if result == text:
        return False
    if not os.path.isdir(os.path.dirname(path) or "."):
        return False  # not a Recalbox
    temporary = path + ".rfid-tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(result)
    os.replace(temporary, path)
    return True


def _read(conf: str):
    try:
        with open(conf, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def _write(conf: str, text: str, value) -> None:
    temporary = conf + ".rfid-tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(write_values(text, {KEY: value}))
    os.replace(temporary, conf)


def skip_interface(home: str, conf: str = RECALBOX_CONF, custom: str = CUSTOM_SH,
                   userscripts: str = USERSCRIPTS) -> bool:
    """The next boots go straight to the reader screen. True if something changed.

    Call it while Recalbox's interface is stopped: it saves recalbox.conf when
    it quits.
    """
    text = _read(conf)
    if text is None:
        return False
    changed = set_custom_block(boot_lines(userscripts, conf), custom)
    current = read_values(text, [KEY])[KEY]
    if current == "0":
        return changed
    saved = os.path.join(home, SAVED_FILENAME)
    if not os.path.exists(saved):
        with open(saved, "w", encoding="utf-8") as handle:
            json.dump({"value": current}, handle)
    _write(conf, text, "0")
    return True


def restore_interface(home: str, conf: str = RECALBOX_CONF, custom: str = CUSTOM_SH) -> bool:
    """Recalbox's interface starts at boot again (as before). True if something changed."""
    changed = set_custom_block(None, custom)
    saved_path = os.path.join(home, SAVED_FILENAME)
    try:
        with open(saved_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
    except (OSError, ValueError):
        return changed  # never changed by the reader: left as the user set it
    text = _read(conf)
    if text is not None:
        value = saved.get("value") if isinstance(saved, dict) else None
        if read_values(text, [KEY])[KEY] != value:
            _write(conf, text, value)
            changed = True
    try:
        os.remove(saved_path)
    except OSError:
        pass
    return changed


def skipping(conf: str = RECALBOX_CONF) -> bool:
    """True when Recalbox's interface does not start at boot."""
    text = _read(conf)
    return text is not None and read_values(text, [KEY])[KEY] == "0"
