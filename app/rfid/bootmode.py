"""The reader screen straight at boot, without Recalbox's interface first.

Recalbox starts its interface (S31emulationstation) only when
``system.es.atstartup`` is not 0 in recalbox.conf, and it is the interface
that starts the "(permanent)" userscripts, so our service. With the reader
screen on:

* ``system.es.atstartup=0`` (the value before is kept in ``es-atstartup.json``
  and given back when the reader screen is left, before the interface is
  started again);
* our own script ``boot.sh`` (in the service folder) starts the service and the
  page agent; ``/recalbox/share/system/custom.sh``, the user hook that
  S99custom runs with "start" at the end of the boot and "stop" at the start
  of the shutdown, only gets one commented line calling it. If the service is
  not running two minutes after the boot, boot.sh brings the interface back
  on its own (``atstartup=1``, S31 start); and if boot.sh is missing, the line
  itself does: a broken install never leaves a black TV.
"""

from __future__ import annotations

import json
import os

from .frontend_lock import RECALBOX_CONF, read_values, write_values

KEY = "system.es.atstartup"
SAVED_FILENAME = "es-atstartup.json"
BOOT_FILENAME = "boot.sh"
CUSTOM_SH = "/recalbox/share/system/custom.sh"
USERSCRIPTS = "/recalbox/share/userscripts"
SCRIPTS = ("recalbox-rfid(permanent).py3", "recalbox-rfid-agent(permanent).py3")
#: The comment before our line of custom.sh (it identifies the line too).
COMMENT = ("# Recalbox RFID Launcher: shows the reader screen at boot instead of the Recalbox "
           "interface (removed when the reader screen is turned off).")
#: The block written by the first version, removed when found.
OLD_BEGIN = "# --- rfid-reader: reader screen at boot (begin) ---"
OLD_END = "# --- rfid-reader: reader screen at boot (end) ---"
#: Seconds after the boot when boot.sh checks that the service runs.
GUARD_S = 120
#: Written by boot.sh when the Recalbox stops (custom.sh stop runs first):
#: the service stopping then is not leaving the reader screen. In RAM (/tmp).
STOPPING_FLAG = "/tmp/rfid-system-stopping"


def _back_to_interface(conf: str) -> str:
    return "sed -i 's/^%s=0$/%s=1/' %s; /etc/init.d/S31emulationstation start" % (KEY, KEY, conf)


def boot_lines(userscripts: str = USERSCRIPTS, conf: str = RECALBOX_CONF) -> list:
    """The content of boot.sh (run with "start" or "stop")."""
    scripts = " ".join('"%s/%s"' % (userscripts, name) for name in SCRIPTS)
    return [
        "#!/bin/sh",
        "# Recalbox RFID Launcher: called by /recalbox/share/system/custom.sh while",
        "# the reader screen is on. Written by the service: do not edit.",
        'if [ "$1" = "start" ]; then',
        "  # Recalbox's interface does not start (system.es.atstartup=0): the",
        "  # reader service and its page agent start here instead.",
        "  export HOME=/recalbox/share/system",
        "  for script in %s; do" % scripts,
        '    [ -f "$script" ] && python3 "$script" >/dev/null 2>&1 &',
        "  done",
        "  # Safety: no reader service two minutes later, the interface comes back.",
        "  ( sleep %d" % GUARD_S,
        "    if ! pgrep -f 'main.py daemon' >/dev/null; then",
        "      %s" % _back_to_interface(conf),
        "    fi ) >/dev/null 2>&1 &",
        "fi",
        "# The Recalbox stops: the reader screen stays for the next boot.",
        'if [ "$1" = "stop" ]; then',
        "  touch %s" % STOPPING_FLAG,
        "fi",
    ]


def custom_line(boot: str, conf: str = RECALBOX_CONF) -> str:
    """Our line of custom.sh: runs boot.sh, or brings the interface back without it."""
    return ('if [ -f "%s" ]; then sh "%s" "$1"; elif [ "$1" = "start" ]; then %s; fi'
            % (boot, boot, _back_to_interface(conf)))


def set_custom_line(boot, path: str = CUSTOM_SH, conf: str = RECALBOX_CONF) -> bool:
    """Adds (boot: path of boot.sh) or removes (None) our line of custom.sh. True if changed.

    The user's own lines stay; the file is created when missing, and removed
    again when nothing else is left in it.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    target = boot or ""
    kept, inside, found = [], False, False
    for line in text.splitlines():
        if line.strip() == OLD_BEGIN:
            inside = found = True
            continue
        if line.strip() == OLD_END:
            inside = False
            continue
        if inside:
            continue
        if line.strip() == COMMENT or ("rfid" in line and BOOT_FILENAME in line and "S31emulationstation" in line):
            found = True
            continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    if boot:
        if not kept:
            kept = ["#!/bin/bash"]
        kept += ["", COMMENT, custom_line(target, conf)]
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


def write_boot_script(home: str, userscripts: str = USERSCRIPTS, conf: str = RECALBOX_CONF) -> str:
    """Writes boot.sh in the service folder; returns its path."""
    path = os.path.join(home, BOOT_FILENAME)
    content = "\n".join(boot_lines(userscripts, conf)) + "\n"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            if handle.read() == content:
                return path
    except OSError:
        pass
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.replace(temporary, path)
    return path


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
    boot = write_boot_script(home, userscripts, conf)
    changed = set_custom_line(boot, custom, conf)
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
    changed = set_custom_line(None, custom, conf)
    try:
        os.remove(os.path.join(home, BOOT_FILENAME))
    except OSError:
        pass
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


def mark_stopping(path: str = STOPPING_FLAG) -> None:
    """The Recalbox is about to turn off or restart (our own power menu, card...)."""
    try:
        with open(path, "w", encoding="ascii") as handle:
            handle.write("1\n")
    except OSError:
        pass


def system_stopping(path: str = STOPPING_FLAG) -> bool:
    return os.path.exists(path)
