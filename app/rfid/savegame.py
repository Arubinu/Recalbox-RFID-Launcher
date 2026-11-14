"""Saves the game before the reader quits it, and resumes it at the next launch.

Optional ("Settings > Save the game before quitting", off by default). Only
for the games run by RetroArch (most consoles), through its network commands
(UDP port 55355, enabled by Recalbox), checked on Recalbox 10.1 (RetroArch
1.22):

* ``GET_STATUS`` answers ``GET_STATUS PLAYING <core>,<game>,crc32=...``: the
  game name is the file name of its save states;
* ``SAVE_FILES`` writes the in-game save (battery memory), ``SAVE_STATE``
  writes a save state in the current slot (about half a second);
* ``LOAD_STATE_SLOT -1`` loads ``<game>.state.auto``: the "auto" save state,
  the very file of the Recalbox "auto save/load" option.

The save state is copied as the "auto" one, then the slot RetroArch wrote is
put back as it was: the player's own save states never change. Stand-alone
emulators do not answer ``GET_STATUS``: nothing is done, the game is quit as
before.
"""

from __future__ import annotations

import glob
import os
import re
import socket
import threading
import time

RETROARCH_PORT = 55355
#: Written by Recalbox at each RetroArch launch: holds the save state folder
#: of the running game.
RETROARCH_CFG = "/recalbox/share/system/configs/retroarch/retroarchcustom.cfg"
AUTO_SUFFIX = ".state.auto"
#: Save states kept in memory while RetroArch writes (to put the slot back).
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
#: Time given to RetroArch to write the save state.
SAVE_TIMEOUT_S = 5.0
#: Time given to a game to start before it is resumed.
RESUME_TIMEOUT_S = 90.0

_STATUS = re.compile(r"^GET_STATUS\s+(\w+)\s+([^,]*),(.*?)(?:,crc32=\w+)?\s*$")


def parse_status(reply: str):
    """{"core", "name"} of a GET_STATUS reply while a game runs, else None.

    A game is PLAYING, or PAUSED while RetroArch's own menu is open.
    """
    match = _STATUS.match((reply or "").strip())
    if not match or match.group(1) not in ("PLAYING", "PAUSED"):
        return None
    name = match.group(3).strip()
    if not name:
        return None
    return {"core": match.group(2).strip(), "name": name}


def read_retroarch_cfg(path: str = RETROARCH_CFG) -> dict:
    values = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "=" not in line or line.lstrip().startswith("#"):
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return values


def _is_slot(path: str, name: str) -> bool:
    """``<name>.state`` or ``<name>.state<N>`` (never the auto one, no thumbnail)."""
    base = os.path.basename(path)
    prefix = name + ".state"
    return base.startswith(prefix) and base[len(prefix):].isdigit() or base == prefix


class GameSaver:
    """Save on quit and resume, through RetroArch network commands."""

    def __init__(self, port: int = RETROARCH_PORT, host: str = "127.0.0.1", log=None,
                 query=None, cfg_path: str = RETROARCH_CFG, sleep=None, clock=None, show=None):
        self.port = int(port)
        self.host = host
        self.log = log
        self._query = query or self._udp
        self.cfg_path = cfg_path
        self._sleep = sleep or time.sleep
        self._clock = clock or time.time
        #: Shows a message on the game screen (osd.ScreenMessages.say).
        self.show = show
        self._resuming = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------ commands
    def _udp(self, command: str, wait: float):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(wait)
            # Connected: with no RetroArch listening, the reply fails at once.
            sock.connect((self.host, self.port))
            sock.send(command.encode("utf-8"))
            if wait <= 0:
                return None
            return sock.recv(4096).decode("utf-8", "replace")
        except OSError:
            return None
        finally:
            sock.close()

    def status(self):
        return parse_status(self._query("GET_STATUS", 0.6))

    def state_folder(self) -> str:
        folder = read_retroarch_cfg(self.cfg_path).get("savestate_directory", "")
        return folder if folder and os.path.isdir(folder) else ""

    def _folders(self, folder: str):
        """The folder and its sub-folders (RetroArch may sort the saves)."""
        found = [folder]
        try:
            for entry in sorted(os.listdir(folder)):
                path = os.path.join(folder, entry)
                if os.path.isdir(path):
                    found.append(path)
        except OSError:
            pass
        return found

    def _files(self, folder: str, name: str):
        """Save state files of the game (slots and their thumbnails, not the auto one)."""
        files = []
        for place in self._folders(folder):
            for path in glob.glob(os.path.join(glob.escape(place), glob.escape(name) + ".state*")):
                base = os.path.basename(path)
                if base.startswith(name + AUTO_SUFFIX):
                    continue
                files.append(path)
        return files

    @staticmethod
    def _stamp(path: str):
        try:
            info = os.stat(path)
        except OSError:
            return None
        return info.st_mtime, info.st_size

    # ---------------------------------------------------------------- save
    def save(self, timeout_s: float = SAVE_TIMEOUT_S) -> str:
        """Saves the running game as its "auto" save state.

        Returns the path written, or "" (no RetroArch game, nothing written).
        """
        status = self.status()
        if status is None:
            return ""
        name = status["name"]
        folder = self.state_folder()
        if not folder:
            self._info("Dossier des sauvegardes RetroArch introuvable : partie non sauvegardee")
            return ""
        before = {}
        total = 0
        for path in self._files(folder, name):
            try:
                with open(path, "rb") as handle:
                    before[path] = handle.read()
            except OSError:
                continue
            total += len(before[path])
            if total > MAX_SNAPSHOT_BYTES:
                self._info("Sauvegardes de %s trop lourdes : partie non sauvegardee" % name)
                return ""
        stamps = {path: self._stamp(path) for path in before}
        self._query("SAVE_FILES", 0.5)
        self._query("SAVE_STATE", 0)
        written = ""
        try:
            written = self._wait_written(folder, name, stamps, timeout_s)
            if not written:
                self._info("RetroArch n'a pas ecrit de sauvegarde pour %s" % name)
                return ""
            auto = os.path.join(os.path.dirname(written), name + AUTO_SUFFIX)
            with open(written, "rb") as handle:
                data = handle.read()
            temporary = auto + ".rfid-tmp"
            with open(temporary, "wb") as handle:
                handle.write(data)
            os.replace(temporary, auto)
            self._info("Partie sauvegardee avant de quitter : %s" % auto)
            return auto
        finally:
            self._put_back(folder, name, before)

    def _wait_written(self, folder: str, name: str, stamps: dict, timeout_s: float) -> str:
        deadline = self._clock() + timeout_s
        candidate = ""
        last = None
        while self._clock() < deadline:
            self._sleep(0.15)
            if not candidate:
                for path in self._files(folder, name):
                    if _is_slot(path, name) and self._stamp(path) != stamps.get(path):
                        candidate = path
                        break
                continue
            # Written: wait until its size stops changing.
            stamp = self._stamp(candidate)
            if stamp is not None and stamp == last:
                return candidate
            last = stamp
        return candidate if candidate and last is not None else ""

    def _put_back(self, folder: str, name: str, before: dict) -> None:
        """The slot RetroArch wrote (and its thumbnail) is put back as it was."""
        for path in self._files(folder, name):
            try:
                if path not in before:
                    os.remove(path)
                    continue
                with open(path, "rb") as handle:
                    same = handle.read() == before[path]
                if not same:
                    with open(path, "wb") as handle:
                        handle.write(before[path])
            except OSError as exc:
                self._info("Sauvegarde %s non remise : %s" % (path, exc))

    # -------------------------------------------------------------- resume
    def auto_state(self, name: str) -> str:
        folder = self.state_folder()
        if not folder:
            return ""
        for place in self._folders(folder):
            path = os.path.join(place, name + AUTO_SUFFIX)
            if os.path.isfile(path):
                return path
        return ""

    def resume(self, expected: str = "", timeout_s: float = RESUME_TIMEOUT_S) -> bool:
        """Waits for the game to run, then loads its "auto" save state."""
        deadline = self._clock() + timeout_s
        status = None
        while self._clock() < deadline:
            status = self.status()
            if status is not None and (not expected or status["name"] == expected):
                break
            status = None
            self._sleep(1.0)
        if status is None:
            return False
        if read_retroarch_cfg(self.cfg_path).get("savestate_auto_load") == "true":
            return False  # Recalbox's own option: RetroArch loaded it already
        if not self.auto_state(status["name"]):
            return False
        # The core answers before the first frames: let the game start.
        self._sleep(1.5)
        self._query("LOAD_STATE_SLOT -1", 1.0)
        if self.show is not None:
            try:
                self.show("game_resumed")
            except Exception:  # noqa: BLE001 - message only
                pass
        self._info("Partie reprise : %s" % status["name"])
        return True

    def resume_later(self, expected: str = "") -> bool:
        """resume() in the background (one at a time)."""
        with self._lock:
            if self._resuming:
                return False
            self._resuming = True

        def work():
            try:
                self.resume(expected)
            except Exception as exc:  # noqa: BLE001 - never stops the service
                self._info("Reprise de la partie impossible : %s" % exc)
            finally:
                with self._lock:
                    self._resuming = False

        threading.Thread(target=work, name="rfid-resume", daemon=True).start()
        return True

    def _info(self, text: str) -> None:
        if self.log:
            self.log.info(text)
