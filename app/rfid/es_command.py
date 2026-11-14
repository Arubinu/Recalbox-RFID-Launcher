"""The command Recalbox's interface runs to start a game, rebuilt by the reader.

Used by the reader screen (games started without Recalbox's interface), and
checked against the real command each time Recalbox's interface starts a
game. Checked on Recalbox 10.1 (``systemlist.xml``)::

    python /usr/bin/emulatorlauncher.pyc %CONTROLLERSCONFIG% -system %SYSTEM%
        -rom %ROM% -emulator %EMULATOR% -core %CORE% -ratio %RATIO%
        -videobackend %VIDEO_BACKEND% %NETPLAY% %CRT%

followed by ``-rotation``, ``-resolution``, ``-disabledsoftpatching`` and
``-systemtype``. Shaders, smoothing, auto save and the per-game overrides are
not on the command line: the launcher reads them itself in recalbox.conf.

* controllers: SDL (the same library as the interface, through pygame) gives
  the GUID, the name and the number of axes, hats and buttons; udev gives the
  device and physical paths; the player order comes from
  ``emulationstation.padN`` in recalbox.conf;
* emulator and core: the game (gamelist.xml), then the console
  (recalbox.conf), then the default core of systemlist.xml.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import struct
import subprocess
import sys

try:
    from xml.etree import ElementTree
except ImportError:  # pragma: no cover
    ElementTree = None

from .library import ROMS_DIRS

LAUNCHER = "/usr/bin/emulatorlauncher.pyc"
SYSTEMLIST = "/recalbox/share_init/system/.emulationstation/systemlist.xml"
RECALBOX_CONF = "/recalbox/share/system/recalbox.conf"
INPUT_SYS = "/sys/class/input"
#: Environment of the interface when it starts a game (Raspberry Pi).
LAUNCH_ENV = {
    "HOME": "/recalbox/share/system",
    "SDL_VIDEO_GL_DRIVER": "/usr/lib/libGLESv2.so",
    "SDL_VIDEO_EGL_DRIVER": "/usr/lib/libEGL.so",
    "SDL_NOMOUSE": "1",
    "XDG_RUNTIME_DIR": "/run/user/0",
}

#: Asks SDL (pygame) for the controllers, as the interface sees them.
_PROBE = r"""
import json, os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame
pygame.joystick.init()
pads = []
for index in range(pygame.joystick.get_count()):
    pad = pygame.joystick.Joystick(index)
    pads.append({"index": index, "guid": pad.get_guid(), "name": pad.get_name(),
                 "axes": pad.get_numaxes(), "hats": pad.get_numhats(), "buttons": pad.get_numbuttons()})
print(json.dumps(pads))
"""


class CommandError(Exception):
    pass


def read_conf(path: str = RECALBOX_CONF) -> dict:
    """Active ``key=value`` lines of recalbox.conf."""
    values = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith((";", "#")) or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


# ------------------------------------------------------------------ systems
_systems_cache = {}


def systems(path: str = SYSTEMLIST) -> dict:
    """{name: {"type", "cores": [{"emulator", "core", "priority", "videobackend"}]}}."""
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _systems_cache.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    found = {}
    if ElementTree is not None:
        try:
            root = ElementTree.parse(path).getroot()
        except (OSError, ElementTree.ParseError):
            root = None
        for node in (root.iter("system") if root is not None else ()):
            name = node.get("name") or ""
            properties = node.find("properties")
            cores = []
            for emulator in node.iter("emulator"):
                for core in emulator.iter("core"):
                    try:
                        priority = int(core.get("priority") or 99)
                    except ValueError:
                        priority = 99
                    cores.append({"emulator": emulator.get("name") or "", "core": core.get("name") or "",
                                  "priority": priority, "videobackend": core.get("video.backend") or "default"})
            if name:
                found[name] = {"type": (properties.get("type") if properties is not None else "") or "",
                               "fullname": node.get("fullname") or name, "cores": cores}
    _systems_cache[path] = (stamp, found)
    return found


def game_meta(system: str, rom: str, roms_dirs=ROMS_DIRS) -> dict:
    """Per-game settings of gamelist.xml (emulator, core, ratio, rotation...)."""
    if ElementTree is None:
        return {}
    for base in roms_dirs:
        folder = os.path.join(base, system)
        path = os.path.join(folder, "gamelist.xml")
        if not os.path.isfile(path):
            continue
        try:
            root = ElementTree.parse(path).getroot()
        except (OSError, ElementTree.ParseError):
            continue
        for node in root.iter("game"):
            relative = (node.findtext("path") or "").strip()
            if relative and os.path.normpath(os.path.join(folder, relative)) == os.path.normpath(rom):
                return {child.tag: (child.text or "").strip() for child in node}
    return {}


def choose_core(system: str, rom: str, conf: dict, info: dict, meta: dict) -> dict:
    """Emulator, core and video backend: the game, the console, the default."""
    cores = info.get("cores") or []
    if not cores:
        raise CommandError("console inconnue de Recalbox : %s" % system)
    emulator = meta.get("emulator") or conf.get(system + ".emulator") or ""
    core = meta.get("core") or conf.get(system + ".core") or ""
    for item in cores:
        if item["emulator"] == emulator and item["core"] == core:
            return item
    if emulator or core:
        for item in sorted(cores, key=lambda c: c["priority"]):
            if (not emulator or item["emulator"] == emulator) and (not core or item["core"] == core):
                return item
    return sorted(cores, key=lambda c: c["priority"])[0]


# -------------------------------------------------------------- controllers
def probe_pads(timeout: float = 20.0) -> list:
    """Controllers as SDL sees them (index, guid, name, axes, hats, buttons)."""
    try:
        result = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,
                                timeout=timeout)
        lines = [line for line in result.stdout.splitlines() if line.startswith("[")]
        return json.loads(lines[-1]) if lines else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def _udev_path(device: str) -> str:
    try:
        result = subprocess.run(["udevadm", "info", "-q", "property", "-n", device],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in result.stdout.splitlines():
        if line.startswith("ID_PATH="):
            return line.split("=", 1)[1].strip()
    return ""


def input_devices(sys_dir: str = INPUT_SYS, udev_path=_udev_path) -> list:
    """Joystick event devices in order: [{"name", "devicepath", "physicalpath"}]."""
    found = []
    try:
        entries = os.listdir(sys_dir)
    except OSError:
        return found
    for entry in sorted((e for e in entries if re.match(r"^event\d+$", e)), key=lambda e: int(e[5:])):
        base = os.path.join(sys_dir, entry, "device")
        try:
            with open(os.path.join(base, "name"), "r", encoding="utf-8", errors="replace") as handle:
                name = handle.read().strip()
        except OSError:
            continue
        # Joysticks only: they have buttons in the gamepad range (BTN_JOYSTICK/BTN_GAMEPAD).
        if not _is_joystick(base):
            continue
        device = "/dev/input/" + entry
        found.append({"name": name, "devicepath": device, "physicalpath": udev_path(device)})
    return found


#: Size of the words of /sys/.../capabilities (an "unsigned long": 32 bits on a Pi 3).
WORD_BITS = struct.calcsize("L") * 8


def _is_joystick(base: str, word_bits: int = None) -> bool:
    try:
        with open(os.path.join(base, "capabilities", "key"), "r", encoding="ascii") as handle:
            words = handle.read().split()
    except OSError:
        return False
    if not words:
        return False
    bits = 0
    for word in words:
        bits = (bits << (word_bits or WORD_BITS)) | int(word, 16)
    # BTN_JOYSTICK 0x120..0x12f and BTN_GAMEPAD 0x130..0x13e
    return any(bits >> code & 1 for code in range(0x120, 0x13f))


def controllers(conf: dict, pads: list, devices: list) -> list:
    """The %CONTROLLERSCONFIG% arguments, players in the interface order."""
    # Device paths: the n-th SDL pad of a name is the n-th device of that name.
    seen = {}
    for pad in pads:
        same = [d for d in devices if d["name"] == pad["name"]]
        rank = seen.get(pad["name"], 0)
        seen[pad["name"]] = rank + 1
        device = same[rank] if rank < len(same) else {}
        pad["devicepath"] = device.get("devicepath", "")
        pad["physicalpath"] = device.get("physicalpath", "")
    ordered = []
    free = list(pads)
    slot = 0
    while ("emulationstation.pad%d" % slot) in conf:
        wanted = conf.get("emulationstation.pad%d" % slot, "")
        guid, _, name = wanted.partition(":")
        path = conf.get("emulationstation.pad%d.path" % slot, "")
        match = None
        for pad in free:
            if path and pad.get("physicalpath") == path and pad["guid"] == guid:
                match = pad
                break
        if match is None:
            for pad in free:
                if pad["guid"] == guid and (not name or pad["name"] == name):
                    match = pad
                    break
        if match is not None:
            ordered.append(match)
            free.remove(match)
        slot += 1
    ordered.extend(free)
    args = []
    for number, pad in enumerate(ordered, start=1):
        prefix = "-p%d" % number
        args += [prefix + "index", str(pad["index"]), prefix + "guid", pad["guid"], prefix + "name", pad["name"],
                 prefix + "nbaxes", str(pad["axes"]), prefix + "nbhats", str(pad["hats"]),
                 prefix + "nbbuttons", str(pad["buttons"]), prefix + "devicepath", pad.get("devicepath", ""),
                 prefix + "physicalpath", pad.get("physicalpath", "")]
    return args


# ------------------------------------------------------------------ command
def build(system: str, rom: str, conf: dict = None, info: dict = None, meta: dict = None,
          pads=None, devices=None) -> list:
    """argv of the launcher for ``rom``, as Recalbox's interface would run it."""
    conf = read_conf() if conf is None else conf
    if info is None:
        info = systems().get(system)
    if not info:
        raise CommandError("console inconnue de Recalbox : %s" % system)
    meta = game_meta(system, rom) if meta is None else meta
    chosen = choose_core(system, rom, conf, info, meta)
    pads = probe_pads() if pads is None else pads
    devices = input_devices() if devices is None else devices
    ratio = meta.get("ratio") or conf.get(system + ".ratio") or conf.get("global.ratio") or "auto"
    resolution = conf.get(system + ".videomode") or conf.get("global.videomode") or "default"
    argv = ["python", LAUNCHER] + controllers(conf, [dict(p) for p in pads], devices)
    argv += ["-system", system, "-rom", rom, "-emulator", chosen["emulator"], "-core", chosen["core"],
             "-ratio", ratio, "-videobackend", chosen["videobackend"],
             "-rotation", meta.get("rotation") or "0", "-resolution", resolution]
    if meta.get("softpatching", "").lower() not in ("1", "true", "auto", "patched"):
        argv.append("-disabledsoftpatching")
    argv += ["-systemtype", info.get("type") or "console"]
    return argv


def launch_env(conf: dict = None, base: dict = None) -> dict:
    conf = read_conf() if conf is None else conf
    env = dict(os.environ if base is None else base)
    env.update(LAUNCH_ENV)
    language = conf.get("system.language") or "en_US"
    env["LANG"] = language + ".UTF-8"
    return env


# ------------------------------------------------------------------ checking
def options(argv) -> dict:
    """{"-option": "value" or True} of a launcher command (argv[2:])."""
    found = {}
    items = list(argv)[2:]
    index = 0
    while index < len(items):
        key = items[index]
        if index + 1 < len(items) and not items[index + 1].startswith("-"):
            found[key] = items[index + 1]
            index += 2
        else:
            found[key] = True
            index += 1
    return found


def compare(actual, ours) -> list:
    """Differences between the interface's command and ours: [(option, theirs, ours)]."""
    theirs, mine = options(actual), options(ours)
    return [(key, theirs.get(key), mine.get(key)) for key in sorted(set(theirs) | set(mine))
            if theirs.get(key) != mine.get(key)]


def describe(argv) -> str:
    return " ".join(shlex.quote(str(part)) for part in argv)
