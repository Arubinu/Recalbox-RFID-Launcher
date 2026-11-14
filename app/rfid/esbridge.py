"""Dialogue with the Recalbox frontend (EmulationStation).

Two official mechanisms are used, without changing the OS:

1. **Reading** ``/tmp/es_state.inf``: the frontend writes there, on every
   event, the currently selected system and game. This is what lets the push
   button know which game to pair the badge with.

2. **Starting** a game: since Recalbox 9, the frontend listens on UDP port
   1337 and expects a text frame ::

       START|<system id>|<game path relative to the system folder>

   packet = a single UDP datagram, without a trailing newline. The frontend
   then resolves the game exactly as if it had been started from the menu
   (splash screen, saves, retroachievements, etc.).
"""

from __future__ import annotations

import os
import signal
import socket
import time
from dataclasses import dataclass

from .consts import ES_STATE_FILE, ES_UDP_HOST, ES_UDP_PORT


@dataclass
class Target:
    """Game selected in the Recalbox interface."""

    system: str
    game: str
    name: str = ""
    path: str = ""

    def describe(self) -> str:
        return "%s / %s" % (self.system, self.name or self.game)


def read_state(path: str = ES_STATE_FILE):
    """Reads ``es_state.inf`` and returns a dictionary (None if missing)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return None

    state = {}
    for line in lines:
        line = line.strip("\r\n")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


def game_is_running(state) -> bool:
    """True if a game is running (according to the state file)."""
    return bool(state) and state.get("State") == "playing"


def relative_game_key(system: str, absolute_path: str) -> str:
    """Converts an absolute ROM path into the key expected by the UDP command.

    The frontend looks the game up by its path relative to the system folder,
    extension included, ignoring case. For example
    ``/recalbox/share/roms/snes/Super Mario World.smc`` -> ``Super Mario World.smc``.
    """
    if not absolute_path:
        return ""
    normalized = absolute_path.replace("\\", "/")
    candidates = [
        "/recalbox/share/roms/%s/" % system,
        "/recalbox/share/roms/%s" % system,
    ]
    for prefix in candidates[:-1]:
        if normalized.startswith(prefix):
            return normalized[len(prefix):]

    marker = "/roms/"
    index = normalized.find(marker)
    if index >= 0:
        remainder = normalized[index + len(marker):]
        parts = remainder.split("/")
        if len(parts) > 1:
            return "/".join(parts[1:])
        return parts[0]
    return os.path.basename(normalized)


#: Keys the Recalbox frontend may use depending on the version.
CLES_SYSTEME = ("SystemId", "System", "SystemName")
CLES_CHEMIN = ("GamePath", "Path", "File", "RomPath")


def state_snapshot(state, limite: int = 120) -> dict:
    """Readable summary of ``es_state.inf`` (for status.json and the logs)."""
    if not state:
        return {}
    resume = {}
    for cle, valeur in state.items():
        texte = str(valeur or "")
        if len(texte) > limite:
            texte = texte[: limite - 1] + "…"
        resume[cle] = texte
    return resume


def describe_state(state) -> str:
    """Explains why no game was found (log message)."""
    if not state:
        return "/tmp/es_state.inf absent ou vide"
    cles = ("Action", "State", "Type", "IsFolder", "SystemId", "System", "Game", "GamePath")
    presentes = [cle for cle in cles if cle in state]
    if not presentes:
        return "etat illisible (aucune cle connue) : %s" % sorted(state.keys())[:8]
    return ", ".join("%s=%r" % (cle, state.get(cle)) for cle in presentes)


#: Folders where Recalbox stores games (writable part, then the read-only base).
ROMS_DIRS = ("/recalbox/share/roms", "/recalbox/share_init/roms")


def resolve_rom_path(system: str, game: str) -> str:
    """Full path of a game, for entries that do not have one.

    The frontend identifies a game by its full path: it is rebuilt here
    (no check is possible on a PC, the first candidate is returned then).
    """
    if not system or not game:
        return ""
    if game.startswith("/"):
        return game
    # POSIX paths: the service runs on Linux, even when the tests run on
    # Windows.
    candidats = ["%s/%s/%s" % (base, system, game) for base in ROMS_DIRS]
    for candidat in candidats:
        if os.path.isfile(candidat):
            return candidat
    return candidats[0]


def current_target(state, allow_running: bool = False) -> "Target | None":
    """Returns the selected game, or None if no game is selected.

    ``allow_running`` is used for the association: the frontend may leave
    ``State=playing`` (or show a game page) while no game is running; the
    displayed game is then accepted. For badge launches, the filter is kept
    (no interruption of a game).
    """
    if not state:
        return None
    system = ""
    for cle in CLES_SYSTEME:
        system = (state.get(cle) or "").strip()
        if system:
            break
    absolute = ""
    for cle in CLES_CHEMIN:
        absolute = (state.get(cle) or "").strip()
        if absolute:
            break
    if not system or not absolute:
        return None
    if state.get("IsFolder") == "1":
        return None
    if str(state.get("Type") or "").strip().lower() in ("folder", "system", "empty", "none"):
        return None
    if not allow_running:
        if game_is_running(state):
            return None
        if state.get("State") == "demo":
            return None
    game = relative_game_key(system, absolute)
    if not game:
        return None
    return Target(system=system, game=game, name=(state.get("Game") or "").strip(), path=absolute)


#: Frontend events that blank the state file while the selection stays the same
#: (screensaver): the last selected game is then still the right one.
IDLE_ACTIONS = ("sleep", "wakeup")


def last_target_path() -> str:
    """File holding the last selected game (tmpfs, cleared at boot)."""
    import tempfile

    return os.environ.get("RFID_LAST_TARGET") or os.path.join(
        tempfile.gettempdir(), "rfid-launcher-last-target.json")


def remember_target(target, path: str = None) -> None:
    """Keeps the selected game: the screensaver erases it from the state file."""
    import json

    path = path or last_target_path()
    try:
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump({"system": target.system, "game": target.game, "name": target.name,
                       "path": target.path}, handle)
        os.replace(temporary, path)
    except OSError:
        pass


def forget_target(path: str = None) -> None:
    """No game is selected any more (reader screen): the last one is forgotten."""
    try:
        os.remove(path or last_target_path())
    except OSError:
        pass


def last_target(path: str = None):
    import json

    try:
        with open(path or last_target_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("system") and data.get("game"):
            return Target(system=data["system"], game=data["game"], name=data.get("name", ""),
                          path=data.get("path", ""))
    except (OSError, ValueError, AttributeError):
        pass
    return None


def selected_target(state, allow_running: bool = False):
    """(game, remembered): the selected game, or the last one during the screensaver."""
    target = current_target(state, allow_running=allow_running)
    if target is not None:
        remember_target(target)
        return target, False
    if state is None:
        idle = True                       # no state file at all
    else:
        empty = not any((state.get(key) or "").strip() for key in CLES_CHEMIN)
        idle = empty and str(state.get("Action") or "").lower() in IDLE_ACTIONS
    if idle:
        remembered = last_target()
        if remembered is not None:
            return remembered, True
    return None, False


#: Emulator processes that may be stopped (never EmulationStation).
EMULATEURS = (
    "retroarch",
    "emulatorlauncher",
    "dolphin",
    "ppsspp",
    "mupen64plus",
    "scummvm",
    "dosbox",
    "amiberry",
    "flycast",
    "pcsx",
    "duckstation",
    "yabasanshiro",
    "mednafen",
    "hatari",
    "vice",
    "fs-uae",
)


#: Process folder (replaceable in the tests).
PROC_DIR = "/proc"

#: Signals used to stop an emulator (missing on Windows).
SIG_TERM = getattr(signal, "SIGTERM", 15)
SIG_KILL = getattr(signal, "SIGKILL", 9)

#: Program never to stop: the frontend itself.
JAMAIS_ARRETER = ("emulationstation", "emulationstation.sh")


def _cmdline(pid: str, proc_dir: str = PROC_DIR) -> str:
    try:
        with open(os.path.join(proc_dir, str(pid), "cmdline"), "rb") as handle:
            brut = handle.read()
    except OSError:
        return ""
    return brut.decode("utf-8", "replace").replace("\x00", " ").strip()


def _programmes(ligne: str) -> list:
    """Program names of a command line (argv[0] and the script, if any).

    Only file names are compared: looking for "vice" anywhere in the line
    would stop unrelated system processes (packages, services).
    """
    morceaux = ligne.split()
    return [os.path.basename(morceau).lower() for morceau in morceaux[:3]]


def _est_emulateur(noms, ligne: str, rom_path: str) -> bool:
    if rom_path and rom_path in ligne:
        return True
    for nom in noms:
        if nom in JAMAIS_ARRETER:
            return False
        if nom in EMULATEURS:
            return True
        base = nom.split(".")[0]
        if base in EMULATEURS:
            return True
    return False


def emulator_pids(rom_path: str = "", proc_dir: str = PROC_DIR):
    """PIDs of the running emulation processes (never ES, never us)."""
    pids = []
    propre = os.getpid()
    try:
        entrees = os.listdir(proc_dir)
    except OSError:
        return pids
    for entree in entrees:
        if not entree.isdigit():
            continue
        pid = int(entree)
        if pid == propre:
            continue
        ligne = _cmdline(entree, proc_dir)
        if not ligne:
            continue
        if _est_emulateur(_programmes(ligne), ligne, rom_path):
            pids.append(pid)
    return pids


#: Recalbox's launcher: it waits for the emulator, then gives the screen and
#: the sound back to the menu. It is never signalled while its emulator runs.
LAUNCHERS = ("emulatorlauncher",)

#: RetroArch network commands (enabled by Recalbox).
RETROARCH_PORT = 55355


def _is_launcher(pid, proc_dir: str = PROC_DIR) -> bool:
    return any(name.split(".")[0] in LAUNCHERS for name in _programmes(_cmdline(str(pid), proc_dir)))


def _parent(pid, proc_dir: str = PROC_DIR) -> int:
    try:
        with open(os.path.join(proc_dir, str(pid), "stat"), "r", encoding="utf-8", errors="replace") as handle:
            data = handle.read()
        return int(data.rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        return 0


def _children(parents, proc_dir: str = PROC_DIR) -> list:
    """Processes started by ``parents`` (the emulator of a launcher)."""
    wanted = set(int(pid) for pid in parents)
    found = []
    try:
        entries = os.listdir(proc_dir)
    except OSError:
        return found
    for entry in entries:
        if entry.isdigit() and int(entry) not in wanted and _parent(entry, proc_dir) in wanted:
            found.append(int(entry))
    return found


def quit_retroarch(port: int = RETROARCH_PORT, host: str = "127.0.0.1", sleep=time.sleep) -> bool:
    """Asks RetroArch to quit, like its hotkey. True if a RetroArch game answered.

    Twice when needed: Recalbox may ask for a second press to quit.
    """
    def ask(command: bytes, wait: float):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(wait)
            sock.connect((host, int(port)))
            sock.send(command)
            return sock.recv(512).decode("utf-8", "replace") if wait > 0 else ""
        except OSError:
            return None
        finally:
            sock.close()

    def running() -> bool:
        reply = ask(b"GET_STATUS", 0.6) or ""
        return " PLAYING " in reply or " PAUSED " in reply

    if not running():
        return False
    ask(b"QUIT", 0)
    sleep(1.0)
    if running():
        ask(b"QUIT", 0)
    return True


def reset_retroarch(port: int = RETROARCH_PORT, host: str = "127.0.0.1") -> bool:
    """Restarts the RetroArch game in place (like the reset button of a
    console): the emulator keeps running. True if a RetroArch game answered."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(0.6)
        sock.connect((host, int(port)))
        sock.send(b"GET_STATUS")
        reply = sock.recv(512).decode("utf-8", "replace")
        if " PLAYING " not in reply and " PAUSED " not in reply:
            return False
        sock.send(b"RESET")
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _kill(pid: int, sig: int) -> None:
    """Signal sending point (replaced in the tests)."""
    os.kill(pid, sig)


class EsLauncher:
    """Sends the launch command to the frontend."""

    def __init__(self, host: str = ES_UDP_HOST, port: int = ES_UDP_PORT, log=None):
        self.host = host
        self.port = int(port)
        self.log = log
        #: Clean exit of a RetroArch game (replaced in the tests).
        self.quit_command = quit_retroarch
        #: Restart of a RetroArch game in place (replaced in the tests).
        self.reset_command = reset_retroarch
        #: Reader mode (reader_mode.ReaderMode): the games are started by the
        #: service itself while Recalbox's interface is stopped.
        self.reader = None

    @staticmethod
    def build_payload(system: str, game: str) -> bytes:
        """Builds the ``START|system|reference`` frame (file system bytes).

        ``reference`` is the **full** path of the game as the frontend knows it
        (it publishes it in its state file). Since Recalbox 10, the file name
        alone is no longer enough.
        """
        system = str(system)
        game = str(game)
        if not system or not game:
            raise ValueError("systeme ou jeu vide")
        if "|" in system or "|" in game:
            raise ValueError(
                "le caractere '|' n'est pas accepte dans le nom d'un jeu (trame UDP)"
            )
        return b"START|" + os.fsencode(system) + b"|" + os.fsencode(game)

    def game_running(self, rom_path: str = "") -> bool:
        """True if an emulator is running (whatever the frontend state)."""
        return bool(emulator_pids(rom_path))

    def stop_game(self, rom_path: str = "", timeout_s: float = 8.0, proc_dir: str = PROC_DIR,
                  graceful_s: float = 6.0) -> bool:
        """Stops the running game, the way its own menu would.

        The frontend offers no network command to quit a game. In order:

        1. a RetroArch game is asked to quit (network command, like its
           hotkey): it frees the screen and the sound itself;
        2. otherwise the emulator is terminated (SIGTERM) -- never Recalbox's
           launcher, which then returns by itself;
        3. what still runs is killed (SIGKILL).

        Terminating the launcher at the same time as the emulator gave the
        screen and the sound back to the menu while the emulator still held
        them: on a Raspberry Pi 3, that froze the sound driver, then the
        whole console.
        """
        if not emulator_pids(rom_path, proc_dir):
            return False
        asked = False
        if self.quit_command is not None:
            try:
                asked = bool(self.quit_command())
            except Exception:  # noqa: BLE001 - the signals below still work
                asked = False
        if asked and self._wait_gone(rom_path, proc_dir, graceful_s):
            if self.log:
                self.log.info("Jeu RetroArch quitte proprement")
            return True
        cibles = emulator_pids(rom_path, proc_dir)
        launchers = [pid for pid in cibles if _is_launcher(pid, proc_dir)]
        emulators = [pid for pid in cibles if pid not in launchers]
        # A stand-alone emulator missing from the list: the launcher's child.
        for pid in _children(launchers, proc_dir):
            if pid not in emulators:
                emulators.append(pid)
        for pid in emulators or launchers:
            try:
                _kill(pid, SIG_TERM)
            except OSError:
                continue
        if self._wait_gone(rom_path, proc_dir, timeout_s):
            if self.log:
                self.log.info("Emulateur arrete (%d processus)" % len(emulators or launchers))
            return True
        for pid in emulator_pids(rom_path, proc_dir):
            try:
                _kill(pid, SIG_KILL)
            except OSError:
                continue
        if self.log:
            self.log.warning("Emulateur force a s'arreter (SIGKILL)")
        return True

    @staticmethod
    def _wait_gone(rom_path: str, proc_dir: str, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not emulator_pids(rom_path, proc_dir):
                return True
            time.sleep(0.2)
        return False

    def start_game(self, system: str, game: str) -> bool:
        """Sends the command; True if the datagram left (or the game started, in reader mode)."""
        reader = self.reader
        if reader is not None and reader.wanted:
            return reader.launch(system, resolve_rom_path(system, game))
        try:
            payload = self.build_payload(system, game)
        except ValueError as exc:
            if self.log:
                self.log.error("Lancement impossible : %s" % exc)
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.settimeout(1.0)
                sock.sendto(payload, (self.host, self.port))
            finally:
                sock.close()
        except OSError as exc:
            if self.log:
                self.log.error(
                    "Commande de lancement non envoyee (%s:%s) : %s" % (self.host, self.port, exc)
                )
            return False
        if self.log:
            self.log.info("Commande envoyee : START|%s|%s" % (system, game))
        return True


def supports_start_command(binary: str = "/usr/bin/emulationstation", chunk_size: int = 1 << 20) -> bool:
    """Detects support for the UDP command in the frontend binary.

    Recalbox 9 introduced the "UDPCommand" thread; the error message it writes
    to the log is present in the binary. This check lets the installer warn
    the user about a version that is too old.
    """
    needle = b"Wrong network command"
    try:
        with open(binary, "rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    return False
                if needle in chunk:
                    return True
    except OSError:
        return False
