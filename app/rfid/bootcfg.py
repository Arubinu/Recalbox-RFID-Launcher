"""Raspberry Pi boot configuration (``/boot``), for the optional hardware.

The programmable LEDs need the second SPI bus: ``dtoverlay=spi1-1cs`` must be
in the boot configuration, then the Recalbox rebooted. Same rules as
install.sh for the main SPI bus:

* ``/boot`` is read-only on Recalbox 9/10: it is remounted read-write for the
  change, then set back to read-only;
* the line goes into ``recalbox-user-config.txt`` and into the global section
  of ``config.txt`` (Recalbox 10 may ignore the user file).
"""

from __future__ import annotations

import os
import shutil
import subprocess

BOOT_FILES = ("/boot/recalbox-user-config.txt", "/boot/config.txt")

#: Second SPI bus with one chip select (data on GPIO20 = physical pin 38).
SPI1_OVERLAY = "dtoverlay=spi1-1cs"

COMMENT = "# Second SPI bus for the status LEDs (added by Recalbox RFID Launcher)"


def has_line(line: str, files=BOOT_FILES) -> bool:
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                if any(raw.strip() == line for raw in handle):
                    return True
        except OSError:
            continue
    return False


def _remount(mode: str) -> bool:
    try:
        return subprocess.run(["mount", "-o", "remount," + mode, "/boot"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _writable(path: str) -> bool:
    probe = path + ".rfid-test"
    try:
        with open(probe, "w", encoding="ascii") as handle:
            handle.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def _insert_global(lines: list, line: str) -> list:
    """Adds ``line`` after the first dtparam/dtoverlay line (global section)."""
    for index, raw in enumerate(lines):
        if raw.strip().startswith("["):
            break
        if raw.strip().startswith(("dtparam=", "dtoverlay=")):
            return lines[:index + 1] + [line] + lines[index + 1:]
    return lines + [line]


def ensure_line(line: str = SPI1_OVERLAY, files=BOOT_FILES, remount=_remount) -> dict:
    """Writes ``line`` in the boot files where it is missing.

    Returns ``{"changed": [...files], "errors": [...]}``. A reboot is needed
    when ``changed`` is not empty.
    """
    result = {"changed": [], "errors": []}
    targets = []
    for path in files:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
        if any(raw.strip() == line for raw in content.splitlines()):
            continue
        targets.append((path, content))
    if not targets:
        return result
    remounted = False
    if not _writable(targets[0][0]):
        remounted = remount("rw")
    try:
        for path, content in targets:
            # The install backup (without our lines) is kept: uninstall.sh
            # relies on it to know which lines it added.
            if not os.path.exists(path + ".bak-rfid-launcher"):
                try:
                    shutil.copy2(path, path + ".bak-rfid-launcher")
                except OSError:
                    pass
            lines = content.split("\n")
            if os.path.basename(path) == "config.txt":
                lines = _insert_global(lines, line)
            else:
                while lines and not lines[-1].strip():
                    lines.pop()
                lines += ["", COMMENT, line, ""]
            try:
                with open(path + ".rfid-new", "w", encoding="utf-8", newline="\n") as handle:
                    handle.write("\n".join(lines))
                os.replace(path + ".rfid-new", path)
                result["changed"].append(path)
            except OSError as exc:
                result["errors"].append("%s : %s" % (path, exc))
    finally:
        if remounted:
            remount("ro")
    return result
