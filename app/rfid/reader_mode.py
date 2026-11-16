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
#: The game shown by the reader screen before it starts, and the answer of
#: the controller (in /tmp: RAM).
LAUNCH_FILE = "/tmp/rfid-screen-launch.json"
ANSWER_FILE = "/tmp/rfid-screen-answer.json"
#: How long the game is shown before it starts (option "show the game").
PREVIEW_S = 2.0
#: A game waiting for the controller is given up after this.
CONFIRM_TIMEOUT_S = 120.0
#: Time between a crash of the screen and its restart.
RESTART_DELAY_S = 2.0
#: Back from a game: seconds of black before the fade (the TV syncing again).
AFTER_GAME_HOLD_S = 3.0
#: Written by ``main.py restart`` (an update, the page): the service that
#: stops leaves the reader screen to the next one instead of starting
#: Recalbox's interface again. RAM; older than this, ignored.
HANDOVER_FILE = "/tmp/rfid-screen-handover"
HANDOVER_MAX_AGE_S = 120.0


def ask_handover(path: str = HANDOVER_FILE, wall=None) -> None:
    try:
        with open(path, "w", encoding="ascii") as handle:
            handle.write("%f\n" % (wall or time.time)())
    except OSError:
        pass


def handover_asked(path: str = HANDOVER_FILE, wall=None, take: bool = False) -> bool:
    """A restart is under way (``take``: the flag is used up)."""
    try:
        with open(path, "r", encoding="ascii") as handle:
            at = float(handle.read().strip() or 0)
    except (OSError, ValueError):
        return False
    if take:
        try:
            os.remove(path)
        except OSError:
            pass
    return 0 <= (wall or time.time)() - at <= HANDOVER_MAX_AGE_S


def recover_frontend(path: str = HANDOVER_FILE, run=None) -> bool:
    """The restart failed after the reader screen was left: Recalbox's
    interface comes back (never a black screen)."""
    if not handover_asked(path, take=True):
        return False
    (run or (lambda args: subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          timeout=60)))([ES_SERVICE, "start"])
    return True
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


def game_image(system: str, rom: str) -> str:
    """The scraped picture of a game (gamelist.xml), or ""."""
    meta = es_command.game_meta(system, rom)
    for key in ("thumbnail", "image"):
        value = meta.get(key) or ""
        if value:
            path = os.path.normpath(os.path.join(os.path.dirname(rom), value))
            if os.path.isfile(path):
                return path
    return ""


def write_json(path: str, data: dict) -> None:
    import json

    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(temporary, path)
    except OSError:
        pass


def read_json(path: str):
    import json

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_no_selection(path: str = ES_STATE_FILE) -> None:
    """``/tmp/es_state.inf`` with no game selected: on the reader screen, the
    game left selected in Recalbox's list must not be paired or started by
    the button."""
    lines = ["Version=2.0", "Action=endgame", "ActionData=", "System=", "SystemId=", "Game=",
             "GamePath=", "IsFolder=0", "State=selected"]
    temporary = path + ".rfid-tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        os.replace(temporary, path)
    except OSError:
        pass


def clear_selection(path: str = ES_STATE_FILE, target_path: str = None) -> None:
    from .esbridge import forget_target

    write_no_selection(path)
    forget_target(target_path)


class ReaderMode:
    """Switches between Recalbox's interface and the reader screen, starts the games."""

    def __init__(self, home: str, log, run=None, running=None, popen=None, clock=None, sleep=None,
                 python=None, hotkey_path: str = OVERRIDES, state_path: str = ES_STATE_FILE, uptime=None,
                 age=None, pids=None, kill=None, target_path: str = None, boot=None):
        self.home = home
        #: Straight to the reader screen at boot (bootmode): skip(), restore(), skipping().
        if boot is None and running is None:
            from . import bootmode

            boot = {"skip": lambda: bootmode.skip_interface(home), "restore": lambda: bootmode.restore_interface(home),
                    "skipping": bootmode.skipping, "stopping": bootmode.system_stopping}
        self._boot = boot or {}
        self.target_path = target_path
        #: Options: show the game before it starts; wait for the controller.
        self.preview = False
        self.confirm = False
        self.launch_path = LAUNCH_FILE
        self.answer_path = ANSWER_FILE
        #: Game shown on the screen, waiting for the controller.
        self.pending = None
        #: Called when a game waits (time paused), starts, or is given up.
        self.on_wait = None
        self.on_go = None
        self.on_cancel = None
        self._age = age or (frontend_age if running is None else (lambda: None))
        self._pids = pids or (frontend_pids if running is None else (lambda: []))
        self._kill = kill or os.kill
        self._uptime = uptime or system_uptime
        self._restart_at = None
        #: Next check that Recalbox's interface did not start behind the reader screen.
        self._intruder_check = 0.0
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
        self.handover_path = HANDOVER_FILE
        self._first_configure = True

    # ---------------------------------------------------------------- state
    @property
    def active(self) -> bool:
        """The reader screen replaces Recalbox's interface (or will)."""
        return self.state in ("screen", "game", "switching") and self.wanted

    def configure(self, wanted: bool, no_quit_hotkey: bool = False) -> None:
        """Settings changed: enter or leave the mode (in the background)."""
        self.no_quit_hotkey = bool(no_quit_hotkey)
        if self._first_configure:
            self._first_configure = False
            # The previous service left the reader screen to this one: taken
            # back (enter), or Recalbox's interface if the mode is now off.
            if handover_asked(self.handover_path, take=True) and not wanted:
                self._info("Relance du service : mode lecteur desactive, retour a l'interface de Recalbox")
                self._switch(False)
                return
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
        if left <= 0 or self._running() or self._boot_call("skipping"):
            return  # (Recalbox's interface does not start at boot: nothing to wait for)
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

    def _boot_call(self, name: str):
        action = self._boot.get(name)
        if action is None:
            return None
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - the boot stays as it was
            self._info("Demarrage direct de l'ecran du lecteur : %s" % exc)
            return None

    def start_frontend(self) -> None:
        # Its start at boot comes back first: the start script reads it.
        if self._boot_call("restore"):
            self._info("Demarrage : l'interface de Recalbox se lancera de nouveau")
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
        clear_selection(self.state_path, self.target_path)
        self.start_screen()
        self.state = "screen"
        self._info("Mode lecteur : l'ecran du lecteur remplace l'interface de Recalbox")
        # The next boots show the reader screen straight away.
        if self._boot_call("skip"):
            self._info("Demarrage : l'ecran du lecteur s'affichera sans passer par l'interface de Recalbox")

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
    def start_screen(self, after_game: bool = False) -> None:
        if self.screen is not None and self.screen.poll() is None:
            return
        main = os.path.join(self.home, "app", "main.py")
        env = es_command.launch_env()
        if after_game:
            # The game often leaves another refresh rate: the TV syncs again
            # (a few seconds of black), so the fade from black waits for it.
            env = dict(env, RFID_SCREEN_HOLD=str(AFTER_GAME_HOLD_S))
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

    def restart_screen(self) -> bool:
        """Starts the reader screen again (asked from the page): not a crash."""
        if self.state != "screen":
            return False
        self._info("Ecran du lecteur relance depuis la page")
        self.stop_screen()
        self._restart_at = None
        self.start_screen()
        return True

    # ---------------------------------------------------------------- games
    def launch(self, system: str, rom: str, name: str = "") -> bool:
        """Starts a game in place of the screen. False when not in the mode.

        Options: the game is shown on the screen first, and with ``confirm``
        it starts only when a controller button is pressed."""
        if self.state != "screen" or not self.wanted or self.pending is not None:
            return False
        try:
            argv = es_command.build(system, rom)
        except es_command.CommandError as exc:
            self._info("Lancement impossible : %s" % exc)
            return False
        name = name or os.path.splitext(os.path.basename(rom))[0]
        if self.preview or self.confirm:
            write_json(self.launch_path, {"system": system, "rom": rom, "name": name, "image": game_image(system, rom),
                                          "confirm": bool(self.confirm), "at": time.time()})
        if self.confirm:
            self.pending = {"argv": argv, "system": system, "rom": rom, "name": name, "since": time.time(),
                            "deadline": self._clock() + CONFIRM_TIMEOUT_S}
            self._info("Mode lecteur : %s attend un bouton de la manette" % name)
            if self.on_wait is not None:
                self.on_wait()
            return True
        if self.preview:
            self._sleep(PREVIEW_S)  # the game is shown, then started
        return self._start(argv, system, rom, name)

    def cancel_pending(self, reason: str = "") -> bool:
        """The game waiting for the controller is given up (card removed...)."""
        if self.pending is None:
            return False
        name = self.pending["name"]
        self.pending = None
        write_json(self.launch_path, {"cancel": True, "at": time.time()})
        self._info("Mode lecteur : lancement de %s annule%s" % (name, (" (%s)" % reason) if reason else ""))
        return True

    def _confirm_step(self) -> None:
        pending = self.pending
        answer = read_json(self.answer_path)
        if answer and answer.get("answer") == "go" and float(answer.get("at") or 0) >= pending["since"]:
            self.pending = None
            if self.on_go is not None:
                self.on_go()
            self._start(pending["argv"], pending["system"], pending["rom"], pending["name"])
            return
        if self._clock() >= pending["deadline"]:
            if self.on_cancel is not None:
                self.on_cancel()  # the controller gives the game up (and its player stays active)
            self.cancel_pending("pas de reponse")

    def _start(self, argv, system: str, rom: str, name: str) -> bool:
        if self.preview or self.confirm:
            write_json(self.launch_path, {"cancel": True, "at": time.time()})  # not shown again after the game
        self.state = "game"
        self.stop_screen()
        if self.no_quit_hotkey:
            set_hotkey_block(True, self.hotkey_path)
        self.game_info = (system, rom, name)
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
            # The end of the game is written as Recalbox does, then nothing is
            # selected any more (no list on the reader screen).
            write_state(self.game_info[0], self.game_info[1], self.game_info[2], False, self.state_path)
            clear_selection(self.state_path, self.target_path)
        self.game_info = None
        if self.wanted:
            self.start_screen(after_game=True)
            self.state = "screen"

    def step(self) -> None:
        """To call often: a game that ended, a screen that crashed."""
        if self.pending is not None:
            self._confirm_step()
        if self.state == "game" and self.game is not None and self.game.poll() is not None:
            self._info("Mode lecteur : fin du jeu, retour a l'ecran du lecteur")
            self._game_over()
            return
        if self.state == "screen" and self.screen is None and self._restart_at is not None:
            if self._clock() >= self._restart_at:
                self._restart_at = None
                self.start_screen()
            return
        if (self.state == "screen" and self.screen is not None and self.screen.poll() is None
                and self._clock() >= self._intruder_check):
            self._intruder_check = self._clock() + 10.0
            if self._running() and (self._thread is None or not self._thread.is_alive()):
                # Started by something else (boot safety, a script...): it cannot
                # get the display and would restart in a loop. Stopped.
                self._info("L'interface de Recalbox a demarre derriere l'ecran du lecteur : elle est arretee")
                self._thread = threading.Thread(target=self._stop_intruder, name="rfid-reader-mode", daemon=True)
                self._thread.start()
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

    def _stop_intruder(self) -> None:
        try:
            self._run([ES_SERVICE, "stop"])
            deadline = self._clock() + STOP_TIMEOUT_S
            while self._running() and self._clock() < deadline:
                self._sleep(0.5)
            for pid in self._pids():
                try:
                    self._kill(pid, getattr(signal, "SIGKILL", 9))
                except OSError:
                    pass
            self._boot_call("skip")  # the next boots skip it again
        except Exception as exc:  # noqa: BLE001 - checked again in 10 s
            self._info("Arret de l'interface de Recalbox impossible : %s" % exc)

    def shutdown(self) -> None:
        """The service stops: Recalbox's interface comes back."""
        if self._boot_call("stopping"):
            # The Recalbox itself turns off or restarts: the reader screen
            # (and its start at boot) stays for the next boot.
            self._info("Arret de la Recalbox : l'ecran du lecteur reviendra au prochain demarrage")
            return
        if self.state != "recalbox" and self.wanted and handover_asked(self.handover_path):
            # A restart (update): the next service shows the reader screen
            # again at once; Recalbox's interface is not started in between.
            self.state = "switching"
            self.stop_screen()
            self._stop_game()
            set_hotkey_block(False, self.hotkey_path)
            self.state = "recalbox"
            self._info("Relance du service : l'ecran du lecteur revient tout de suite (sans l'interface de Recalbox)")
            return  # the flag stays: the next service reads it
        handover_asked(self.handover_path, take=True)  # nothing handed over: the next service starts as usual
        if self.state != "recalbox":
            self.wanted = False
            self.leave()

    def _info(self, text: str) -> None:
        if self.log:
            self.log.info(text)
