"""Main service: reading loop for the reader and the button."""

from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import threading
import time

from . import __version__
from . import calibration
from .config import Config
from .consts import (
    AGENT_COMMAND_FILENAME,
    CALIBRATION_BACKUP_FILENAME,
    TAG_WRITE_FILENAME,
    CALIBRATION_FILENAME,
    ES_STATE_FILE,
    LOCK_FILE,
    READER_TEST_FILENAME,
    db_path,
    home_dir,
)
from .controller import Controller
from .esbridge import (
    EsLauncher,
    Target,
    game_is_running,
    read_state,
    current_target,
    relative_game_key,
    remember_target,
    state_snapshot,
    supports_start_command,
)
from .feedback import Feedback
from .led import StatusLight, build_light
from .library import Library
from .osd import SCREEN_MESSAGE_FILE, ScreenMessages
from .playtime import PlayTimer
from .players import Players
from .savegame import GameSaver
from .reader_mode import ReaderMode
from . import avatars, bedtime, es_command, frontend_lock, power, refusals, trophies
from .drivers.rc522 import PICC_REQA, PICC_WUPA, Rc522, Rc522Error
from .drivers.spi_port import open_spi
from .hardware import build_button, build_gpio, build_reader
from . import pairing
from .logutil import Logger
from .storage import TagStore

try:  # fcntl does not exist on Windows (simulation mode on a PC)
    import fcntl
except ImportError:  # pragma: no cover - platform dependent
    fcntl = None


def pid_path(home: str = None) -> str:
    return os.path.join(home or home_dir(), "rfid.pid")


def status_path(home: str = None) -> str:
    return os.path.join(home or home_dir(), "status.json")


def recalbox_version() -> str:
    try:
        with open("/recalbox/recalbox.version", "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return "inconnue"


def write_json_atomic(path: str, payload: dict) -> None:
    """Writes a small JSON file atomically."""
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".status-", dir=directory)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError:
        pass


def read_status(home: str = None):
    try:
        with open(status_path(home), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def process_alive(pid: int) -> bool:
    """True if the PID exists and really is our service."""
    if pid <= 0:
        return False
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            command = handle.read()
        return b"main.py" in command or b"rfid" in command
    except OSError:
        pass

    if os.name == "nt":  # development on a PC (no /proc)
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, 0, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:  # noqa: BLE001
            return False

    # POSIX systems without /proc: process existence only.
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(home: str = None) -> int:
    try:
        with open(pid_path(home), "r", encoding="ascii") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return 0


def acquire_lock(path: str = LOCK_FILE):
    """Exclusive lock: prevents two instances (ES restarts permanent scripts)."""
    if fcntl is None:
        return -1
    for candidate in (path, os.path.join(tempfile.gettempdir(), "rfid-launcher.lock")):
        try:
            directory = os.path.dirname(candidate)
            if directory:
                os.makedirs(directory, exist_ok=True)
            descriptor = os.open(candidate, os.O_CREAT | os.O_RDWR, 0o644)
        except OSError:
            continue
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            return 0
        try:
            os.ftruncate(descriptor, 0)
            os.write(descriptor, ("%d\n" % os.getpid()).encode("ascii"))
        except OSError:
            pass
        return descriptor
    return -1


def release_lock(descriptor: int) -> None:
    if descriptor and descriptor > 0 and fcntl is not None:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
        except OSError:
            pass


class Service:
    """Puts together hardware, storage and business logic."""

    def __init__(self, cfg: Config, log: Logger, home: str = None, db: str = None):
        self.cfg = cfg
        self.log = log
        self.home = home or home_dir()
        self.db_path = db or db_path()
        self.running = False
        self.gpio = None
        self.button = None
        self.reader = None
        self.store = None
        self.controller = None
        self.feedback = None
        self.launcher = None
        self._web_command_signature = None
        self._press_started_at = None
        self._active_uid = None
        self._absent_since = None
        self._absent_hits = 0
        self._active_seen_at = 0.0
        self._last_read_at = 0.0
        self._action_at = 0.0
        self._launched_uid = None
        self._stop_pending = None
        self._stop_on_remove = bool(cfg.get_bool("launch", "stop_on_remove", False))
        self.power_ctl = None
        self._idle_since = time.monotonic()
        #: Bedtime: was it bedtime at the last check (None: not known yet,
        #: the Recalbox turned on during bedtime is not turned off again).
        self._bedtime_was = None
        self._bedtime_warned = ""
        self._next_bedtime_check = 0.0
        self._next_trophies_check = 0.0
        self.rearm_absent_ms = 1200
        self.last_error_at = 0.0
        self.last_uid = ""
        self.last_uid_at = 0.0
        self.started_at = time.time()
        self._reader_test = None
        self._calibration = None
        self._calibration_signature = None
        #: Set to True after a test/measurement: the badge already on the reader
        #: is adopted (locked) instead of being taken for a new badge.
        #: The adoption expires: a badge placed later must act normally.
        self._adopt_next_read = False
        self._adopt_until = 0.0
        self._status_signature = None
        self._status_written = 0.0
        self.library = None
        self.playtime = None
        self.players = None
        self._next_player_check = 0.0
        self._players_gone = 0
        #: A game refused (no player card, time used up) is being quit.
        self._refusing = False
        self.screen = None
        self.light = None
        self._expire_at = None
        self._pairing_shown = None
        self._next_light_check = 0.0
        self._light_pairing = False
        self._next_game_check = 0.0
        self._game_gone = 0
        self._tag_write = None
        self._es_state_mtime = None
        self._next_es_check = 0.0
        self.saver = None
        #: Reader screen in place of Recalbox's interface (option).
        self.reader_mode = None
        #: Menu lock watchdog: since when the Recalbox interface is missing.
        self._frontend_missing_since = None
        self._next_frontend_check = 0.0
        #: The "unlock" card is switching the menu (the interface restarts).
        self._unlock_busy = False
        #: New game asked by a button double press: {"uid", "player", "at", "tries"}.
        self._new_game = None
        #: The next game start is not resumed (a new game was asked).
        self._skip_resume = False
        #: The frontend said a game runs (to resume it once, at its start).
        #: None until the first reading: a game already running when the
        #: service starts is never reloaded.
        self._es_playing = None

    # ------------------------------------------------------------------ setup
    def setup(self) -> bool:
        self.log.info(
            "Recalbox RFID Launcher %s (Python %s) -- Recalbox %s"
            % (__version__, sys.version.split()[0], recalbox_version())
        )
        if not os.path.exists("/usr/bin/emulationstation"):
            self.log.info("Frontend Recalbox absent (mode developpement, hors Recalbox).")
        elif not supports_start_command():
            self.log.warning(
                "Le binaire du frontend ne contient pas la commande de lancement UDP : "
                "Recalbox 9 ou plus est necessaire pour lancer un jeu."
            )

        self.store = TagStore(self.db_path, self.log)
        self.store.load()
        self.log.info("%d association(s) chargee(s) depuis %s" % (self.store.count(), self.db_path))

        self.feedback = Feedback(
            enabled=self.cfg.get_bool("feedback", "sound", True),
            player=self.cfg.get("feedback", "sound_player", "auto"),
            log=self.log,
        )

        self.gpio = build_gpio(self.cfg, self.log)
        self.button = build_button(self.cfg, self.log, self.gpio)

        self.launcher = EsLauncher(
            self.cfg.get("launch", "udp_host", "127.0.0.1"),
            self.cfg.get_int("launch", "udp_port", 1337),
            self.log,
        )
        self.library = Library(log=self.log)
        self.reader_mode = ReaderMode(self.home, self.log)
        self.launcher.reader = self.reader_mode
        self._configure_reader_mode()
        self.power_ctl = power.Power(self.log, prepare=self._before_power)
        self.playtime = PlayTimer(self.home, log=self.log)
        self.players = Players(self.home, log=self.log)
        self._build_extras()
        self._build_controller()
        return True

    def _build_extras(self) -> None:
        """Screen messages and status light (rebuilt when the settings change)."""
        self.screen = ScreenMessages(
            enabled=self.cfg.get_bool("screen", "messages", True),
            port=self.cfg.get_int("screen", "retroarch_port", 55355),
            log=self.log,
            screen_file=SCREEN_MESSAGE_FILE,
        )
        self.saver = GameSaver(
            port=self.cfg.get_int("screen", "retroarch_port", 55355),
            log=self.log,
            show=self.screen.say,
            player_dir=os.path.join(self.home, "player-saves"),
        )
        if self.light is not None:
            try:
                self.light.close()
            except Exception:  # noqa: BLE001
                pass
        self.light = build_light(self.cfg, self.gpio, self.log)

    def _build_controller(self) -> None:
        self.controller = Controller(
            self.store, self.launcher, self.feedback, self.cfg, self.log,
            library=self.library, playtime=self.playtime, screen=self.screen,
            light=self.light, power=self._power_off, card_reader=self._read_card_memory,
            players=self.players, saver=self.saver,
            unlock=self._unlock_card,
            unlocked=lambda: frontend_lock.is_unlocked(self.home),
            home=self.home,
        )

    def _read_card_memory(self):
        """Memory of the badge on the reader (portable cards), or None."""
        reader = self.reader
        if reader is None or not hasattr(reader, "read_memory"):
            return None
        return reader.read_memory()

    def _power_off(self) -> None:
        """The "turn off" card: after a countdown (removing the card cancels), or at once."""
        ctl = getattr(self, "power_ctl", None)
        if ctl is None:
            return
        if not self.cfg.get_bool("display", "poweroff_countdown", True):
            ctl.now("poweroff")
            return
        ctl.begin("poweroff", "card", uid=self.last_uid)
        reader = getattr(self, "reader_mode", None)
        if self.screen is not None and (reader is None or reader.state != "screen"):
            # The reader screen shows the countdown itself; elsewhere, a message.
            self.screen.say("power_card", n=int(power.DELAYS["card"]))

    def _before_power(self, action: str) -> None:
        """Just before turning off: a game running is quit first (and saved, if set)."""
        controller = self.controller
        try:
            if controller is not None and controller.game_running():
                controller.stop_game("poweroff")
        except Exception as exc:  # noqa: BLE001 - turned off all the same
            self.log.warning("Arret du jeu avant extinction impossible : %s" % exc)

    def _power_step(self) -> None:
        ctl = getattr(self, "power_ctl", None)
        if ctl is None or ctl.done is not None:
            return
        now = time.monotonic()
        reader = getattr(self, "reader_mode", None)
        on_screen = reader is not None and reader.state == "screen"
        try:
            playing = bool(self.controller is not None and self.controller.game_running())
        except Exception:  # noqa: BLE001
            playing = False
        asked = ctl.take_request()
        if asked:
            self._idle_since = now  # someone uses a controller
        if asked == "cancel" and (ctl.pending is None or ctl.pending["source"] != "curfew"):
            pending = ctl.pending
            if ctl.cancel("manette"):
                self._power_cancelled(pending)
        elif asked in power.ACTIONS:
            allowed = power.menu_actions(self.cfg.get("display", "power_menu", "both"))
            if asked in allowed and on_screen and not playing and ctl.pending is None:
                ctl.begin(asked, "menu")
            else:
                self.log.info("Menu d'alimentation : %s refuse" % asked)
        # Nobody playing on the reader screen for a while: turned off.
        minutes = self.cfg.get_int("display", "idle_off_min", 0)
        if (minutes <= 0 or not on_screen or playing or ctl.pending is not None
                or self._active_uid is not None or reader.pending is not None):
            if ctl.pending is None or ctl.pending["source"] != "idle":
                self._idle_since = now
        elif now - self._idle_since >= minutes * 60:
            self.log.info("Personne ne joue depuis %d min" % minutes)
            ctl.begin("poweroff", "idle")
        if ctl.pending is not None and ctl.pending["source"] == "idle" and (playing or not on_screen):
            ctl.cancel("partie")
        pending = ctl.pending
        ctl.step(self._active_uid)
        if pending is not None and ctl.pending is None and ctl.done is None:
            self._idle_since = now
            self._power_cancelled(pending)

    def _power_cancelled(self, pending) -> None:
        if self.screen is not None and pending is not None:
            self.screen.say("power_cancelled" if pending["action"] == "poweroff" else "reboot_cancelled")

    def _open_reader(self) -> bool:
        try:
            self.reader = build_reader(self.cfg, self.log, self.gpio)
            self.reader.start()
            return True
        except Exception as exc:  # noqa: BLE001 - retried later
            now = time.monotonic()
            if now - self.last_error_at > 30:
                self.last_error_at = now
                self.log.error("Lecteur RFID indisponible : %s" % exc)
                self.log.error(
                    "Verifiez le cablage, puis 'dtparam=spi=on' dans "
                    "/boot/recalbox-user-config.txt et redemarrez."
                )
            return False

    # ------------------------------------------------------------------ execution
    def run(self) -> int:
        lock = acquire_lock()
        if lock == 0:
            self.log.info("Une autre instance du service tourne deja : abandon.")
            return 0
        self.running = True
        os.makedirs(self.home, exist_ok=True)
        try:
            with open(pid_path(self.home), "w", encoding="ascii") as handle:
                handle.write("%d\n" % os.getpid())
        except OSError:
            pass

        self._install_signals()
        try:
            self.setup()
        except Exception as exc:  # noqa: BLE001 - unreadable configuration, disk full...
            self.log.error("Initialisation impossible : %s" % exc)
            self._shutdown(lock)
            return 2

        interval = max(0.02, self.cfg.get_int("rfid", "poll_interval_ms", 150) / 1000.0)
        self.rearm_absent_ms = float(self.cfg.get_int("rfid", "rearm_absent_ms", 1200))
        next_slot = 0.0
        next_status = 0.0
        next_reader = 0.0
        try:
            while self.running:
                now = time.monotonic()

                # The reader may show up later (SPI enabled afterwards): retry
                # regularly without blocking the button or the agent.
                if self.reader is None and now >= next_reader:
                    next_reader = now + 2.0
                    self._open_reader()
                    if self.reader is None:
                        self._write_status()

                if (self.reader is not None and self._reader_test is None
                        and self._calibration is None and self._tag_write is None
                        and now >= next_slot):
                    # Read again at each turn: the setting applies without a restart.
                    interval = max(0.02, self.cfg.get_int("rfid", "poll_interval_ms", 150) / 1000.0)
                    next_slot = now + interval
                    uid = None
                    try:
                        uid = self.reader.read_uid()
                    except Exception as exc:  # noqa: BLE001
                        self.log.warning("Lecture RFID en echec : %s" % exc)
                    if uid:
                        self._badge_seen(uid)

                if self.button is not None:
                    self._track_press()
                    gesture = self.button.poll()
                    if gesture:
                        self._handle_gesture(gesture)

                # Is the badge still there? The read may fail or be filtered
                # (debounce): only an absence ANSWERED by the reader counts.
                if self._calibration is None:
                    self._check_presence()
                    self._service_stop()
                self._calibration_step()
                self._tag_write_step()
                self._consume_agent_command()
                self._reader_test_step()

                if self.controller.tick() == "expired":
                    self.log.info("Mode arme expire")
                self._playtime_step()
                self._new_game_step()
                self._players_step()
                self._light_step()
                self._lock_watchdog()
                self._reader_step()
                self._power_step()
                self._bedtime_step()
                self._trophies_step()
                self._watch_frontend()

                try:
                    self.store.reload_if_changed()
                except Exception as exc:  # noqa: BLE001 - database edited by hand
                    self.log.warning("Relecture de la base impossible : %s" % exc)

                if now >= next_status:
                    next_status = now + 2.0
                    self._write_status()

                time.sleep(0.03)
        finally:
            self._shutdown(lock)
        return 0

    # ------------------------------------------------------------------ badge
    def _badge_seen(self, uid: str) -> None:
        """A badge is read. A badge left in place does not repeat the action."""
        self.last_uid = uid
        self.last_uid_at = time.time()
        maintenant = time.monotonic()
        self._last_read_at = maintenant
        if getattr(self, "_adopt_next_read", False) and maintenant <= getattr(
                self, "_adopt_until", 0.0):
            # A test or a measurement has just queried the reader itself: the
            # badge left at the end was never seen by the loop. Without this it
            # looked like a new badge and started the game right after the
            # measurement.
            self._adopt_next_read = False
            self._active_uid = uid
            self._active_seen_at = maintenant
            self._absent_since = None
            self._absent_hits = 0
            if self.log:
                self.log.info(
                    "Badge %s deja pose : il n'agit pas (retirez-le pour le rescanner)" % uid
                )
            return
        # Too late: the badge may have been swapped meanwhile, it acts.
        self._adopt_next_read = False
        if uid == self._active_uid:
            # The badge is still there: its presence is refreshed, without acting.
            self._active_seen_at = maintenant
            self._absent_since = None
            self._absent_hits = 0
            return
        self._active_uid = uid
        self._active_seen_at = maintenant
        self._absent_since = None
        self._absent_hits = 0
        self._launched_uid = None
        stop_pending = getattr(self, "_stop_pending", None)
        ctl = getattr(self, "power_ctl", None)
        if ctl is not None and ctl.pending is not None and ctl.pending["source"] not in ("card", "curfew"):
            # A card cancels the countdown of the power menu or of nobody playing.
            pending = ctl.pending
            if ctl.cancel("carte posee"):
                self._power_cancelled(pending)
        self._idle_since = time.monotonic()
        result = self.controller.on_badge(uid)
        self._action_at = time.monotonic()
        if getattr(self.controller, "last_action", "") == "launched":
            # Kept for the "quit the game when the badge is removed" option.
            self._launched_uid = uid
        elif result == "extended" and stop_pending is not None:
            # Cartridge swap: the game card was just pulled out and a bonus
            # card put in its place before the game was quit. The game goes
            # on, and the bonus card now holds it.
            self._stop_pending = None
            self._launched_uid = uid
            if self.log:
                self.log.info("Carte bonus inseree a la place du jeu : la partie continue")

    def _watch_frontend(self) -> None:
        """Remembers the selected game: the screensaver erases it from the state file."""
        now = time.monotonic()
        if now < self._next_es_check:
            return
        self._next_es_check = now + 1.0
        try:
            mtime = os.stat(ES_STATE_FILE).st_mtime
        except OSError:
            return
        if mtime == self._es_state_mtime:
            return
        self._es_state_mtime = mtime
        state = read_state()
        self._resume_on_start(state)
        target = current_target(state, allow_running=True)
        if target is not None:
            remember_target(target)

    def _resume_on_start(self, state) -> None:
        """A game starts: its game saved by the reader is resumed (option)."""
        playing = game_is_running(state)
        started = playing and getattr(self, "_es_playing", None) is False
        self._es_playing = playing
        if started:
            self._check_command_later()
        controller = self.controller
        if not started or self.saver is None or controller is None:
            return
        if not getattr(controller, "save_on_quit", False):
            return
        if self._skip_resume:
            self._skip_resume = False
            self.log.info("Nouvelle partie : la sauvegarde n'est pas reprise")
            return
        path = str((state or {}).get("GamePath") or "")
        expected = os.path.splitext(os.path.basename(path))[0] if path else ""
        self.saver.resume_later(expected, owner=controller.save_owner)

    #: The interface's command is read once the game has settled.
    COMMAND_CHECK_DELAY_S = 25.0

    def _check_command_later(self) -> None:
        """A game started by Recalbox's interface: its command is compared with
        the one the reader screen would run (diagnostic shown by the page)."""
        reader_mode = getattr(self, "reader_mode", None)
        if reader_mode is not None and reader_mode.state != "recalbox":
            return  # our own launch

        def work():
            time.sleep(self.COMMAND_CHECK_DELAY_S)
            try:
                actual = es_command.running_command()
                if not actual:
                    return
                result = es_command.check(actual)
                es_command.record(self.home, result)
                if result.get("same"):
                    self.log.info("Commande de lancement identique a celle de Recalbox (%s)" % result["game"])
                else:
                    self.log.warning("Commande de lancement differente de celle de Recalbox (%s) : %s" % (
                        result["game"], result.get("error") or ", ".join(
                            "%s %s au lieu de %s" % (d["option"], d["reader"], d["recalbox"])
                            for d in result["differences"])))
                self._write_status(force=True)
            except Exception as exc:  # noqa: BLE001 - a check never disturbs the game
                self.log.warning("Verification de la commande impossible : %s" % exc)

        threading.Thread(target=work, name="command-check", daemon=True).start()

    # ------------------------------------------------------------- play time
    #: Time given to read "play time is over" before the game is quit.
    EXPIRE_NOTICE_S = 3.0

    def _playtime_step(self) -> None:
        """Warnings, end of a time-limited game, game quit from its own menu."""
        timer = getattr(self, "playtime", None)
        if timer is None or self.controller is None:
            return
        now = time.monotonic()
        if self._expire_at is not None and now >= self._expire_at:
            self._expire_at = None
            self._launched_uid = None
            try:
                self.controller.stop_game("refused" if getattr(self, "_refusing", False) else "time")
            except Exception as exc:  # noqa: BLE001 - never blocking
                self.log.warning("Arret du jeu impossible : %s" % exc)
            return
        event = timer.tick()
        if event in ("warn300", "warn60"):
            if self.screen is not None:
                self.screen.say(event)
            self.feedback.armed()
            self.log.info("Temps de jeu : avertissement (%s)" % event)
        elif event == "expired":
            if self.screen is not None:
                self.screen.say("expired")
            self.feedback.timeout()
            if self.light is not None:
                self.light.flash("timeup")
            self.log.info("Temps de jeu termine : le jeu va etre quitte")
            self._expire_at = now + self.EXPIRE_NOTICE_S
            return
        # Game quit from the emulator menu: the limited session is over.
        if timer.session is not None and now >= self._next_game_check:
            self._next_game_check = now + 2.0
            if now - timer.session["started"] < 20.0:
                return
            if self.controller.game_running():
                self._game_gone = 0
                return
            self._game_gone += 1
            if self._game_gone >= 2:
                self._game_gone = 0
                timer.end("quit")
                self.controller.launched_uid = None
                self.log.info("Jeu limite quitte depuis son menu")

    # ---------------------------------------------------------------- players
    def _active_player(self):
        """(uid, entry) when the badge lying on the reader is a player card."""
        uid = self._active_uid
        if not uid or self.store is None:
            return None
        try:
            entry = self.store.get(uid)
        except Exception:  # noqa: BLE001 - unreadable list
            return None
        if entry and entry.get("kind") == "action" and entry.get("action") == "player":
            return uid, entry
        return None

    def _refuse_game(self, key: str, message: str, record: bool = True, **values) -> None:
        """A game started from the menu is not allowed: message, then quit."""
        self._refusing = True
        if record:
            game = {}
            try:
                game = self.controller.running_game() or {}
            except Exception:  # noqa: BLE001
                pass
            refusals.record(self.home, key, player=values.get("name", ""), game=game.get("name", ""),
                            system=game.get("system", ""), via="menu")
        if self.screen is not None:
            self.screen.say(key, **values)
        self.feedback.error()
        if self.light is not None:
            self.light.flash("error")
        self.log.info(message)
        self._expire_at = time.monotonic() + self.EXPIRE_NOTICE_S

    def _limit_menu_game(self, uid: str, name: str, left) -> None:
        if left is not None and self.playtime is not None and self.playtime.session is None:
            self.playtime.start(uid, {"name": name}, left / 60.0)

    def _menu_game(self) -> None:
        """A game nobody started with a card: launched from the Recalbox menu."""
        controller = self.controller
        players = self.players
        # A player card placed earlier and lifted does not count: for a menu
        # game, the card stays on the reader (unless the player is kept active).
        players.pending = None
        holder = self._active_player()
        if holder is None and players.keep and players.kept is not None:
            holder = (players.kept["uid"], players.kept["entry"])
        if holder is not None:
            uid, entry = holder
            name = players.player_name(entry)
            game = controller.running_game() or {}
            state = read_state() or {}
            rule = None if controller.unlocked else controller.player_rule(
                uid, entry, game={"system": game.get("system", ""), "path": str(state.get("GamePath") or "")})
            if rule is not None and controller.block_exhausted:
                self._refuse_game(rule[0], "Jeu du menu refuse pour %s (%s)" % (name, rule[0]), **rule[1])
                return
            left = None if controller.unlocked else controller.player_left(uid, entry)
            if left is not None and left <= 0 and controller.block_exhausted:
                self._refuse_game("player_exhausted", "Jeu du menu refuse : plus de temps pour %s" % name, name=name)
                return
            players.begin(uid, entry, via="reader", game=controller.running_game())
            self._remember_menu_game(uid)
            self._limit_menu_game(uid, name, left)
            if self.screen is not None:
                if left is None:
                    self.screen.say("player_unlimited", name=name)
                else:
                    self.screen.say("player_hello", name=name, n=max(1, int(round(left / 60.0))))
            self.log.info("Jeu lance depuis le menu : compte pour %s" % name)
            return
        free = controller.unlocked
        if controller.require_player and not free:
            self._refuse_game("player_needed", "Jeu du menu refuse : aucune carte joueur posee")
            return
        left = None if free else controller.guest_left()
        if left is not None and left <= 0 and controller.block_exhausted:
            self._refuse_game("guest_exhausted", "Jeu du menu refuse : plus de temps sans carte joueur")
            return
        players.begin("", {}, via="menu", game=controller.running_game())
        self._remember_menu_game("")
        self._limit_menu_game("", "", left)
        self.log.info("Jeu lance depuis le menu : compte pour l'invite")

    def _remember_menu_game(self, uid: str) -> None:
        """A game started from the menu: the "continue" card can start it again."""
        try:
            game = self.controller.running_game() or {}
            path = str((read_state() or {}).get("GamePath") or "")
            self.players.remember(uid, game.get("system", ""), game.get("name", ""), path)
        except Exception:  # noqa: BLE001 - never blocking
            pass

    def _players_step(self) -> None:
        """Counts the time of the player, and watches the games started from the menu."""
        players = getattr(self, "players", None)
        controller = self.controller
        if players is None or controller is None or not getattr(controller, "counting_players", False):
            return
        players.tick()
        now = time.monotonic()
        if now < self._next_player_check:
            return
        self._next_player_check = now + 2.0
        try:
            running = bool(controller.game_running())
        except Exception:  # noqa: BLE001 - never blocking
            return
        current = players.current
        kept = players.kept if players.keep else None
        if kept is not None and current is None and not controller.unlocked:
            left = controller.player_left(kept["uid"], kept["entry"])
            if left is not None and left <= 0:
                players.release("temps ecoule")
        if not running:
            self._refusing = False
            if current is not None and now - current["since"] > 20.0:
                self._players_gone += 1
                if self._players_gone >= 2:
                    self._players_gone = 0
                    players.finish()
                    self.log.info("Fin de partie : temps de jeu enregistre")
            return
        self._players_gone = 0
        if controller.paused and self.saver is not None and self.saver.state() == "PLAYING":
            controller.resume_time()  # pause left from the game itself
            self.log.info("Fin de la pause : le temps est de nouveau compte")
        if current is None and not self._refusing:
            self._menu_game()

    # ---------------------------------------------------------- status light
    def _light_step(self) -> None:
        """Pairing message on the game screen and colour of the light."""
        now = time.monotonic()
        if now >= self._next_light_check:
            self._next_light_check = now + 0.5
            try:
                request = pairing.pending(self.home)
            except Exception:  # noqa: BLE001 - unreadable state file
                request = None
            self._light_pairing = request is not None
            if request is not None and request.get("id") != self._pairing_shown:
                self._pairing_shown = request.get("id")
                if self.screen is not None:
                    self.screen.say("pairing")
        light = self.light
        if light is None or not light.enabled:
            return
        mode = self.controller.mode if self.controller is not None else ""
        remaining = self.playtime.remaining_s() if self.playtime is not None else None
        if self.reader is None:
            state = "noreader"
        elif self._light_pairing:
            state = "pairing"
        elif mode == "associate":
            state = "associate"
        elif mode == "delete":
            state = "delete"
        elif remaining is not None and remaining <= 60:
            state = "warning"
        elif self.controller is not None and self.controller.launched_uid:
            state = "playing"
        else:
            state = "idle"
        light.set_state(state)
        light.update()

    #: Time (seconds) without seeing the badge before concluding it was removed.
    ABSENCE_MIN_S = 2.0
    #: Grace delay after an action: a launch must never be undone.
    GRACE_ACTION_S = 3.0
    #: Maximum time (seconds) to wait for the emulator to start.
    STOP_WAIT_S = 6.0

    def _check_presence(self) -> None:
        """Is the locked badge still on the reader?

        The reader answers (REQA or WUPA), never the silence of a failed read: a
        read may fail or be filtered by the debounce without the badge moving.
        """
        if self._active_uid is None or self.reader is None:
            return
        # During a reader test, the test is the one querying the module.
        if (getattr(self, "_reader_test", None) is not None
                or getattr(self, "_calibration", None) is not None):
            return
        maintenant = time.monotonic()
        # A recent positive read is enough: no need to query again.
        if maintenant - self._last_read_at < 0.6:
            self._absent_since = None
            self._absent_hits = 0
            return
        if maintenant - self._action_at < self.GRACE_ACTION_S:
            return
        try:
            verdict = self.reader.tag_present()
        except Exception:  # noqa: BLE001 - reader unplugged while running
            verdict = None
        if verdict is None:
            # Silent reader: nothing can be concluded about the badge presence.
            return
        if verdict:
            self._absent_since = None
            self._absent_hits = 0
            return
        if self._absent_since is None:
            self._absent_since = maintenant
        self._absent_hits += 1
        if self._absent_hits < 3:
            return
        if maintenant - self._absent_since < self._absence_requise_s():
            return
        self._release_latch()

    def _absence_requise_s(self) -> float:
        return max(self.ABSENCE_MIN_S, float(self.rearm_absent_ms) / 1000.0)

    def _release_latch(self) -> None:
        """Badge removed: the lock is released and, if requested, the game is quit."""
        badge = self._active_uid
        lance = self._launched_uid
        self._active_uid = None
        self._absent_since = None
        self._absent_hits = 0
        self._launched_uid = None
        players = getattr(self, "players", None)
        current = players.current if players is not None else None
        if current is not None and current.get("via") == "reader" and current.get("uid") == badge:
            self._stop_pending = (badge, time.monotonic() + self.STOP_WAIT_S)
            if self.screen is not None:
                self.screen.say("player_left")
            self.log.info("Carte joueur %s retiree : fin de la partie" % badge)
            return
        if not (self._stop_on_remove and lance and badge):
            return
        # The emulator may still be starting: let the service notice it in
        # the loop instead of blocking the badge reading.
        self._stop_pending = (badge, time.monotonic() + self.STOP_WAIT_S)
        if self.log:
            self.log.info("Badge %s retire : arret du jeu demande" % badge)

    def _service_stop(self) -> None:
        """Stops the game when one is really running (never EmulationStation)."""
        if self._stop_pending is None or self.controller is None:
            return
        badge, echeance = self._stop_pending
        try:
            en_cours = bool(self.controller.game_running())
        except Exception:  # noqa: BLE001 - never blocking
            en_cours = False
        if not en_cours:
            if time.monotonic() < echeance:
                return
            self._stop_pending = None
            if self.log:
                self.log.info("Badge %s retire : aucun jeu en cours a arreter" % badge)
            return
        self._stop_pending = None
        try:
            arrete = bool(self.controller.stop_game())
        except Exception as exc:  # noqa: BLE001 - never blocking
            arrete = False
            if self.log:
                self.log.warning("Arret du jeu impossible : %s" % exc)
        if self.log:
            self.log.info(
                "Badge %s retire : %s" % (badge, "jeu arrete" if arrete else "arret impossible")
            )

    # ------------------------------------------------------------------ button
    def _track_press(self) -> None:
        """Memorise l'instant (horloge murale) ou l'appui a commence."""
        try:
            pressed = self.button.is_pressed()
        except Exception:  # noqa: BLE001 - button unplugged while running
            return
        if pressed and self._press_started_at is None:
            self._press_started_at = time.time()
        elif not pressed:
            self._press_started_at = None

    def _arm_adoption(self, secondes: float = 10.0) -> None:
        """The next badge read is locked without acting (after a measurement).

        The adoption expires after a few seconds: a badge placed well after the
        measurement must behave normally.
        """
        self._adopt_next_read = True
        self._adopt_until = time.monotonic() + secondes

    def _forget_latch(self) -> None:
        """Forgets the badge on the reader: an armed mode allows presenting it again."""
        self._active_uid = None
        self._absent_since = None
        self._absent_hits = 0
        self._last_read_at = 0.0
        self._adopt_next_read = False
        self._adopt_until = 0.0

    def _handle_gesture(self, gesture: str) -> None:
        """Handles a gesture received on release (short or very long)."""
        request = None
        try:
            request = pairing.pending(self.home)
        except Exception as exc:  # noqa: BLE001 - unreadable state file
            if self.log:
                self.log.warning("Demande d'appairage illisible : %s" % exc)

        if request is not None:
            if gesture == "hold":
                started = self._press_started_at or time.time()
                if pairing.grant(self.home, request, started):
                    self.feedback.ok()
                    if getattr(self, "screen", None) is not None:
                        self.screen.say("paired")
                    if getattr(self, "light", None) is not None:
                        self.light.flash("ok")
                    if self.log:
                        self.log.info(
                            "Appairage confirme au bouton (demande %s)" % request.get("id")
                        )
                else:
                    self.feedback.error()
                    if self.log:
                        self.log.warning(
                            "Appui commence avant la demande d'appairage : ignore"
                        )
                return

        if gesture == "double" and self._start_new_game():
            return
        if gesture not in ("short", "double"):
            # "hold" without a pending request does nothing; the "long" gesture
            # no longer exists (erasing is done from the web interface).
            return
        self._forget_latch()
        self.controller.on_button("short")

    # ---------------------------------------------------------- trophies
    def _trophies_step(self) -> None:
        """New trophies of the players (every minute): a message on the screen."""
        now = time.monotonic()
        players = getattr(self, "players", None)
        if (now < self._next_trophies_check or players is None or self.controller is None
                or not getattr(self.controller, "counting_players", False)):
            return
        self._next_trophies_check = now + 60.0
        try:
            new = trophies.update(self.home, players.games)
        except Exception as exc:  # noqa: BLE001 - never blocking
            self.log.warning("Trophees non calcules : %s" % exc)
            return
        for uid, kind, level in new[:3]:
            entry = None
            try:
                entry = self.store.get(uid)
            except Exception:  # noqa: BLE001
                pass
            name = players.player_name(entry)
            self.log.info("Nouveau trophee pour %s : %s %d" % (name, kind, level))
            if self.screen is not None:
                self.screen.say("trophy_" + kind, name=name, n=level)

    # ---------------------------------------------------------- bedtime
    def _bedtime_step(self) -> None:
        """Warning 5 minutes before bedtime, then the game is quit (and the
        Recalbox turned off, as an option). Games started during bedtime are quit."""
        controller = self.controller
        span = getattr(controller, "bedtime", None) if controller is not None else None
        now = time.monotonic()
        if span is None or now < self._next_bedtime_check:
            if span is None:
                self._bedtime_was = None
            return
        self._next_bedtime_check = now + 5.0
        wall = time.time()
        night = bedtime.active(span, wall)
        free = controller.unlocked
        try:
            running = bool(controller.game_running())
        except Exception:  # noqa: BLE001
            running = False
        if not running and not getattr(controller, "counting_players", False):
            self._refusing = False
        before = bedtime.minutes_to_start(span, wall)
        today = time.strftime("%Y-%m-%d", time.localtime(wall))
        if not night and 0 < before <= bedtime.WARN_MIN and self._bedtime_warned != today and not free:
            self._bedtime_warned = today
            if self.screen is not None:
                self.screen.say("curfew_soon", n=max(1, int(round(before))))
            self.log.info("Heure du coucher dans %d min" % max(1, int(round(before))))
        starting = night and self._bedtime_was is False
        self._bedtime_was = night
        ctl = getattr(self, "power_ctl", None)
        if ctl is not None and ctl.pending is not None and ctl.pending["source"] == "curfew" and free:
            ctl.cancel("carte deverrouiller")
        if not night or free:
            return
        if running and not getattr(self, "_refusing", False):
            to = bedtime.clock_text(span[1])
            if starting:
                self._refuse_game("curfew_now", "Heure du coucher : fin de la partie", record=False, to=to)
            else:
                self._refuse_game("curfew", "Heure du coucher : jeu du menu refuse", to=to)
        if starting:
            self.log.info("Heure du coucher")
            off = ctl is not None and self.cfg.get_bool("time", "curfew_poweroff", False)
            if not running and self.screen is not None:
                if off:
                    self.screen.say("curfew_off")
                else:
                    self.screen.say("curfew_now", to=bedtime.clock_text(span[1]))
            if off:
                ctl.begin("poweroff", "curfew")

    # ------------------------------------------------------- reader mode
    def _configure_reader_mode(self) -> None:
        reader = getattr(self, "reader_mode", None)
        if reader is None:
            return
        wanted = self.cfg.get("display", "mode", "recalbox").strip().lower() == "reader"
        if frontend_lock.is_unlocked(self.home):
            wanted = False  # the "unlock" card shows Recalbox's interface
        no_hotkey = (self.cfg.get_bool("display", "no_quit_hotkey", False)
                     and self.cfg.get_bool("launch", "stop_on_remove", False))
        reader.preview = self.cfg.get_bool("display", "show_game", True)
        reader.confirm = (self.cfg.get("launch", "action", "launch").strip().lower() == "confirm"
                          or self.cfg.get_bool("display", "confirm_with_pad", False))  # setting of a test version
        reader.on_wait = self._game_waits
        reader.on_go = self._game_goes
        reader.on_cancel = self._game_given_up
        reader.configure(wanted, no_hotkey)

    # A game shown on the reader screen waits for the controller: its time
    # is not counted until it really starts.
    def _game_waits(self) -> None:
        controller = self.controller
        if controller is None:
            return
        if controller.playtime is not None:
            controller.playtime.pause()
        if controller.players is not None:
            controller.players.pause()

    def _game_goes(self) -> None:
        if self.controller is not None:
            self.controller.resume_time()

    def _game_given_up(self) -> None:
        if self.controller is not None:
            self.controller.stop_game("refused")

    def _reader_step(self) -> None:
        reader = getattr(self, "reader_mode", None)
        if reader is not None:
            reader.step()

    # ------------------------------------------------------ lock watchdog
    #: The Recalbox interface missing this long while the menu is locked:
    #: the lock is undone (a locked menu with nothing to show does not start).
    FRONTEND_MISSING_S = 120.0

    def _lock_watchdog(self) -> None:
        now = time.monotonic()
        if now < self._next_frontend_check:
            return
        self._next_frontend_check = now + 10.0
        reader = getattr(self, "reader_mode", None)
        if (self._unlock_busy or not frontend_lock.lock_active(self.home)
                or (reader is not None and reader.state != "recalbox")
                or frontend_lock.frontend_running()
                or (self.controller is not None and self.controller.game_running())):
            self._frontend_missing_since = None
            return
        if self._frontend_missing_since is None:
            self._frontend_missing_since = now
            return
        if now - self._frontend_missing_since < self.FRONTEND_MISSING_S:
            return
        self._frontend_missing_since = None
        self.log.warning("Menu verrouille et interface de la Recalbox absente depuis 2 min : deverrouillage de secours")
        self._unlock_busy = True

        def work():
            try:
                frontend_lock.apply(self.home, False)
                frontend_lock.forget_unlock(self.home)
                Config(os.path.join(self.home, "config.ini")).write_values({"players.lock_frontend": "0"})
                self.log.warning("Menu de la Recalbox deverrouille et relance (option desactivee)")
            except Exception as exc:  # noqa: BLE001 - never stops the service
                self.log.warning("Deverrouillage de secours impossible : %s" % exc)
            finally:
                self._unlock_busy = False

        threading.Thread(target=work, name="rfid-lock-rescue", daemon=True).start()

    # ----------------------------------------------------------- unlock card
    def _unlock_card(self) -> str:
        """The "unlock" card: opens the locked menu, or locks it again.

        The frontend restarts (a few seconds): done in the background, the
        reader keeps working. Refused while a game runs.
        """
        if self.controller is not None and self.controller.game_running():
            self.feedback.error()
            if self.light is not None:
                self.light.flash("error")
            self.log.info("Carte deverrouiller : quittez d'abord le jeu en cours")
            return "refused"
        if getattr(self, "players", None) is not None:
            self.players.release("carte deverrouiller")
        if self.cfg.get("display", "mode", "recalbox").strip().lower() == "reader":
            # Reader mode: the card shows Recalbox's interface, then the reader screen again.
            if frontend_lock.is_unlocked(self.home):
                frontend_lock.forget_unlock(self.home)
                self.log.info("Carte deverrouiller : retour a l'ecran du lecteur")
            else:
                try:
                    with open(os.path.join(self.home, frontend_lock.UNLOCK_FILENAME), "w", encoding="utf-8") as handle:
                        json.dump({"since": int(time.time())}, handle)
                except OSError as exc:
                    self.log.warning("Carte deverrouiller : %s" % exc)
                    return "failed"
                self.log.info("Carte deverrouiller : interface de Recalbox (tous les jeux)")
            self.feedback.ok()
            if self.light is not None:
                self.light.flash("ok")
            self._configure_reader_mode()
            return "unlock"
        if (not frontend_lock.is_unlocked(self.home) and not frontend_lock.lock_active(self.home)
                and not frontend_lock.is_locked()):
            self.feedback.error()
            if self.light is not None:
                self.light.flash("error")
            self.log.info("Carte deverrouiller : le menu n'est pas verrouille (option dans Reglages)")
            return "not_locked"
        self.feedback.ok()
        if self.light is not None:
            self.light.flash("ok")

        def work():
            self._unlock_busy = True
            try:
                result = frontend_lock.toggle_unlock(self.home, game_running=self.controller.game_running)
            except Exception as exc:  # noqa: BLE001 - never stops the service
                self.log.warning("Carte deverrouiller : %s" % exc)
                return
            finally:
                self._unlock_busy = False
            self.log.info("Carte deverrouiller : menu de la Recalbox %s"
                          % ("ouvert (tous les jeux)" if result == "unlocked" else "verrouille a nouveau"))

        threading.Thread(target=work, name="rfid-unlock", daemon=True).start()
        return "unlock"

    # --------------------------------------------------------------- new game
    #: Time given to the frontend to come back to its menu before a launch.
    NEW_GAME_RETRY_S = 10.0
    NEW_GAME_TRIES = 4

    def _start_new_game(self) -> bool:
        """Button double press with a game card on the reader: the game starts
        again from the beginning, for the same player.

        A RetroArch game is restarted in place (RESET, like the reset button of
        a console: instant, the session and the player go on). Otherwise the
        running game is quit without saving and started again.
        """
        uid = self._active_uid
        controller = self.controller
        if not uid or controller is None or controller.game_card(uid) is None:
            return False
        player = None
        players = getattr(self, "players", None)
        current = players.current if players is not None else None
        if current is not None and current.get("uid") not in ("", "guest"):
            player = (current["uid"], current["entry"])
        running = controller.game_running()
        if running and self._reset_in_place():
            self.feedback.ok()
            if self.light is not None:
                self.light.flash("ok")
            if getattr(self, "screen", None) is not None:
                self.screen.say("new_game")
            self.log.info("Double appui : la partie recommence au debut (RetroArch)")
            return True
        if running:
            controller.stop_game("new")
        self._skip_resume = True
        self._new_game = {"uid": uid, "player": player, "tries": 0,
                          "at": time.monotonic() + (self.NEW_GAME_RETRY_S if running else 0.0)}
        self.feedback.ok()
        if self.light is not None:
            self.light.flash("ok")
        self.log.info("Double appui : nouvelle partie pour le badge %s" % uid)
        return True

    def _reset_in_place(self) -> bool:
        """RetroArch game: restarted at once, the emulator keeps running."""
        reset = getattr(getattr(self, "launcher", None), "reset_command", None)
        if reset is None:
            return False
        try:
            return bool(reset())
        except Exception:  # noqa: BLE001 - the quit and relaunch still works
            return False

    def _new_game_step(self) -> None:
        """Starts the new game once the frontend is back to its menu."""
        job = self._new_game
        if job is None or time.monotonic() < job["at"]:
            return
        controller = self.controller
        if controller.game_running():
            if job["tries"]:
                self._new_game = None  # started
            else:
                job["at"] = time.monotonic() + 2.0  # the old game is still closing
            return
        if job["tries"] >= self.NEW_GAME_TRIES:
            self._new_game = None
            self._skip_resume = False
            self.log.warning("Nouvelle partie : le jeu n'a pas pu etre relance")
            return
        job["tries"] += 1
        job["at"] = time.monotonic() + self.NEW_GAME_RETRY_S
        if controller.new_game(job["uid"], job["player"]) == "launched":
            self._launched_uid = job["uid"]
        else:
            self._new_game = None
            self._skip_resume = False

    # ----------------------------------------------------------- commandes agent
    def _consume_agent_command(self) -> None:
        """Runs a command dropped by the WebSocket agent (JSON file)."""
        path = os.path.join(self.home, AGENT_COMMAND_FILENAME)
        try:
            info = os.stat(path)
        except OSError:
            return
        signature = (info.st_mtime, info.st_size)
        if signature == self._web_command_signature:
            return
        self._web_command_signature = signature
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            self.log.warning("Commande agent illisible : %s" % exc)
            return
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

        if not isinstance(payload, dict):
            return
        command = payload.get("cmd")
        if command == "arm_associate":
            self._forget_latch()
            self.controller.on_button("short")
        elif command == "arm_delete":
            self._forget_latch()
            self.controller.on_button("long")
        elif command == "arm_target":
            # Game chosen in the page (search), not on the TV.
            target = payload.get("target") or {}
            system = str(target.get("system") or "")
            path = str(target.get("path") or "")
            if system and path:
                self._forget_latch()
                self.controller.arm_target(Target(
                    system=system, game=relative_game_key(system, path) or path,
                    name=str(target.get("name") or ""), path=path))
        elif command == "arm_entry":
            entry = payload.get("entry")
            if isinstance(entry, dict):
                self._forget_latch()
                self.controller.arm_entry(entry)
        elif command == "calibrate_start":
            self._start_calibration()
        elif command == "calibrate_cancel":
            self._finish_calibration("cancelled")
        elif command == "calibrate_reset":
            self._reset_calibration_settings()
        elif command == "reader_test":
            self._start_reader_test(float(payload.get("seconds") or 5))
        elif command == "write_tag":
            self._start_tag_write(payload)
        elif command == "players_reset":
            if self.players is not None:
                self.players.reset(str(payload.get("uid") or ""))
                self._write_status(force=True)
        elif command == "screen_restart":
            reader = getattr(self, "reader_mode", None)
            if reader is not None:
                reader.restart_screen()
        elif command == "simulate_scan":
            uid = str(payload.get("uid") or "")
            if uid:
                self.controller.on_badge(uid)
        else:
            self.log.warning("Commande agent inconnue : %s" % command)

    # ------------------------------------------------- automatic tuning
    def _start_calibration(self) -> None:
        """Starts the reader measurement sequence (never blocking)."""
        self._calibration = {
            "phase": "speed",
            "instruct": "",
            "started_at": self._now_text(),
            "deadline": time.monotonic() + 30.0,
            "error": "",
            "measures": {
                "speeds": [],
                "best_speed": None,
                "read_ms": None,
                "reads": 0,
                "uids": [],
                "reqa_ok": 0,
                "wupa_ok": 0,
                "noise": 0,
                "absence_ms": None,
                "reinsert_ms": None,
            },
            "applied": {},
            "reader_ready": self.reader is not None,
        }
        self._calibration_signature = None
        if self.log:
            self.log.info("Reglage automatique du lecteur demande")
        self._publish_calibration()

    def _calibration_step(self) -> None:
        """Moves the sequence one step forward (called at each loop turn)."""
        etat = self._calibration
        if etat is None:
            return
        if self.reader is None:
            self._finish_calibration("no_reader")
            return
        phase = etat["phase"]
        try:
            if phase == "speed":
                self._calibration_speed(etat)
            elif phase == "read":
                self._calibration_read(etat)
            elif phase == "presence":
                self._calibration_presence(etat)
            elif phase == "remove":
                self._calibration_remove(etat)
            elif phase == "reinsert":
                self._calibration_reinsert(etat)
        except (Rc522Error, OSError) as exc:
            if self.log:
                self.log.warning("Reglage automatique interrompu : %s" % exc)
            self._finish_calibration("no_reader")
            return
        self._publish_calibration()

    # -- phase 1: which bus speed really holds? ----------------------------
    def _probe_speed(self, vitesse: int) -> bool:
        puce = None
        try:
            spi = open_spi(self.cfg.get("rfid", "spi_device", "/dev/spidev0.0"), vitesse)
            puce = Rc522(spi, self.log)
            reference = puce.begin()
            if reference in (0x00, 0xFF):
                return False
            for _ in range(40):
                if puce.read_version() != reference:
                    return False
            return True
        except Exception:  # noqa: BLE001 - a failing speed is ruled out
            return False
        finally:
            try:
                if puce is not None:
                    puce.close()
            except Exception:  # noqa: BLE001
                pass

    def _calibration_speed(self, etat) -> None:
        mesures = etat["measures"]
        meilleure = None
        for vitesse in calibration.SPEEDS:
            ok = self._probe_speed(vitesse)
            mesures["speeds"].append([vitesse, 1 if ok else 0])
            if ok:
                meilleure = vitesse
                break
        if meilleure is None:
            self._finish_calibration("spi_failed")
            return
        mesures["best_speed"] = meilleure
        # The probe touched the module registers: the service reader is
        # reset before going on.
        try:
            self.reader.start()
        except Exception as exc:  # noqa: BLE001
            if self.log:
                self.log.warning("Lecteur non reinitialise : %s" % exc)
            self._finish_calibration("no_reader")
            return
        etat["phase"] = "read"
        etat["instruct"] = "pose_badge"
        etat["deadline"] = time.monotonic() + 60.0

    # -- phase 2: real duration of a read (badge on the reader) ------------
    def _badge_is_there(self) -> bool:
        try:
            return self.reader.tag_present() is True
        except Exception:  # noqa: BLE001
            return False

    def _calibration_read(self, etat) -> None:
        if not self._badge_is_there():
            if time.monotonic() > etat["deadline"]:
                self._finish_calibration("timeout_pose")
            return
        mesures = etat["measures"]
        durees = []
        for _ in range(20):
            debut = time.monotonic()
            try:
                raw = self.reader.rc522.read_uid()
            except (Rc522Error, OSError):
                raw = None
            if raw:
                durees.append((time.monotonic() - debut) * 1000.0)
                uid = raw.hex().upper()
                if uid not in mesures["uids"]:
                    mesures["uids"].append(uid)
        if not durees:
            self._finish_calibration("badge_unreadable")
            return
        mesures["reads"] = len(durees)
        mesures["read_ms"] = round(sum(durees) / len(durees), 1)
        etat["phase"] = "presence"
        etat["instruct"] = "hold_badge"
        etat["deadline"] = time.monotonic() + 20.0

    # -- phase 3: do REQA and WUPA answer? ----------------------------
    def _calibration_presence(self, etat) -> None:
        if not self._badge_is_there():
            if time.monotonic() > etat["deadline"]:
                self._finish_calibration("no_badge")
            return
        mesures = etat["measures"]
        puce = self.reader.rc522
        reqa = wupa = 0
        for _ in range(20):
            try:
                if puce.request(PICC_REQA) is not None:
                    reqa += 1
            except (Rc522Error, OSError):
                pass
            try:
                if puce.request(PICC_WUPA) is not None:
                    wupa += 1
            except (Rc522Error, OSError):
                pass
        mesures["reqa_ok"] = reqa
        mesures["wupa_ok"] = wupa
        silences = 0
        for _ in range(10):
            try:
                if self.reader.tag_present() is False:
                    silences += 1
            except Exception:  # noqa: BLE001
                silences += 1
        mesures["noise"] = silences
        etat["phase"] = "remove"
        etat["instruct"] = "remove_badge"
        etat["deadline"] = time.monotonic() + 60.0
        etat["absence_since"] = None
        etat["absences"] = 0
        etat["repose_since"] = None

    # -- phase 4: removal latency (badge to remove) ------------------------
    def _calibration_remove(self, etat) -> None:
        maintenant = time.monotonic()
        try:
            verdict = self.reader.tag_present()
        except Exception:  # noqa: BLE001
            verdict = None
        if verdict is None:
            return
        if verdict:
            etat["absence_since"] = None
            etat["absences"] = 0
            if maintenant > etat["deadline"]:
                self._finish_calibration("timeout_remove")
            return
        if etat["absence_since"] is None:
            etat["absence_since"] = maintenant
        etat["absences"] = etat.get("absences", 0) + 1
        if etat["absences"] < 4:
            return
        etat["measures"]["absence_ms"] = round(
            (maintenant - etat["absence_since"]) * 1000.0
        )
        etat["phase"] = "reinsert"
        etat["instruct"] = "replace_badge"
        etat["deadline"] = time.monotonic() + 60.0
        etat["repose_since"] = None

    # -- phase 5: is the badge seen right away? ----------------------
    def _calibration_reinsert(self, etat) -> None:
        maintenant = time.monotonic()
        try:
            verdict = self.reader.tag_present()
        except Exception:  # noqa: BLE001
            verdict = None
        if verdict is None:
            return
        if not verdict:
            etat["repose_since"] = None
            if maintenant > etat["deadline"]:
                self._finish_calibration("timeout_replace")
            return
        if etat.get("repose_since") is None:
            etat["repose_since"] = maintenant
        try:
            raw = self.reader.rc522.read_uid()
        except (Rc522Error, OSError):
            raw = None
        if raw is None:
            if maintenant > etat["deadline"]:
                self._finish_calibration("timeout_replace")
            return
        etat["measures"]["reinsert_ms"] = round(
            (maintenant - etat["repose_since"]) * 1000.0
        )
        self._finish_calibration()

    # -- fin, application, publication ------------------------------------
    def _finish_calibration(self, erreur: str = "") -> None:
        """Ends the sequence: applies the measured settings, or nothing."""
        etat = self._calibration
        if etat is None:
            return
        if erreur:
            etat["phase"] = "error"
            etat["error"] = erreur
            etat["instruct"] = ""
            if self.log:
                self.log.info("Reglage automatique : %s" % calibration.error_text(erreur))
        else:
            reglages = calibration.settings_from(etat["measures"])
            etat["applied"] = self._apply_calibration_settings(reglages)
            etat["phase"] = "done"
            etat["instruct"] = ""
            if self.log:
                self.log.info(
                    "Reglage automatique applique : %s"
                    % ", ".join(
                        "%s %s -> %s" % (cle, valeurs[0], valeurs[1])
                        for cle, valeurs in sorted(etat["applied"].items())
                    )
                )
                mesures = etat["measures"]
                self.log.info(
                    "  mesures : %s, lecture %.0f ms, presence %s, retrait %s ms, repose %s ms"
                    % (
                        calibration.speed_label(mesures.get("best_speed")),
                        float(mesures.get("read_ms") or 0.0),
                        calibration.presence_verdict(mesures),
                        mesures.get("absence_ms"),
                        mesures.get("reinsert_ms"),
                    )
                )
        etat["finished"] = True
        self._calibration = None
        if self.reader is not None:
            self._arm_adoption()
        self._publish_calibration(etat)

    def _apply_calibration_settings(self, reglages: dict) -> dict:
        """Saves the measured values and reopens the reader at the right speed."""
        avant = {}
        for cle in reglages:
            section, nom = cle.split(".", 1)
            avant[cle] = self.cfg.get(section, nom)
        try:
            self._write_json(
                os.path.join(self.home, CALIBRATION_BACKUP_FILENAME),
                {"values": avant, "at": self._now_text()},
            )
            self.cfg.write_values(reglages)
        except Exception as exc:  # noqa: BLE001 - nothing must break
            if self.log:
                self.log.error("Reglages non enregistres : %s" % exc)
            return {}
        self.rearm_absent_ms = float(self.cfg.get_int("rfid", "rearm_absent_ms", 1200))
        if not self._reopen_reader_at_speed():
            # The measured speed misbehaves: back to the safe value.
            if self.log:
                self.log.warning(
                    "Vitesse %s inutilisable : retour a %s"
                    % (calibration.speed_label(reglages["rfid.spi_speed_hz"]),
                       calibration.speed_label(calibration.SPEED_FALLBACK))
                )
            self.cfg.write_values({"rfid.spi_speed_hz": str(calibration.SPEED_FALLBACK)})
            self._reopen_reader_at_speed()
            reglages["rfid.spi_speed_hz"] = str(calibration.SPEED_FALLBACK)
        return {cle: [avant[cle], reglages[cle]] for cle in reglages}

    def _reopen_reader_at_speed(self) -> bool:
        """Reopens the reader with the current configuration and checks it answers."""
        if self.reader is not None:
            try:
                self.reader.close()
            except Exception:  # noqa: BLE001
                pass
        self.reader = None
        if not self._open_reader():
            return False
        try:
            version = self.reader.rc522.read_version()
        except Exception:  # noqa: BLE001
            version = 0
        return bool(version) and version != 0xFF

    def _reset_calibration_settings(self) -> None:
        """Resets the three reader settings to their original values."""
        avant = {}
        for cle in calibration.DEFAULTS:
            section, nom = cle.split(".", 1)
            avant[cle] = self.cfg.get(section, nom)
        try:
            self.cfg.write_values(calibration.DEFAULTS)
        except Exception as exc:  # noqa: BLE001
            if self.log:
                self.log.error("Reinitialisation impossible : %s" % exc)
            return
        self.rearm_absent_ms = float(self.cfg.get_int("rfid", "rearm_absent_ms", 1200))
        self._reopen_reader_at_speed()
        if self.reader is not None:
            self._arm_adoption()
        if self.log:
            self.log.info(
                "Reglages du lecteur reinitialises : %s"
                % ", ".join(
                    "%s %s -> %s" % (cle, avant[cle], valeur)
                    for cle, valeur in sorted(calibration.DEFAULTS.items())
                )
            )
        self._publish_calibration(
            {
                "phase": "reset",
                "finished": True,
                "instruct": "",
                "error": "",
                "started_at": self._now_text(),
                "finished_at": self._now_text(),
                "reader_ready": self.reader is not None,
                "measures": {},
                "applied": {
                    cle: [avant[cle], valeur]
                    for cle, valeur in calibration.DEFAULTS.items()
                },
                "version": getattr(self.reader, "version", None),
            }
        )

    def _publish_calibration(self, etat: dict = None) -> None:
        """Writes the measurement state (read by the page through the agent)."""
        etat = self._calibration if etat is None else etat
        if etat is None:
            return
        payload = dict(etat)
        payload["steps"] = list(calibration.STEPS)
        payload["step"] = (
            calibration.STEPS.index(payload["phase"])
            if payload.get("phase") in calibration.STEPS else len(calibration.STEPS)
        )
        payload["total"] = len(calibration.STEPS)
        payload["finished"] = bool(payload.get("phase") in ("done", "error", "reset")
                                   or payload.get("finished"))
        payload["finished_at"] = payload.get("finished_at") or (
            self._now_text() if payload["finished"] else ""
        )
        payload["version"] = getattr(self.reader, "version", None)
        payload["defaults"] = dict(calibration.DEFAULTS)
        signature = json.dumps(payload, sort_keys=True, default=str)
        if signature == self._calibration_signature:
            return
        self._calibration_signature = signature
        self._write_json(os.path.join(self.home, CALIBRATION_FILENAME), payload)

    def _write_json(self, chemin: str, payload: dict) -> None:
        temporaire = chemin + ".tmp"
        try:
            with open(temporaire, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, default=str)
            os.replace(temporaire, chemin)
        except OSError as exc:
            if self.log:
                self.log.warning("Ecriture impossible (%s) : %s" % (chemin, exc))

    # ------------------------------------------------------- portable cards
    TAG_WRITE_S = 15.0

    def _tag_write_path(self) -> str:
        return os.path.join(self.home, TAG_WRITE_FILENAME)

    def _start_tag_write(self, payload: dict) -> None:
        """Waits for a badge, then writes its game into it (portable card)."""
        try:
            data = bytes.fromhex(str(payload.get("data") or ""))
        except ValueError:
            data = b""
        try:
            os.remove(self._tag_write_path())
        except OSError:
            pass
        if not data:
            self._write_json(self._tag_write_path(), {"state": "error", "message": "rien a ecrire"})
            return
        self._tag_write = {
            "uid": str(payload.get("uid") or "").upper(),
            "data": data,
            "deadline": time.monotonic() + self.TAG_WRITE_S,
            "next": 0.0,
            "error": "",
        }
        self._write_json(self._tag_write_path(), {"state": "waiting"})
        self.feedback.armed()
        if self.light is not None:
            self.light.flash("launch")
        self.log.info("Ecriture du jeu dans le badge %s demandee" % (self._tag_write["uid"] or "?"))

    def _tag_write_step(self) -> None:
        job = getattr(self, "_tag_write", None)
        if job is None:
            return
        now = time.monotonic()
        if now < job["next"]:
            return
        job["next"] = now + 0.3
        if self.reader is None:
            job["error"] = "lecteur indisponible"
        else:
            try:
                self.reader.write_memory(job["data"], job["uid"])
                written = self.reader.read_memory() or b""
                if not written.startswith(job["data"].rstrip(b"\x00")):
                    raise Rc522Error("la relecture ne correspond pas")
            except Rc522Error as exc:
                job["error"] = str(exc)
            else:
                self._tag_write = None
                self._arm_adoption()
                self.feedback.ok()
                if self.light is not None:
                    self.light.flash("ok")
                self._write_json(self._tag_write_path(), {"state": "done", "bytes": len(job["data"])})
                self.log.info("Jeu ecrit dans le badge %s (%d octets)" % (job["uid"], len(job["data"])))
                return
        if now >= job["deadline"]:
            self._tag_write = None
            self.feedback.error()
            if self.light is not None:
                self.light.flash("error")
            self._write_json(self._tag_write_path(), {"state": "error", "message": job["error"] or "aucun badge"})
            self.log.warning("Ecriture dans le badge abandonnee : %s" % (job["error"] or "aucun badge"))

    # ------------------------------------------------------------ reader test
    def _now_text(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

    def _start_reader_test(self, seconds: float) -> None:
        """Starts an RF test: one pass per loop turn, without blocking."""
        seconds = max(2.0, min(15.0, float(seconds or 5)))
        try:
            os.remove(os.path.join(self.home, READER_TEST_FILENAME))
        except OSError:
            pass
        self._reader_test = {
            "seconds": seconds,
            "until": time.monotonic() + seconds,
            "started_at": self._now_text(),
            "attempts": 0,
            "answers": 0,
            "reqa": 0,
            "wupa": 0,
            "atqas": {},
            "uids": [],
            "errors": [],
            "trace": {},
            "reader_ready": self.reader is not None,
        }
        if self.log:
            self.log.info("Test du lecteur demande (%.0f s)" % seconds)

    def _reader_test_step(self) -> None:
        test = self._reader_test
        if test is None:
            return
        if time.monotonic() >= test["until"]:
            self._finish_reader_test()
            return
        chip = getattr(self.reader, "rc522", None) if self.reader is not None else None
        if chip is None:
            test["reader_ready"] = False
            test["errors"].append("lecteur RC522 indisponible")
            self._finish_reader_test()
            return
        test["reader_ready"] = True
        test["attempts"] += 1
        trace = {"steps": []}
        try:
            raw = chip.read_uid(trace=trace)
        except (Rc522Error, OSError) as exc:
            if len(test["errors"]) < 6:
                test["errors"].append(str(exc))
            return
        if trace.get("steps"):
            test["trace"] = trace          # last meaningful attempt
        if raw:
            uid = raw.hex().upper()
            test["answers"] += 1
            if uid not in test["uids"]:
                test["uids"].append(uid)
            return
        # No complete UID: does the card answer at least (ATQA)?
        try:
            atqa = chip.request()
            if atqa:
                test["reqa"] += 1
            else:
                atqa = chip.request(PICC_WUPA)
                if atqa:
                    test["wupa"] += 1
        except (Rc522Error, OSError) as exc:
            if len(test["errors"]) < 6:
                test["errors"].append(str(exc))
            return
        if atqa:
            test["answers"] += 1
            key = bytes(atqa).hex().upper()
            test["atqas"][key] = test["atqas"].get(key, 0) + 1

    def _finish_reader_test(self) -> None:
        test = self._reader_test
        if test is None:
            return
        self._reader_test = None
        if self.reader is not None:
            self._arm_adoption()
        result = {
            "finished": True,
            "seconds": test["seconds"],
            "attempts": test["attempts"],
            "answers": test["answers"],
            "reqa": test["reqa"],
            "wupa": test["wupa"],
            "atqas": test["atqas"],
            "uids": test["uids"],
            "errors": test["errors"],
            "trace": test.get("trace") or {},
            "reader_ready": test["reader_ready"],
            "version": getattr(self.reader, "version", None),
            "started_at": test["started_at"],
            "finished_at": self._now_text(),
        }
        if self.log:
            self.log.info(
                "Test lecteur : %d essai(s), %d reponse(s), UID %s, ATQA %s"
                % (test["attempts"], test["answers"], test["uids"], sorted(test["atqas"]))
            )
            trace = test.get("trace") or {}
            for step in (trace.get("steps") or [])[:6]:
                self.log.info(
                    "  trame : envoi %s -> recu %s (ErrorReg %s)"
                    % (step.get("tx", ""), step.get("rx") or "rien", step.get("err", "?"))
                )
        path = os.path.join(self.home, READER_TEST_FILENAME)
        temporary = path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(result, handle)
            os.replace(temporary, path)
        except OSError as exc:
            if self.log:
                self.log.warning("Resultat du test lecteur non ecrit : %s" % exc)

    def _shutdown(self, lock: int) -> None:
        self.log.info("Arret du service")
        reader_mode = getattr(self, "reader_mode", None)
        if reader_mode is not None:
            try:
                reader_mode.shutdown()  # Recalbox's interface comes back
            except Exception as exc:  # noqa: BLE001
                self.log.warning("Retour a l'interface de Recalbox impossible : %s" % exc)
        if self.reader is not None:
            try:
                self.reader.close()
            except Exception:  # noqa: BLE001
                pass
        if self.light is not None:
            try:
                self.light.close()
            except Exception:  # noqa: BLE001
                pass
        if self.button is not None:
            try:
                self.button.close()
            except Exception:  # noqa: BLE001
                pass
        for path in (pid_path(self.home), status_path(self.home)):
            try:
                os.remove(path)
            except OSError:
                pass
        release_lock(lock)

    # ------------------------------------------------------------------ statut
    def _player_cards(self) -> list:
        cards = []
        if self.store is None:
            return cards
        try:
            items = self.store.items()
        except Exception:  # noqa: BLE001
            return cards
        for uid, entry in items:
            if entry.get("kind") == "action" and entry.get("action") == "player":
                cards.append((uid, entry))
        return cards

    def _players_status(self) -> dict:
        if getattr(self, "players", None) is None or self.controller is None                 or not getattr(self.controller, "counting_players", False):
            return {}
        status = self.players.status(self._player_cards())
        stored = avatars.versions(self.home)
        for row in status.get("players") or []:
            row["avatar"] = stored.get(str(row.get("uid") or "").upper(), 0)
        controller = self.controller
        if controller.guest_quota_min:
            left = controller.guest_left()
            status["guest"] = {"quota_min": controller.guest_quota_min, "period": controller.guest_period,
                               "remaining_s": int(left or 0)}
        return status

    def _players_signature(self):
        players = getattr(self, "players", None)
        if players is None:
            return None
        current = players.current
        return (
            current["uid"] if current else "",
            bool(players.pending),
            int(players.used_s(current["uid"]) // 60) if current else 0,
            self._avatars_stamp(),
        )

    def _avatars_stamp(self) -> int:
        """Changes when an avatar is added, replaced or removed (one stat)."""
        try:
            return int(os.stat(os.path.join(self.home, avatars.AVATARS_DIR)).st_mtime_ns)
        except OSError:
            return 0

    def _write_status(self, force: bool = False) -> None:
        """Writes status.json (only when useful: spares the SD card)."""
        controller_status = self.controller.status() if self.controller else {}
        signature = (
            self.last_uid,
            controller_status.get("mode", ""),
            controller_status.get("target"),
            round(controller_status.get("seconds_left") or 0),
            self.reader.version if self.reader else None,
            bool(self.button and getattr(self.button, "available", False)),
            self.store.count() if self.store else 0,
            int((self.playtime.remaining_s() or 0) // 15) if self.playtime else 0,
            self._players_signature(),
            frontend_lock.is_unlocked(self.home),
        )
        now = time.time()
        if not force and signature == self._status_signature and (now - self._status_written) < 30:
            return
        self._status_signature = signature
        self._status_written = now

        payload = {
            "version": __version__,
            "pid": os.getpid(),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.started_at)),
            "uptime_s": int(now - self.started_at),
            "reader": ("0x%02X" % self.reader.version) if (self.reader and self.reader.version) else "",
            "button": bool(self.button and getattr(self.button, "available", False)),
            "backend_gpio": getattr(self.gpio, "name", ""),
            "tags": self.store.count() if self.store else 0,
            "es_state": state_snapshot(read_state()),
            "last_uid": self.last_uid,
            "last_uid_at": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.last_uid_at))
                if self.last_uid_at
                else ""
            ),
            "controller": controller_status,
            "playtime": self.playtime.status() if self.playtime else {},
            "players": self._players_status(),
            "menu_unlocked": frontend_lock.is_unlocked(self.home),
            "command_check": es_command.summary(self.home),
            "display_mode": (self.cfg.get("display", "mode", "recalbox") if self.cfg else "recalbox").strip().lower(),
            "reader_screen": getattr(getattr(self, "reader_mode", None), "state", "recalbox") == "screen",
            "light": getattr(getattr(self.light, "output", None), "name", "none"),
        }
        write_json_atomic(status_path(self.home), payload)

    # ------------------------------------------------------------------ signaux
    def _install_signals(self) -> None:
        def stop_handler(signum, frame):  # noqa: ARG001 - signature imposee
            self.log.info("Signal %d recu : arret demande" % signum)
            self.running = False

        def reload_handler(signum, frame):  # noqa: ARG001
            self.log.info("Signal %d recu : rechargement de la configuration" % signum)
            try:
                self.cfg.reload()
                self.log.set_level(self.cfg.get("general", "log_level", "INFO"))
                if self.store:
                    self.store.load()
                if self.launcher is not None:
                    self.launcher.host = self.cfg.get("launch", "udp_host", "127.0.0.1")
                    self.launcher.port = self.cfg.get_int("launch", "udp_port", 1337)
                self._stop_on_remove = self.cfg.get_bool("launch", "stop_on_remove", False)
                # Reading settings: read again at each loop turn.
                self.rearm_absent_ms = float(self.cfg.get_int("rfid", "rearm_absent_ms", 1200))
                if self.reader is not None and hasattr(self.reader, "cooldown_s"):
                    self.reader.cooldown_s = max(
                        0.0, self.cfg.get_float("rfid", "same_tag_cooldown_s", 2.5)
                    )
                if self.button is not None and hasattr(self.button, "hold_press_s"):
                    self.button.hold_press_s = max(
                        0.3, self.cfg.get_float("button", "hold_press_s", 3.0)
                    )
                    self.button.debounce_s = max(
                        0.005, self.cfg.get_int("button", "debounce_ms", 40) / 1000.0
                    )
                if self.feedback is not None:
                    wanted = self.cfg.get_bool("feedback", "sound", True)
                    if wanted and not getattr(self.feedback, "_player", None):
                        self.feedback.enabled = True
                        self.feedback._detect_player()
                    else:
                        self.feedback.enabled = wanted and bool(getattr(self.feedback, "_player", None))
                if self.store and self.launcher and self.feedback:
                    self._build_extras()
                    # The running session and the armed mode survive the reload.
                    previous = self.controller
                    self._build_controller()
                    if previous is not None:
                        self.controller.launched_uid = previous.launched_uid
                self._configure_reader_mode()
                self.log.info(
                    "Configuration rechargee (%d badge(s))" % (self.store.count() if self.store else 0)
                )
            except Exception as exc:  # noqa: BLE001
                self.log.error("Rechargement impossible : %s" % exc)

        for name in ("SIGTERM", "SIGINT"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), stop_handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, reload_handler)


def run(config: Config, log: Logger, home: str = None, db: str = None) -> int:
    """Service entry point (called by the CLI and the userscript)."""
    return Service(config, log, home=home, db=db).run()
