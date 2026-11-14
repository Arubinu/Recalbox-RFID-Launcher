"""Reader mode: the reader screen instead of Recalbox's interface (option).

Recalbox's interface is stopped (and waited for: it may take long to quit),
the reader screen (``main.py screen``) is shown, and the games are started
by the service itself with the command Recalbox's interface would run
(``es_command``). When the game ends, the screen comes back.

While a game runs, ``/tmp/es_state.inf`` is written as Recalbox's interface
writes it: the rest of the service (game running, saves...) works the same.

Leaving the mode (option turned off, "unlock" card, service stopped,
uninstalled) closes the screen and starts Recalbox's interface again. Three
crashes of the screen in a row also go back to Recalbox's interface.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time

from . import es_command
from .consts import ES_STATE_FILE
from .frontend_lock import ES_SERVICE, START_TIMEOUT_S, STOP_TIMEOUT_S, frontend_age, frontend_pids, frontend_running

#: RetroArch reads this file last: the quit hotkey and the menu are turned
#: off here while a game started by the reader runs (option).
OVERRIDES = "/recalbox/share/system/configs/retroarch/retroarchcustom.cfg.overrides.cfg"
HOTKEY_BEGIN = "# --- rfid-reader: quit hotkey off (begin) ---"
HOTKEY_END = "# --- rfid-reader: quit hotkey off (end) ---"
HOTKEY_LINES = (
    'input_exit_emulator = "nul"',
    'input_exit_emulator_btn = "nul"',
    'input_exit_emulator_axis = "nul"',
    'input_menu_toggle = "nul"',
    'input_menu_toggle_btn = "nul"',
    'input_menu_toggle_axis = "nul"',
    'input_quit_gamepad_combo = "0"',
    'input_menu_toggle_gamepad_combo = "0"',
)
#: The screen crashing this many times within CRASH_WINDOW_S: back to Recalbox.
MAX_CRASHES = 3
CRASH_WINDOW_S = 120.0
#: Time between a crash of the screen and its restart.
RESTART_DELAY_S = 2.0
#: The system started less than this ago: Recalbox's interface may still be
#: about to start (the service starts before it); it is waited for.
BOOT_WINDOW_S = 240.0
BOOT_WAIT_S = 120.0
#: Recalbox's interface stopped while it starts hangs for a long time and
#: keeps the screen: it is stopped once it has run at least this long.
SETTLE_S = 25.0


def system_uptime() -> float:
    try:
        with open("/proc/uptime", "r") as handle:
            return float(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return BOOT_WINDOW_S  # unknown: not booting


def set_hotkey_block(enabled: bool, path: str = OVERRIDES) -> bool:
    """Adds or removes the reader block of the RetroArch overrides. True if changed."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    lines = text.splitlines()
    kept = []
    inside = False
    for line in lines:
        if line.strip() == HOTKEY_BEGIN:
            inside = True
            continue
        if line.strip() == HOTKEY_END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    if enabled:
        kept += [HOTKEY_BEGIN] + list(HOTKEY_LINES) + [HOTKEY_END]
    result = "\n".join(kept) + ("\n" if kept else "")
    if result == text or (not kept and not text):
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temporary = path + ".rfid-tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(result)
    os.replace(temporary, path)
    return True


def write_state(system: str, rom: str, name: str, playing: bool, path: str = ES_STATE_FILE) -> None:
    """``/tmp/es_state.inf`` as Recalbox's interface writes it."""
    info = es_command.systems().get(system) or {}
    lines = [
        "Version=2.0",
        "Action=%s" % ("rungame" if playing else "endgame"),
        "ActionData=%s" % rom,
        "System=%s" % (info.get("fullname") or system),
        "SystemId=%s" % system,
        "Game=%s" % name,
        "GamePath=%s" % rom,
        "IsFolder=0",
        "State=%s" % ("playing" if playing else "selected"),
    ]
    temporary = path + ".rfid-tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        os.replace(temporary, path)
    except OSError:
        pass


class ReaderMode:
    """Switches between Recalbox's interface and the reader screen, starts the games."""

    def __init__(self, home: str, log, run=None, running=None, popen=None, clock=None, sleep=None,
                 python=None, hotkey_path: str = OVERRIDES, state_path: str = ES_STATE_FILE, uptime=None,
                 age=None, pids=None, kill=None):
        self.home = home
        self._age = age or (frontend_age if running is None else (lambda: None))
        self._pids = pids or (frontend_pids if running is None else (lambda: []))
        self._kill = kill or os.kill
        self._uptime = uptime or system_uptime
        self._restart_at = None
        self.log = log
        self._run = run or (lambda args: subprocess.run(args, stdout=subprocess.DEVNULL,
                                                        stderr=subprocess.DEVNULL, timeout=60))
        self._running = running or frontend_running
        self._popen = popen or subprocess.Popen
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self.python = python or sys.executable
        self.hotkey_path = hotkey_path
        self.state_path = state_path
        #: "recalbox", "switching", "screen" or "game".
        self.state = "recalbox"
        self.wanted = False
        self.no_quit_hotkey = False
        self.screen = None
        self.game = None
        self.game_info = None
        self.crashes = []
        self.lock = threading.Lock()
        self._thread = None

    # ---------------------------------------------------------------- state
    @property
    def active(self) -> bool:
        """The reader screen replaces Recalbox's interface (or will)."""
        return self.state in ("screen", "game", "switching") and self.wanted

    def configure(self, wanted: bool, no_quit_hotkey: bool = False) -> None:
        """Settings changed: enter or leave the mode (in the background)."""
        self.no_quit_hotkey = bool(no_quit_hotkey)
        if bool(wanted) == self.wanted and self.state != "switching":
            if wanted and self.state == "recalbox":
                self._switch(True)
            return
        self.wanted = bool(wanted)
        self._switch(self.wanted)

    def _switch(self, enter: bool) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # the running switch reads self.wanted when it ends
        self.state = "switching"
        self._thread = threading.Thread(target=self._switch_work, args=(enter,), name="rfid-reader-mode",
                                        daemon=True)
        self._thread.start()

    def _switch_work(self, enter: bool) -> None:
        try:
            if enter:
                self.enter()
            else:
                self.leave()
        except Exception as exc:  # noqa: BLE001 - never stops the service
            self._info("Changement de mode impossible : %s" % exc)
        if self.wanted != (self.state in ("screen", "game")):
            # Asked again meanwhile.
            try:
                self.enter() if self.wanted else self.leave()
            except Exception as exc:  # noqa: BLE001
                self._info("Changement de mode impossible : %s" % exc)

    # ------------------------------------------------------------ switching
    def _wait_boot_frontend(self) -> None:
        """At boot, Recalbox's interface starts after the service: wait for it,
        otherwise it would take the screen back a few seconds later."""
        left = BOOT_WINDOW_S - self._uptime()
        if left <= 0 or self._running():
            return
        self._info("Demarrage : attente de l'interface de Recalbox pour la remplacer")
        deadline = self._clock() + min(BOOT_WAIT_S, left)
        while self._clock() < deadline:
            if self._running():
                self._sleep(3.0)  # let it settle before stopping it
                return
            self._sleep(1.0)

    def _wait_settled(self) -> None:
        """Lets Recalbox's interface finish starting before stopping it."""
        deadline = self._clock() + SETTLE_S + 5
        while self._clock() < deadline:
            age = self._age()
            if age is None or age >= SETTLE_S:
                return
            self._sleep(1.0)

    def stop_frontend(self) -> bool:
        self._wait_boot_frontend()
        if not self._running():
            return True
        self._wait_settled()
        self._run([ES_SERVICE, "stop"])
        deadline = self._clock() + STOP_TIMEOUT_S
        while self._clock() < deadline:
            if not self._running():
                return True
            self._sleep(0.5)
        # Still there (stuck): forced to quit, it would keep the screen.
        for sig in (signal.SIGTERM, getattr(signal, "SIGKILL", 9)):
            for pid in self._pids():
                try:
                    self._kill(pid, sig)
                except OSError:
                    pass
            for _ in range(10):
                if not self._running():
                    self._info("Interface de Recalbox bloquee : arretee de force")
                    return True
                self._sleep(0.5)
        return not self._running()

    def start_frontend(self) -> None:
        if self._running():
            return
        self._run([ES_SERVICE, "start"])
        deadline = self._clock() + START_TIMEOUT_S
        while self._clock() < deadline:
            if self._running():
                return
            self._sleep(0.5)
        self._run([ES_SERVICE, "start"])

    def enter(self) -> None:
        with self.lock:
            if self.state in ("screen", "game"):
                return
            self.state = "switching"
        if not self.stop_frontend():
            self._info("L'interface de Recalbox ne s'arrete pas : mode lecteur abandonne")
            self.state = "recalbox"
            self.start_frontend()
            return
        self.start_screen()
        self.state = "screen"
        self._info("Mode lecteur : l'ecran du lecteur remplace l'interface de Recalbox")

    def leave(self) -> None:
        with self.lock:
            self.state = "switching"
        self.stop_screen()
        self._stop_game()
        set_hotkey_block(False, self.hotkey_path)
        self.start_frontend()
        self.state = "recalbox"
        self._info("Mode lecteur quitte : interface de Recalbox relancee")

    # --------------------------------------------------------------- screen
    def start_screen(self) -> None:
        if self.screen is not None and self.screen.poll() is None:
            return
        main = os.path.join(self.home, "app", "main.py")
        env = es_command.launch_env()
        log_path = os.path.join(self.home, "logs", "screen.log")
        try:
            output = open(log_path, "ab")
        except OSError:
            output = subprocess.DEVNULL
        self.screen = self._popen([self.python, main, "screen", "--home", self.home], env=env,
                                  stdout=output, stderr=subprocess.STDOUT, start_new_session=True)

    def stop_screen(self, timeout_s: float = 8.0) -> None:
        process = self.screen
        self.screen = None
        if process is None or process.poll() is not None:
            return
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=timeout_s)
        except Exception:  # noqa: BLE001 - stuck: killed
            try:
                process.kill()
                process.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- games
    def launch(self, system: str, rom: str, name: str = "") -> bool:
        """Starts a game in place of the screen. False when not in the mode."""
        if self.state != "screen" or not self.wanted:
            return False
        try:
            argv = es_command.build(system, rom)
        except es_command.CommandError as exc:
            self._info("Lancement impossible : %s" % exc)
            return False
        self.state = "game"
        self.stop_screen()
        if self.no_quit_hotkey:
            set_hotkey_block(True, self.hotkey_path)
        self.game_info = (system, rom, name or os.path.splitext(os.path.basename(rom))[0])
        write_state(system, rom, self.game_info[2], True, self.state_path)
        try:
            self.game = self._popen(argv, env=es_command.launch_env(), stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            self._info("Lancement impossible : %s" % exc)
            self._game_over()
            return False
        self._info("Mode lecteur : lancement de %s" % es_command.describe(argv))
        return True

    def _stop_game(self) -> None:
        process = self.game
        if process is not None and process.poll() is None:
            try:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    process.kill()
                except Exception:  # noqa: BLE001
                    pass
        self.game = None

    def _game_over(self) -> None:
        self.game = None
        set_hotkey_block(False, self.hotkey_path)
        if self.game_info is not None:
            write_state(self.game_info[0], self.game_info[1], self.game_info[2], False, self.state_path)
        self.game_info = None
        if self.wanted:
            self.start_screen()
            self.state = "screen"

    def step(self) -> None:
        """To call often: a game that ended, a screen that crashed."""
        if self.state == "game" and self.game is not None and self.game.poll() is not None:
            self._info("Mode lecteur : fin du jeu, retour a l'ecran du lecteur")
            self._game_over()
            return
        if self.state == "screen" and self.screen is None and self._restart_at is not None:
            if self._clock() >= self._restart_at:
                self._restart_at = None
                self.start_screen()
            return
        if self.state == "screen" and self.screen is not None and self.screen.poll() is not None:
            self.screen = None
            if self._running():
                # Recalbox's interface came back and took the display: stopped again.
                self._info("L'interface de Recalbox est revenue : elle est arretee de nouveau")
                self.state = "recalbox"
                self._switch(True)
                return
            now = self._clock()
            self.crashes = [t for t in self.crashes if now - t < CRASH_WINDOW_S] + [now]
            if len(self.crashes) >= MAX_CRASHES:
                self._info("L'ecran du lecteur s'arrete sans cesse : retour a l'interface de Recalbox")
                self.wanted = False
                self.crashes = []
                self._switch(False)
                return
            self._info("Ecran du lecteur arrete : relance")
            self._restart_at = now + RESTART_DELAY_S

    def shutdown(self) -> None:
        """The service stops: Recalbox's interface comes back."""
        if self.state != "recalbox":
            self.wanted = False
            self.leave()

    def _info(self, text: str) -> None:
        if self.log:
            self.log.info(text)
