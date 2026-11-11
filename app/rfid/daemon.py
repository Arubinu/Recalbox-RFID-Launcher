"""Service principal : boucle de lecture du lecteur et du bouton."""

from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import time

from . import __version__
from .config import Config
from .consts import AGENT_COMMAND_FILENAME, LOCK_FILE, db_path, home_dir
from .controller import Controller
from .esbridge import EsLauncher, supports_start_command
from .feedback import Feedback
from .hardware import build_button, build_gpio, build_reader
from .logutil import Logger
from .storage import TagStore

try:  # fcntl n'existe pas sous Windows (mode simulation sur PC)
    import fcntl
except ImportError:  # pragma: no cover - depend de la plateforme
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
    """Ecrit un petit fichier JSON de facon atomique."""
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
    """True si le PID existe et correspond bien a notre service."""
    if pid <= 0:
        return False
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            command = handle.read()
        return b"main.py" in command or b"rfid" in command
    except OSError:
        pass

    if os.name == "nt":  # developpement sur PC (pas de /proc)
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, 0, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:  # noqa: BLE001
            return False

    # Systemes POSIX sans /proc : existence du processus uniquement.
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
    """Verrou exclusif : empeche deux instances (ES relance les scripts permanents)."""
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
    """Assemble materiel, stockage et logique metier."""

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
        self.last_error_at = 0.0
        self.last_uid = ""
        self.last_uid_at = 0.0
        self.started_at = time.time()
        self._status_signature = None
        self._status_written = 0.0

    # ------------------------------------------------------------------ mise en place
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
        self._build_controller()
        return True

    def _build_controller(self) -> None:
        self.controller = Controller(
            self.store, self.launcher, self.feedback, self.cfg, self.log
        )

    def _open_reader(self) -> bool:
        try:
            self.reader = build_reader(self.cfg, self.log, self.gpio)
            self.reader.start()
            return True
        except Exception as exc:  # noqa: BLE001 - on retente plus tard
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
        except Exception as exc:  # noqa: BLE001 - configuration illisible, disque plein...
            self.log.error("Initialisation impossible : %s" % exc)
            self._shutdown(lock)
            return 2

        interval = max(0.02, self.cfg.get_int("rfid", "poll_interval_ms", 150) / 1000.0)
        next_slot = 0.0
        next_status = 0.0
        next_reader = 0.0
        try:
            while self.running:
                now = time.monotonic()

                # Le lecteur peut arriver plus tard (SPI active apres coup) : on
                # reessaie regulierement sans bloquer le bouton ni l'agent.
                if self.reader is None and now >= next_reader:
                    next_reader = now + 2.0
                    self._open_reader()
                    if self.reader is None:
                        self._write_status()

                if self.reader is not None and now >= next_slot:
                    next_slot = now + interval
                    uid = None
                    try:
                        uid = self.reader.read_uid()
                    except Exception as exc:  # noqa: BLE001
                        self.log.warning("Lecture RFID en echec : %s" % exc)
                    if uid:
                        self.last_uid = uid
                        self.last_uid_at = time.time()
                        self.controller.on_badge(uid)

                if self.button is not None:
                    gesture = self.button.poll()
                    if gesture:
                        self.controller.on_button(gesture)

                self._consume_agent_command()

                if self.controller.tick() == "expired":
                    self.log.info("Mode arme expire")

                try:
                    self.store.reload_if_changed()
                except Exception as exc:  # noqa: BLE001 - base modifiee a la main
                    self.log.warning("Relecture de la base impossible : %s" % exc)

                if now >= next_status:
                    next_status = now + 2.0
                    self._write_status()

                time.sleep(0.03)
        finally:
            self._shutdown(lock)
        return 0

    # ----------------------------------------------------------- commandes agent
    def _consume_agent_command(self) -> None:
        """Execute une commande deposee par l'agent WebSocket (fichier JSON)."""
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
            self.controller.on_button("short")
        elif command == "arm_delete":
            self.controller.on_button("long")
        elif command == "simulate_scan":
            uid = str(payload.get("uid") or "")
            if uid:
                self.controller.on_badge(uid)
        else:
            self.log.warning("Commande agent inconnue : %s" % command)

    def _shutdown(self, lock: int) -> None:
        self.log.info("Arret du service")
        if self.reader is not None:
            try:
                self.reader.close()
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
    def _write_status(self, force: bool = False) -> None:
        """Ecrit status.json (uniquement si utile : menage la carte SD)."""
        controller_status = self.controller.status() if self.controller else {}
        signature = (
            self.last_uid,
            controller_status.get("mode", ""),
            controller_status.get("target"),
            round(controller_status.get("seconds_left") or 0),
            self.reader.version if self.reader else None,
            bool(self.button and getattr(self.button, "available", False)),
            self.store.count() if self.store else 0,
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
            "last_uid": self.last_uid,
            "last_uid_at": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.last_uid_at))
                if self.last_uid_at
                else ""
            ),
            "controller": controller_status,
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
                if self.store and self.launcher and self.feedback:
                    self._build_controller()
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
    """Point d'entree du service (appele par le CLI et le userscript)."""
    return Service(config, log, home=home, db=db).run()
