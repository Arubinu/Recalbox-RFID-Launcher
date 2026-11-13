"""WebSocket agent: installation, update and management from `installer.html`.

Two ways to open the page:

* a plain HTML file opened on the PC (`file://`): it does not share the
  Recalbox origin, so `fetch()` would be blocked, whereas a `WebSocket` is
  allowed (the `null` origin of a local file is accepted);
* the same page served by this agent over plain HTTP (`GET /`), for phones
  and tablets: same origin, accepted only under a local name or an IP
  address (protection against DNS rebinding).

Everything comes from the standard library: HTTP handshake, RFC 6455 frames
and the service loop. Only a session authorized by a physical press can act.

Commands (JSON, one answer per `id`):

* ``pair.request`` / ``pair.check`` / ``pair.cancel`` (pairing confirmed with the button);
* ``auth`` (session secret), ``status``, ``version``, ``log``;
* ``install`` (share folder or URL), ``upload.begin/chunk/end`` (ZIP);
* ``tags.list/add/update/write/remove/export/import`` (``write``: the game
  is written into the badge itself, portable card);
* ``associate`` (selected game, game chosen in the page, special card, erase),
  ``scan`` (simulated badge);
* ``games.systems/search``, ``media.image/logo`` (game library, card designer);
* ``cards.templates``, ``cards.template.save/delete`` (card templates);
* ``service`` (start/stop/restart), ``reboot``.

Server -> client events: ``{"event": "log"}``, ``{"event": "install"}``,
``{"event": "restart_agent"}``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

from . import __version__
from . import pairing
from .consts import (
    AGENT_COMMAND_FILENAME,
    CALIBRATION_FILENAME,
    CONFIG_FILENAME,
    DB_FILENAME,
    READER_TEST_FILENAME,
    TAG_WRITE_FILENAME,
    TOKEN_FILENAME,
)
from . import access, bootcfg, portable
from .calibration import STEPS as CALIBRATION_STEPS
from .config import Config
from .daemon import process_alive, read_pid, read_status, recalbox_version, acquire_lock, release_lock
from .esbridge import read_state, resolve_rom_path, selected_target, supports_start_command
from .library import Library, LibraryError, relative_to_system
from .storage import StorageError, TagStore, normalize_uid, pretty_uid

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

#: Configuration reload signal (missing on Windows).
SIG_HUP = getattr(signal, "SIGHUP", 1)
MAX_MESSAGE = 4 * 1024 * 1024
MAX_UPLOAD = 64 * 1024 * 1024
AUTH_FAILURES = 3
AUTH_TIMEOUT = 20.0
DEFAULT_PORT = 8765
PAIRING_FILENAME = "pairing.json"
PAIRED_FILENAME = "paired.ok"
#: Session secret kept in the private folder (tmpfs, never the SMB share).
SESSION_FILENAME = "session-secret"
PAIRING_MINUTES = 15
USERSCRIPT = "/recalbox/share/userscripts/recalbox-rfid(permanent).py3"
AGENT_USERSCRIPT = "/recalbox/share/userscripts/recalbox-rfid-agent(permanent).py3"
#: Card templates saved from the page (shared by every computer and phone).
TEMPLATES_FILENAME = "card-templates.json"
MAX_TEMPLATES = 60
MAX_TEMPLATE_BYTES = 64 * 1024
#: Management page served to phones (built by tools/build_installer.py).
WEB_PAGES = ("web/index.html", "installer.html")
#: Host names accepted for the page served by the agent (DNS rebinding guard).
LOCAL_HOSTNAMES = ("recalbox", "recalbox.local", "localhost")


# ---------------------------------------------------------------------------
# Pairing: get the token without a network share or copy-paste
# ---------------------------------------------------------------------------
def is_private_address(address) -> bool:
    """True if the connection comes from the local network (pairing allowed)."""
    if isinstance(address, (tuple, list)):
        address = address[0] if address else ""
    host = str(address or "").split("%")[0].strip()
    if host.startswith("::ffff:"):
        host = host[7:]
    if host in ("", "::1", "localhost"):
        return True
    if host.startswith(("127.", "10.", "192.168.")):
        return True
    if host.startswith("172."):
        try:
            return 16 <= int(host.split(".")[1]) <= 31
        except (IndexError, ValueError):
            return False
    # IPv6 link-local and unique local (fd00::/8, fc00::/7)
    return host.startswith(("fe80:", "fd", "fc"))


def pairing_path(home: str) -> str:
    # Same private folder as the pairing states: never the SMB share.
    return os.path.join(pairing.state_dir(home), PAIRING_FILENAME)


def open_pairing_window(home: str, minutes: int = PAIRING_MINUTES) -> float:
    """Opens a (single use) pairing window and returns its deadline."""
    os.makedirs(home, exist_ok=True)
    until = time.time() + max(1, int(minutes)) * 60
    try:
        with open(pairing_path(home), "w", encoding="utf-8") as handle:
            json.dump({"until": until}, handle)
    except OSError:
        pass
    return until


def close_pairing_window(home: str) -> None:
    try:
        os.remove(pairing_path(home))
    except OSError:
        pass


def pairing_is_open(home: str) -> bool:
    try:
        # utf-8-sig: tolerates the BOM a Windows editor may add.
        with open(pairing_path(home), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return float(data.get("until") or 0) > time.time()
    except (OSError, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Program version and source folder
# ---------------------------------------------------------------------------
def read_version(folder: str) -> str:
    """Version given by the VERSION file of a folder (or an empty string)."""
    try:
        with open(os.path.join(folder, "VERSION"), "r", encoding="utf-8-sig") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def version_key(text: str):
    """Version comparison key: (1, 8, 2) for "1.8.2", () when empty."""
    raw = str(text or "").strip()
    if not raw:
        return ()
    parts = []
    for chunk in raw.split("."):
        digits = "".join(car for car in chunk if car.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def find_source(share: str = "/recalbox/share", home: str = None):
    """Looks for the project folder (app/main.py + install.sh) on the share."""
    import glob

    home = os.path.abspath(home) if home else None
    patterns = (
        os.path.join(share, "*", "app", "main.py"),
        os.path.join(share, "*", "*", "app", "main.py"),
        os.path.join(share, "*", "*", "*", "app", "main.py"),
    )
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            folder = os.path.dirname(os.path.dirname(os.path.abspath(candidate)))
            if home and folder == home:
                continue
            if os.path.isfile(os.path.join(folder, "install.sh")):
                return folder
    return None


# ---------------------------------------------------------------------------
# Trames RFC 6455
# ---------------------------------------------------------------------------
class ProtocolError(Exception):
    pass


class _Client:
    """One client connection: read buffer, serialized sending, state."""

    def __init__(self, sock, address):
        self.sock = sock
        self.address = address
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.authenticated = False
        self.failures = 0
        self.upload = None
        self.upload_size = 0
        self.tempdir = None

    # ---------------------------------------------------------------- lecture
    def read(self, count: int) -> bytes:
        while len(self.buffer) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("connexion fermee")
            self.buffer.extend(chunk)
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def send(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self.lock:
            try:
                _send_frame(self.sock, 0x1, data)
            except OSError:
                pass

    def close(self) -> None:
        try:
            _send_frame(self.sock, 0x8, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        if self.tempdir:
            import shutil

            shutil.rmtree(self.tempdir, ignore_errors=True)
            self.tempdir = None


def _recv_exact(client: _Client, count: int) -> bytes:
    return client.read(count)


def _read_frame(client: _Client):
    first = _recv_exact(client, 2)
    fin = bool(first[0] & 0x80)
    opcode = first[0] & 0x0F
    masked = bool(first[1] & 0x80)
    length = first[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(client, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(client, 8))[0]
    if length > MAX_MESSAGE:
        raise ProtocolError("message trop volumineux")
    mask = _recv_exact(client, 4) if masked else b""
    payload = _recv_exact(client, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return fin, opcode, payload


def _read_message(client: _Client, on_control=None):
    """Reads a whole message and returns ``(opcode, payload)``.

    Browsers (Chromium in particular) split large messages into several
    frames: a first text frame without the FIN bit, then continuation frames
    (opcode 0). Reading them one by one gave a truncated JSON, and sending a
    ZIP from the page never got an answer. Control frames (ping, pong) may be
    interleaved between fragments (RFC 6455, 5.4): they are handed to
    ``on_control``. A close frame is returned as is.
    """
    message_opcode = None
    parts = []
    size = 0
    while True:
        fin, opcode, payload = _read_frame(client)
        if opcode >= 0x8:
            if opcode == 0x8:
                return opcode, payload
            if on_control is not None:
                on_control(opcode, payload)
            continue
        if opcode == 0x0:
            if message_opcode is None:
                raise ProtocolError("trame de continuation sans debut de message")
        else:
            if message_opcode is not None:
                raise ProtocolError("nouveau message avant la fin du precedent")
            message_opcode = opcode
        parts.append(payload)
        size += len(payload)
        if size > MAX_MESSAGE:
            raise ProtocolError("message trop volumineux")
        if fin:
            return message_opcode, b"".join(parts)


def _send_frame(sock, opcode: int, payload: bytes) -> None:
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += struct.pack("!H", length)
    else:
        header.append(127)
        header += struct.pack("!Q", length)
    sock.sendall(bytes(header) + payload)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class Agent:
    """WebSocket server and management logic."""

    def __init__(self, cfg, log, home: str, source: str = None, db: str = None, port: int = None):
        self.cfg = cfg
        self.log = log
        self.home = os.path.abspath(home)
        self.source = os.path.abspath(source) if source else None
        self.db_path = db or os.path.join(self.home, DB_FILENAME)
        self.port = int(port) if port is not None else cfg.get_int("agent", "port", DEFAULT_PORT)
        # No secret on the SMB share: authorization comes from a physical press
        # on the button, and the session secret lives in a private folder (0600,
        # tmpfs). It therefore survives a restart of the service or of the agent
        # (update), but not a reboot of the Recalbox.
        self.token = self._session_secret()
        self.token_path = ""
        self._forget_legacy_tokens()
        # New secret at each start: the pairing window stays open until a
        # computer is authorized (3 s press on the button).
        open_pairing_window(self.home)
        self._store = TagStore(self.db_path, log)
        self._store_guard = threading.Lock()
        self.library = Library(log=log)
        self._templates_guard = threading.Lock()
        #: Connected clients (to log out the others when the password changes).
        self._clients = set()
        self._clients_guard = threading.Lock()
        #: Requests granted by the button that still wait for the password.
        self._awaiting_password = {}
        self._install_lock = threading.Lock()
        self._install_running = False
        self.server = None
        self.running = False
        self._lock = None

    def _session_secret(self) -> str:
        """Session secret: read back from the private folder, or created."""
        path = os.path.join(pairing.state_dir(self.home), SESSION_FILENAME)
        saved = ""
        try:
            with open(path, "r", encoding="ascii") as handle:
                saved = handle.read().strip()
        except OSError:
            saved = ""
        token = saved if len(saved) >= 32 else secrets.token_hex(16).upper()
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                handle.write(token)
        except OSError:
            pass                     # disk full: the secret stays in memory
        return token

    def rotate_secret(self, keep=None) -> str:
        """New session secret: every other device must be authorized again."""
        path = os.path.join(pairing.state_dir(self.home), SESSION_FILENAME)
        try:
            os.remove(path)
        except OSError:
            pass
        self.token = self._session_secret()
        with self._clients_guard:
            for other in self._clients:
                if other is not keep:
                    other.authenticated = False
        return self.token

    def register(self, client) -> None:
        with self._clients_guard:
            self._clients.add(client)

    def unregister(self, client) -> None:
        with self._clients_guard:
            self._clients.discard(client)

    def web_enabled(self) -> bool:
        """Page for phones (and same-origin connections) allowed by the settings."""
        try:
            return Config(self.config_path()).get_bool("agent", "web", True)
        except Exception:  # noqa: BLE001 - unreadable file: keep the default
            return True

    def _forget_legacy_tokens(self) -> None:
        """Deletes the tokens of previous versions (they lived on the share)."""
        candidates = (
            os.path.join(self.home, TOKEN_FILENAME),
            os.path.join("/overlay/rfid", TOKEN_FILENAME),
            os.path.join(self.home, PAIRED_FILENAME),
        )
        for path in candidates:
            try:
                os.remove(path)
            except OSError:
                continue
            if self.log:
                self.log.warning("Ancien jeton supprime : %s" % path)

    # ------------------------------------------------------------------ cycle
    def serve_forever(self) -> int:
        if not self.cfg.get_bool("agent", "enabled", True):
            if self.log:
                self.log.info("Agent WebSocket desactive dans la configuration")
            return 0
        self._lock = acquire_lock(os.path.join("/var/run", "recalbox-rfid-agent.lock"))
        if self._lock == 0:
            if self.log:
                self.log.info("Agent deja en cours d'execution : abandon")
            return 0
        os.makedirs(self.home, exist_ok=True)
        try:
            server = _Server(("0.0.0.0", self.port), _Handler, self)
        except OSError as exc:
            if self.log:
                self.log.error(
                    "Agent WebSocket impossible sur le port %d : %s "
                    "(changez 'port' dans [agent])" % (self.port, exc)
                )
            release_lock(self._lock)
            return 1
        self.server = server
        self.running = True
        if self.log:
            self.log.info(
                "Agent WebSocket pret sur ws://%s:%d (autorisation : appui de 3 s sur le bouton)"
                % (_local_ip(), self.port)
            )
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            try:
                server.server_close()
            except OSError:
                pass
            release_lock(self._lock)
        return 0

    def stop(self) -> None:
        self.running = False
        if self.server is not None:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    # ------------------------------------------------------------------ outils
    def installer(self):
        """Install script to run.

        The project folder on the share comes first (it carries the new version),
        but never at the expense of a newer version already installed: otherwise
        "Install / update" would do nothing or downgrade the program.
        """
        source = self.source
        if not source:
            try:
                source = find_source(home=self.home)
            except Exception:  # noqa: BLE001 - share missing or unreadable
                source = None
        installed = os.path.join(self.home, "install.sh")
        if source:
            shared = os.path.join(source, "install.sh")
            if os.path.isfile(shared):
                partage = version_key(read_version(source))
                local = version_key(read_version(self.home))
                if not partage or not local or partage >= local:
                    return shared
        return installed if os.path.isfile(installed) else None

    def main_py(self) -> str:
        return os.path.join(self.home, "app", "main.py")

    def config_path(self) -> str:
        return os.path.join(self.home, CONFIG_FILENAME)

    def web_page(self):
        """Management page to serve to phones (or None)."""
        for relative in WEB_PAGES:
            path = os.path.join(self.home, relative)
            if os.path.isfile(path):
                return path
        return None

    def _tags(self) -> TagStore:
        with self._store_guard:
            self._store.reload_if_changed()
            return self._store

    def _write_command(self, command: str, **extra) -> None:
        path = os.path.join(self.home, AGENT_COMMAND_FILENAME)
        payload = {"cmd": command, "ts": time.time()}
        payload.update(extra)
        temporary = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, path)

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        pid = read_pid(self.home)
        running = process_alive(pid)
        installed = os.path.isfile(self.main_py())
        installed_version = ""
        try:
            with open(os.path.join(self.home, "VERSION"), "r", encoding="utf-8") as handle:
                installed_version = handle.read().strip()
        except OSError:
            pass
        # allow_running: the frontend keeps State=playing on a game's page
        # (and right after leaving a game); the display must show it.
        target, remembered = selected_target(read_state(), allow_running=True)
        frontend = supports_start_command() if os.path.exists("/usr/bin/emulationstation") else None
        return {
            "app_version": __version__,
            "home": self.home,
            "source": self.source,
            "installed": installed,
            "installed_version": installed_version,
            "source_version": self.source_version(self.installer()),
            "recalbox": recalbox_version(),
            "spi": os.path.exists("/dev/spidev0.0"),
            "userscript": os.path.isfile(USERSCRIPT) or os.path.isfile(AGENT_USERSCRIPT),
            "frontend": frontend,
            "service": {
                "running": running,
                "pid": pid,
                "status": read_status(self.home) if running else None,
            },
            "tags": self._tags().count(),
            "current": (
                {
                    "system": target.system,
                    "game": target.game,
                    "name": target.name,
                    "path": target.path,
                    "remembered": remembered,
                }
                if target
                else None
            ),
            "install": {"running": self._install_running},
            "agent": {
                "port": self.port,
                "session": bool(self.token),
                "pairing": pairing_is_open(self.home),
                "ip": lan_ip(),
                "web": self.web_page() is not None,
            },
        }

    # ------------------------------------------------------------- installation
    def start_install(self, client: _Client, command) -> None:
        with self._install_lock:
            if self._install_running:
                raise RuntimeError("une installation est deja en cours")
            self._install_running = True
        threading.Thread(target=self._install_job, args=(client, command), daemon=True).start()

    def _install_job(self, client: _Client, command) -> None:
        client.send({"event": "install", "state": "running"})
        code = -1
        output = []
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:  # type: ignore[union-attr]
                line = line.rstrip("\n")
                output.append(line)
                client.send({"event": "log", "line": line})
            code = process.wait()
        except OSError as exc:
            output.append(str(exc))
            client.send({"event": "log", "line": str(exc)})
        finally:
            self._install_running = False
            client.send({"event": "install", "state": "ok" if code == 0 else "error", "code": code})
            self._append_install_log(output)
            if self.log:
                self.log.info("Installation via agent terminee (code %s)" % code)
            if code == 0:
                self._after_install(client)

    def _restart_service(self) -> None:
        """Restarts the service so that it loads the freshly installed code.

        ``install.sh`` is called with ``--no-restart``: without this restart, the
        service kept running the old code (and so did not know the new commands)
        until the next reboot.
        """
        programme = self.main_py()
        if not os.path.isfile(programme):
            return
        action = "restart" if process_alive(read_pid(self.home)) else "start"
        try:
            subprocess.run(
                [sys.executable, programme, action, "--home", self.home],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=45,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            if self.log:
                self.log.warning("Relance du service apres installation impossible : %s" % exc)
            return
        if self.log:
            self.log.info("Service relance apres installation (%s)" % action)

    def _after_install(self, client: _Client) -> None:
        # The service must restart with the new code (the agent re-executes itself).
        self._restart_service()
        client.send({"event": "restart_agent", "in": 2})
        threading.Timer(2.0, self._reexec).start()

    def _reexec(self) -> None:
        """Reloads the agent with the freshly installed code."""
        if "agent" not in sys.argv[1:3]:
            # Safety: never replace another program (tests, CLI...).
            if self.log:
                self.log.info("Rechargement de l'agent ignore (processus non-agent)")
            return
        target = self.main_py() if os.path.isfile(self.main_py()) else os.path.join(self.source or "", "app", "main.py")
        if not os.path.isfile(target):
            return
        if self.log:
            self.log.info("Redemarrage de l'agent apres installation")
        try:
            os.execv(sys.executable, [sys.executable, target, "agent", "--home", self.home])
        except OSError as exc:
            if self.log:
                self.log.error("Redemarrage de l'agent impossible : %s" % exc)

    def _append_install_log(self, lines) -> None:
        if not lines:
            return
        path = os.path.join(self.home, "logs", "install.log")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.isfile(path) and os.path.getsize(path) > 200000:
                os.replace(path, path + ".1")
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                handle.write("\n".join(lines) + "\n")
        except OSError:
            pass

    # --------------------------------------------------------------- commandes
    def process(self, client: _Client, message: dict) -> bool:
        """Handles a message; returns False to close the connection."""
        if not isinstance(message, dict):
            client.send({"ok": False, "error": "objet JSON attendu"})
            return True
        request_id = message.get("id")
        command = str(message.get("cmd") or "").strip()

        if command == "pair":
            client.send({
                "id": request_id,
                "ok": False,
                "error": "appairage par fichier supprime : utilisez pair.request puis "
                         "l'appui de 3 s sur le bouton",
            })
            return True

        if command in ("pair.request", "pair.check", "pair.cancel", "pair.password"):
            return self._handle_pairing(client, request_id, command, message)

        if command == "auth":
            if secrets.compare_digest(str(message.get("token") or ""), self.token):
                client.authenticated = True
                close_pairing_window(self.home)
                client.send(
                    {
                        "id": request_id,
                        "ok": True,
                        "data": {"authenticated": True, "version": __version__},
                    }
                )
                return True
            client.failures += 1
            client.send({"id": request_id, "ok": False, "error": "session non autorisee : refaites l'appairage (appui de 3 s)"})
            if client.failures >= AUTH_FAILURES:
                if self.log:
                    self.log.warning("Agent : trop d'echecs d'authentification (%s)" % (client.address,))
                return False
            return True

        if not client.authenticated:
            client.failures += 1
            client.send({"id": request_id, "ok": False, "error": "authentification requise"})
            return client.failures < AUTH_FAILURES

        handler = getattr(self, "_cmd_" + command.replace(".", "_").replace("-", "_"), None)
        if handler is None:
            client.send({"id": request_id, "ok": False, "error": "commande inconnue : %s" % command})
            return True
        try:
            data = handler(client, message) or {}
            client.send({"id": request_id, "ok": True, "data": data})
        except ValueError as exc:
            client.send({"id": request_id, "ok": False, "error": str(exc)})
        except RuntimeError as exc:
            client.send({"id": request_id, "ok": False, "error": str(exc)})
        except StorageError as exc:
            client.send({"id": request_id, "ok": False, "error": "badge invalide : %s" % exc})
        except Exception as exc:  # noqa: BLE001 - the agent must never crash
            if self.log:
                self.log.error("Agent : erreur sur %s : %s" % (command, exc))
            client.send({"id": request_id, "ok": False, "error": "erreur interne : %s" % exc})
        return True

    # ------------------------------------------------------------- appairage
    def _handle_pairing(self, client, request_id, command, message) -> bool:
        """Pairing confirmed with the button: request, wait, session secret.

        No authentication (that is the point), but three safeguards: local network
        only, a single request at a time, and validation by a long press on the
        Recalbox physical button.
        """
        source = getattr(client, "address", "")
        if not is_private_address(source):
            client.send({
                "id": request_id,
                "ok": False,
                "error": "appairage refuse : adresse hors du reseau local",
            })
            return True

        try:
            if command == "pair.request":
                if not process_alive(read_pid(self.home)):
                    client.send({
                        "id": request_id,
                        "ok": False,
                        "error": "le service RFID n'est pas demarre : demarrez-le dans "
                                 "l'onglet Maintenance, puis reessayez",
                    })
                    return True
                request = pairing.create_request(self.home, source=str(source))
                if self.log:
                    self.log.info(
                        "Appairage : demande %s (appui de %.0f s sur le bouton attendu)"
                        % (request["id"], pairing.CONFIRM_HOLD_S)
                    )
                client.send({
                    "id": request_id,
                    "ok": True,
                    "data": {
                        "request": request["id"],
                        "seconds": int(max(0.0, request["until"] - time.time())),
                        "hold": pairing.CONFIRM_HOLD_S,
                    },
                })
                return True

            if command == "pair.password":
                return self._pair_password(client, request_id, message)

            if command == "pair.check":
                wanted = str(message.get("request") or "").strip()
                if pairing.take_grant(self.home, wanted):
                    if self.log:
                        self.log.warning("Appairage : demande %s acceptee au bouton" % wanted)
                    if access.has_password(self.home):
                        # The press is not enough: the password comes next.
                        self._awaiting_password[wanted] = {"until": time.time() + 120.0, "tries": 0}
                        client.send({
                            "id": request_id,
                            "ok": True,
                            "data": {"accepted": True, "password": True},
                        })
                        return True
                    client.send({
                        "id": request_id,
                        "ok": True,
                        "data": {"accepted": True, "token": self.token},
                    })
                    return True
                current = pairing.pending(self.home)
                remaining = 0
                if current:
                    remaining = int(max(0.0, float(current.get("until", 0)) - time.time()))
                client.send({
                    "id": request_id,
                    "ok": True,
                    "data": {
                        "accepted": False,
                        "pending": bool(current) and str(current.get("id")) == wanted,
                        "seconds": remaining,
                    },
                })
                return True

            pairing.cancel(self.home)
            client.send({"id": request_id, "ok": True, "data": {"cancelled": True}})
            return True
        except pairing.PairingError as exc:
            client.send({"id": request_id, "ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - the agent must never crash
            if self.log:
                self.log.error("Appairage : erreur sur %s : %s" % (command, exc))
            client.send({"id": request_id, "ok": False, "error": "appairage impossible : %s" % exc})
        return True

    PASSWORD_TRIES = 5
    #: Pause after a wrong password (slows down guessing).
    PASSWORD_DELAY_S = 1.0

    def _pair_password(self, client, request_id, message) -> bool:
        """Second step of the pairing when a password is set."""
        wanted = str(message.get("request") or "").strip()
        waiting = self._awaiting_password.get(wanted)
        if waiting is None or waiting["until"] < time.time():
            self._awaiting_password.pop(wanted, None)
            client.send({"id": request_id, "ok": False,
                         "error": "demande expiree : recommencez avec le bouton"})
            return True
        if access.check(self.home, str(message.get("password") or "")):
            self._awaiting_password.pop(wanted, None)
            if self.log:
                self.log.warning("Appairage : mot de passe correct (demande %s)" % wanted)
            client.send({"id": request_id, "ok": True, "data": {"accepted": True, "token": self.token}})
            return True
        waiting["tries"] += 1
        time.sleep(self.PASSWORD_DELAY_S)
        left = self.PASSWORD_TRIES - waiting["tries"]
        if left <= 0:
            self._awaiting_password.pop(wanted, None)
            if self.log:
                self.log.warning("Appairage : trop d'essais de mot de passe (demande %s)" % wanted)
            client.send({"id": request_id, "ok": False,
                         "error": "trop d'essais : recommencez avec le bouton"})
            return True
        client.send({"id": request_id, "ok": False,
                     "error": "mot de passe incorrect (encore %d essai%s)" % (left, "s" if left > 1 else "")})
        return True

    # ---------------------------------------------------------- password
    def _cmd_access_status(self, client, message):
        return {"password": access.has_password(self.home)}

    def _cmd_access_set(self, client, message):
        """Sets or changes the password; the other devices are logged out."""
        if access.has_password(self.home) and not access.check(self.home, str(message.get("current") or "")):
            time.sleep(self.PASSWORD_DELAY_S)
            raise ValueError("mot de passe actuel incorrect")
        try:
            access.set_password(self.home, str(message.get("password") or ""))
        except access.AccessError as exc:
            raise ValueError(str(exc))
        token = self.rotate_secret(keep=client)
        if self.log:
            self.log.warning("Mot de passe de la page defini : les autres appareils sont deconnectes")
        return {"password": True, "token": token}

    def _cmd_access_clear(self, client, message):
        if not access.check(self.home, str(message.get("current") or "")):
            time.sleep(self.PASSWORD_DELAY_S)
            raise ValueError("mot de passe actuel incorrect")
        access.clear_password(self.home)
        if self.log:
            self.log.warning("Mot de passe de la page retire")
        return {"password": False}

    # ------------------------------------------------------------- diagnostic
    def _cmd_diag(self, client, message):
        """Read-only system diagnostic (useful when there is no SSH).

        Mainly helps understand why the SPI bus is not active: content of
        ``/boot``, presence of ``/dev/spidev*`` and the Recalbox overlay sync
        mechanism.
        """
        commands = [
            ("version", "cat /recalbox/recalbox.version 2>&1"),
            ("uname", "uname -a 2>&1"),
            ("modele", "cat /proc/device-tree/model 2>&1; echo; "
                       "grep -m2 -E '^(Model|Hardware|Revision)' /proc/cpuinfo 2>&1"),
            ("boot_files", "ls -l /boot/config.txt /boot/cmdline.txt /boot/recalbox-user-config.txt "
                           "/boot/recalbox-boot.conf 2>&1"),
            ("boot_config", "cat /boot/config.txt 2>&1"),
            ("boot_config_spi", "grep -n -i -E 'spi|include|recalbox-user' /boot/config.txt 2>&1 | head -30"),
            ("user_config_spi", "grep -n -i spi /boot/recalbox-user-config.txt 2>&1 | head -20"),
            ("boot_conf_spi", "grep -n -i spi /boot/recalbox-boot.conf 2>&1 | head -20"),
            ("spidev", "ls -l /dev/spidev* 2>&1"),
            ("spi_devices", "ls /sys/bus/spi/devices 2>&1; "
                            "cat /sys/bus/spi/devices/*/modalias 2>&1"),
            ("gpio", "ls -l /dev/gpiochip* 2>&1; command -v gpiodetect gpioinfo gpioget gpioset 2>&1; "
                     "python3 -c 'import RPi.GPIO as g; print(\"RPi.GPIO\", g.VERSION)' 2>&1 | head -3; "
                     "python3 -c 'import lgpio; print(\"lgpio ok\")' 2>&1 | head -3; "
                     "ls -d /usr/lib/python3*/site-packages 2>&1 | head; "
                     "cat /sys/class/gpio/gpiochip0/label 2>&1"),
            ("gpio_home", "echo HOME=$HOME PWD=$PWD; "
                          "cd /tmp && HOME=/tmp python3 -c 'import lgpio; print(\"lgpio\", lgpio.version)' 2>&1 | tail -2; "
                          "cd /tmp && HOME=/tmp python3 -c 'import RPi.GPIO as g; g.setmode(g.BCM); "
                          "g.setup(17, g.IN, pull_up_down=g.PUD_UP); print(\"pin17=\", g.input(17)); g.cleanup()' 2>&1 | tail -4"),
            ("dmesg_spi", "dmesg 2>&1 | grep -i -E 'spi|spidev|mcp' | tail -25"),
            ("modules_spi", "grep -i spi /proc/modules 2>&1 | head; "
                            "ls /lib/modules/$(uname -r)/kernel/drivers/spi 2>&1 | head"),
            ("mounts", "mount | grep -i -E 'boot|mmcblk' 2>&1"),
            ("overlaysync", "ls -l /etc/init.d/S99overlaysync 2>&1; "
                            "head -50 /etc/init.d/S99overlaysync 2>&1"),
        ]
        output = {}
        for name, command in commands:
            try:
                result = subprocess.run(
                    ["sh", "-c", command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=15,
                    text=True,
                )
                output[name] = ((result.stdout or "").strip() or "(vide)")[:2000]
            except Exception as exc:  # noqa: BLE001 - a diagnostic must never crash
                output[name] = "erreur : %s" % exc
        return {"spi": os.path.exists("/dev/spidev0.0"), "commands": output}

    # ------------------------------------------------------- commandes simples
    def _cmd_status(self, client, message):
        return self.status()

    def _cmd_version(self, client, message):
        return {"version": __version__}

    def _cmd_log(self, client, message):
        name = str(message.get("name") or "service")
        count = min(int(message.get("lines") or 200), 2000)
        filenames = {
            "service": os.path.join(self.home, "logs", "rfid.log"),
            "install": os.path.join(self.home, "logs", "install.log"),
            "agent": os.path.join(self.home, "logs", "agent.log"),
            "startup": os.path.join(self.home, "logs", "service.out"),
        }
        filename = filenames.get(name)
        if not filename:
            raise ValueError("journal inconnu : %s" % name)
        try:
            with open(filename, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()[-count:]
        except OSError:
            return {"text": "(journal vide : %s)" % filename}
        return {"text": "".join(lines)}

    def source_version(self, installer: str) -> str:
        """Version of the folder the installer comes from."""
        if not installer:
            return ""
        return read_version(os.path.dirname(os.path.abspath(installer)))

    def up_to_date(self, installer: str):
        """Nothing to install if the disk AND the service are already up to date.

        Returns a ``{"skipped": True, ...}`` dict in that case, otherwise None.
        A service still running an older version prevents the skip: the install
        must be applied again so that it restarts up to date.
        """
        source = self.source_version(installer)
        installed = read_version(self.home)
        if not source or not installed:
            return None
        if version_key(installed) != version_key(source):
            return None                  # real version upgrade or downgrade
        status = read_status(self.home) or {}
        service = str(status.get("version") or "")
        if not service or version_key(service) != version_key(installed):
            return None                  # the service does not have this code yet
        return {
            "skipped": True,
            "installed_version": installed,
            "source_version": source,
            "service_version": service,
        }

    def _cmd_install(self, client, message):
        installer = self.installer()
        if installer is None:
            raise RuntimeError(
                "install.sh introuvable : copiez le dossier du projet sur le partage "
                "(\\\\RECALBOX\\share) puis rechargez cette page"
            )
        url = str(message.get("url") or "").strip()
        force = bool(message.get("force"))
        if not url and not force:
            skipped = self.up_to_date(installer)
            if skipped:
                if self.log:
                    self.log.info(
                        "Installation inutile : deja en %s (service %s)"
                        % (skipped["installed_version"], skipped["service_version"])
                    )
                return skipped
        command = ["sh", installer, "--upgrade", "--no-restart", "--home", self.home]
        if url:
            command += ["--from-url", url]
        self.start_install(client, command)
        return {"started": True}

    def _cmd_upload_begin(self, client, message):
        size = int(message.get("size") or 0)
        if size <= 0:
            raise ValueError("taille manquante")
        if size > MAX_UPLOAD:
            raise ValueError("fichier trop volumineux (max %d Mo)" % (MAX_UPLOAD // (1024 * 1024)))
        client.upload = bytearray()
        client.upload_size = size
        return {"size": size}

    def _cmd_upload_chunk(self, client, message):
        if client.upload is None:
            raise RuntimeError("aucun envoi en cours")
        raw = str(message.get("data") or "")
        try:
            chunk = base64.b64decode(raw, validate=False)
        except ValueError:
            raise ValueError("donnee base64 invalide")
        client.upload.extend(chunk)
        if len(client.upload) > client.upload_size:
            client.upload = None
            raise ValueError("flux plus long que prevu")
        return {"received": len(client.upload)}

    def _cmd_upload_end(self, client, message):
        if client.upload is None:
            raise RuntimeError("aucun envoi en cours")
        payload = bytes(client.upload)
        client.upload = None
        installer = self._installer_from_zip(client, payload)
        self.start_install(client, ["sh", installer, "--upgrade", "--no-restart", "--home", self.home])
        return {"started": True}

    def _installer_from_zip(self, client: _Client, payload: bytes) -> str:
        folder = tempfile.mkdtemp(prefix="rfid-update-")
        archive = os.path.join(folder, "update.zip")
        with open(archive, "wb") as handle:
            handle.write(payload)
        extracted = os.path.join(folder, "src")
        os.makedirs(extracted, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        for root, _directories, files in os.walk(extracted):
            if "install.sh" in files:
                client.tempdir = folder
                return os.path.join(root, "install.sh")
        raise RuntimeError("le fichier ZIP ne contient pas install.sh")

    def _cmd_reboot(self, client, message):
        def reboot():
            subprocess.Popen(
                ["sh", "-c", "sync; reboot"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        threading.Timer(2.0, reboot).start()
        return {"message": "Recalbox redemarre dans 2 secondes"}

    def _cmd_service(self, client, message):
        action = str(message.get("action") or "")
        if action not in ("start", "stop", "restart"):
            raise ValueError("action inconnue")
        if not os.path.isfile(self.main_py()):
            raise RuntimeError("le programme n'est pas installe")
        command = [sys.executable, self.main_py(), action, "--home", self.home]
        if action in ("stop", "restart"):
            # The daemon is a separate process: the agent stays available.
            def later():
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            threading.Timer(0.5, later).start()
            return {"message": "demande envoyee (%s)" % action}
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, text=True
        )
        return {"ok": result.returncode == 0, "output": result.stdout or ""}

    def _cmd_associate(self, client, message):
        """Waits for a badge: selected game, game chosen in the page, special
        card, or badge to erase."""
        mode = str(message.get("mode") or "associate")
        if mode not in ("associate", "delete", "card"):
            raise ValueError("mode inconnu")
        if not process_alive(read_pid(self.home)):
            raise RuntimeError("le service RFID n'est pas demarre")
        if mode == "card":
            entry = message.get("entry")
            if not isinstance(entry, dict):
                raise ValueError("carte manquante")
            # Checked now: the page gets a clear message rather than a silent failure.
            clean = TagStore._clean_entry(entry)
            self._write_command("arm_entry", entry=clean)
            return {"armed": "associate", "entry": clean}
        target = message.get("target")
        if mode == "associate" and isinstance(target, dict):
            system = str(target.get("system") or "").strip()
            path = str(target.get("path") or "").strip()
            if not system or not path or "|" in path:
                raise ValueError("jeu invalide")
            self._write_command("arm_target", target={
                "system": system, "path": path, "name": str(target.get("name") or "")})
            return {"armed": "associate"}
        self._write_command("arm_" + mode)
        return {"armed": mode}

    # ------------------------------------------------------------- library
    def _cmd_games_systems(self, client, message):
        return {"systems": self.library.systems(force=bool(message.get("refresh")))}

    def _cmd_games_search(self, client, message):
        try:
            limit = max(1, min(200, int(message.get("limit") or 60)))
        except (TypeError, ValueError):
            limit = 60
        games = self.library.search(str(message.get("query") or ""),
                                    str(message.get("system") or ""), limit)
        return {"games": games}

    def _cmd_media_image(self, client, message):
        """Scraped picture of a game (base64), for the card designer."""
        try:
            found = self.library.game_image(str(message.get("system") or ""), str(message.get("path") or ""))
        except LibraryError as exc:
            raise RuntimeError(str(exc))
        if not found:
            return {"found": False}
        kind, data = found
        return {"found": True, "type": kind, "data": base64.b64encode(data).decode("ascii")}

    def _cmd_media_logo(self, client, message):
        """Theme logo of a console (SVG text)."""
        try:
            found = self.library.system_logo(str(message.get("system") or ""),
                                             str(message.get("kind") or "logo"),
                                             str(message.get("region") or ""))
        except LibraryError as exc:
            raise ValueError(str(exc))
        if not found:
            return {"found": False}
        return {"found": True, "type": found[0], "svg": found[1].decode("utf-8", "replace")}

    # ------------------------------------------------------- card templates
    def _templates_path(self) -> str:
        return os.path.join(self.home, TEMPLATES_FILENAME)

    def _read_templates(self) -> list:
        try:
            with open(self._templates_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        items = data.get("templates") if isinstance(data, dict) else None
        return [item for item in (items or []) if isinstance(item, dict) and item.get("id")]

    def _write_templates(self, items: list) -> None:
        path = self._templates_path()
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump({"templates": items}, handle, ensure_ascii=False)
        os.replace(temporary, path)

    def _cmd_cards_templates(self, client, message):
        with self._templates_guard:
            return {"templates": self._read_templates()}

    def _cmd_cards_template_save(self, client, message):
        template = message.get("template")
        if not isinstance(template, dict):
            raise ValueError("modele manquant")
        if len(json.dumps(template)) > MAX_TEMPLATE_BYTES:
            raise ValueError("modele trop volumineux")
        name = str(template.get("name") or "").strip()[:60]
        if not name:
            raise ValueError("donnez un nom au modele")
        ident = str(template.get("id") or "").strip()[:40] or secrets.token_hex(6)
        template = dict(template, id=ident, name=name, saved=time.strftime("%Y-%m-%dT%H:%M:%S"))
        with self._templates_guard:
            items = [item for item in self._read_templates() if item.get("id") != ident]
            items.append(template)
            if len(items) > MAX_TEMPLATES:
                raise ValueError("trop de modeles enregistres (%d au plus)" % MAX_TEMPLATES)
            self._write_templates(items)
        return {"template": template}

    def _cmd_cards_template_delete(self, client, message):
        # "template", not "id": "id" is the request number of every message.
        ident = str(message.get("template") or "")
        with self._templates_guard:
            items = self._read_templates()
            kept = [item for item in items if item.get("id") != ident]
            if len(kept) != len(items):
                self._write_templates(kept)
        return {"removed": len(kept) != len(items)}

    def _cmd_config_get(self, client, message):
        """Settings editable from the page (with their current value)."""
        cfg = Config(self.config_path())
        options = []
        for option in OPTIONS:
            options.append(
                dict(
                    option,
                    value=option_value(cfg, option),
                    full="%s.%s" % (option["section"], option["key"]),
                )
            )
        return {"path": cfg.path, "options": options}

    def _cmd_config_set(self, client, message):
        """Saves the settings, then makes the service read its configuration again."""
        valeurs = message.get("values")
        if not isinstance(valeurs, dict) or not valeurs:
            raise ValueError("aucune valeur a enregistrer")
        cfg = Config(self.config_path())
        connues = {"%s.%s" % (o["section"], o["key"]): o for o in OPTIONS}
        a_ecrire = {}
        for cle, valeur in valeurs.items():
            option = connues.get(str(cle))
            if option is None:
                raise ValueError("option inconnue : %s" % cle)
            a_ecrire[cle] = validate_option(option, valeur)
        modifiees = cfg.write_values(a_ecrire)
        applique = self._reload_service()
        if self.log:
            self.log.info(
                "Options enregistrees : %s (%s)"
                % (", ".join(sorted(modifiees)), "service recharge" if applique else "service arrete")
            )
        reboot = False
        boot_errors = []
        if cfg.get("led", "type", "none").lower() == "ws2812" and not os.path.exists("/dev/spidev1.0"):
            # Programmable LEDs: the second SPI bus is enabled at the next boot.
            if os.path.isdir("/boot"):
                outcome = bootcfg.ensure_line()
                boot_errors = outcome["errors"]
                if self.log and outcome["changed"]:
                    self.log.info("Second bus SPI active dans %s" % ", ".join(outcome["changed"]))
            reboot = bootcfg.has_line(bootcfg.SPI1_OVERLAY)
        return {"saved": sorted(modifiees), "reloaded": applique, "reboot": reboot,
                "boot_errors": boot_errors}

    def _reload_service(self) -> bool:
        """Asks the service to read its configuration again (SIGHUP)."""
        pid = read_pid(self.home)
        if not process_alive(pid):
            return False
        try:
            os.kill(pid, SIG_HUP)
            return True
        except OSError as exc:
            if self.log:
                self.log.warning("Rechargement du service impossible : %s" % exc)
            return False

    def _calibration_path(self) -> str:
        return os.path.join(self.home, CALIBRATION_FILENAME)

    def _read_calibration(self):
        try:
            with open(self._calibration_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _require_service(self) -> None:
        """Refuses measurements when the service is not up to date and running."""
        if not process_alive(read_pid(self.home)):
            raise RuntimeError("le service RFID n'est pas demarre : demarrez-le dans "
                               "l'onglet Maintenance, puis relancez la mesure")
        service_version = str((read_status(self.home) or {}).get("version") or "")
        if version_key(service_version) and version_key(service_version) < version_key(__version__):
            raise RuntimeError(
                "le service du lecteur tourne encore en %s alors que l'agent est en %s : "
                "cliquez sur « Installer / mettre a jour » (ou redemarrez le service), "
                "puis relancez la mesure" % (service_version, __version__)
            )

    def _cmd_calibrate_start(self, client, message):
        """Starts the reader tuning sequence (immediate answer)."""
        self._require_service()
        etat = self._read_calibration()
        if etat and not etat.get("finished") and etat.get("phase") in CALIBRATION_STEPS:
            raise RuntimeError("une mesure est deja en cours")
        try:
            os.remove(self._calibration_path())
        except OSError:
            pass
        self._write_command("calibrate_start")
        if self.log:
            self.log.info("Mesure du lecteur demandee par la page")
        # The service publishes its first state within a few hundred ms: it is
        # sent back so that the page shows the right step at once.
        echeance = time.time() + 2.0
        while time.time() < echeance:
            etat = self._read_calibration()
            if etat is not None:
                return {"started": True, "state": etat}
            time.sleep(0.1)
        return {"started": True, "state": None}

    def _cmd_calibrate_status(self, client, message):
        """Measurement state: instruction to display, measures, applied values."""
        etat = self._read_calibration()
        if etat is None:
            return {"phase": "idle", "finished": True, "instruct": "",
                    "measures": {}, "applied": {}, "error": ""}
        return etat

    def _cmd_calibrate_cancel(self, client, message):
        self._require_service()
        self._write_command("calibrate_cancel")
        return {"cancelled": True}

    def _cmd_calibrate_reset(self, client, message):
        """Resets the reader settings to their original values."""
        self._require_service()
        try:
            os.remove(self._calibration_path())
        except OSError:
            pass
        self._write_command("calibrate_reset")
        deadline = time.time() + 6.0
        while time.time() < deadline:
            etat = self._read_calibration()
            if etat and etat.get("phase") == "reset":
                return {"applied": etat.get("applied") or {}, "defaults": etat.get("defaults") or {}}
            time.sleep(0.25)
        raise RuntimeError("le service n'a pas confirme la reinitialisation")

    def _cmd_reader_test(self, client, message):
        """Tests the reader itself: is the card seen, and read?

        The SPI bus belongs to the service: the agent drops the request for it and
        reads the result written back (``reader-test.json``).
        """
        try:
            seconds = float(message.get("seconds") or 5)
        except (TypeError, ValueError):
            raise ValueError("duree invalide")
        seconds = max(2.0, min(15.0, seconds))
        if not process_alive(read_pid(self.home)):
            raise RuntimeError("le service RFID n'est pas demarre : demarrez-le dans "
                               "l'onglet Maintenance, puis relancez le test")
        # An older service does not know this command yet: say so clearly
        # rather than waiting and then reporting a hang.
        service_version = str((read_status(self.home) or {}).get("version") or "")
        if version_key(service_version) and version_key(service_version) < version_key(__version__):
            raise RuntimeError(
                "le service du lecteur tourne encore en %s alors que l'agent est en %s : "
                "cliquez sur « Installer / mettre à jour » (ou redémarrez le service), "
                "puis relancez le test" % (service_version, __version__)
            )
        path = os.path.join(self.home, READER_TEST_FILENAME)
        try:
            os.remove(path)
        except OSError:
            pass
        self._write_command("reader_test", seconds=seconds)
        deadline = time.time() + seconds + 10
        while time.time() < deadline:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict) and data.get("finished"):
                    return data
            except (OSError, ValueError):
                pass
            time.sleep(0.25)
        service_version = str((read_status(self.home) or {}).get("version") or "")
        raise RuntimeError(
            "le lecteur n'a pas répondu au test : le service %s n'a pas réagi "
            "(est-il bien démarré ?)" % (service_version or "inconnu")
        )

    def _cmd_scan(self, client, message):
        uid = str(message.get("uid") or "")
        if not uid:
            raise ValueError("UID manquant")
        if not process_alive(read_pid(self.home)):
            raise RuntimeError("le service RFID n'est pas demarre")
        self._write_command("simulate_scan", uid=normalize_uid(uid))
        return {"uid": normalize_uid(uid)}

    # ------------------------------------------------------------------- badges
    def _cmd_tags_list(self, client, message):
        store = self._tags()
        items = []
        for uid, entry in store.items():
            items.append(
                {
                    "uid": uid,
                    "pretty": pretty_uid(uid),
                    "system": entry["system"],
                    "game": entry["game"],
                    "name": entry["name"],
                    "path": entry.get("path") or "",
                    "kind": entry.get("kind") or "game",
                    "action": entry.get("action") or "",
                    "params": entry.get("params") or {},
                    "limit_min": entry.get("limit_min"),
                    "hits": entry.get("hits", 0),
                    "last_used": entry.get("last_used") or "",
                }
            )
        return {"count": len(items), "tags": items}

    def _cmd_tags_write(self, client, message):
        """Writes the game of a badge into the badge itself (portable card).

        The service owns the reader: it waits up to 15 s for this badge on the
        reader, writes, reads back, and leaves its verdict in tag-write.json.
        """
        uid = normalize_uid(str(message.get("uid") or ""))
        entry = self._tags().get(uid)
        if entry is None:
            raise ValueError("badge inconnu")
        if entry.get("kind") == "action":
            raise ValueError("une carte speciale ne s'ecrit pas dans le badge")
        try:
            data = portable.encode(entry["system"], entry.get("path") or entry["game"])
        except portable.PortableError as exc:
            raise ValueError(str(exc))
        if not process_alive(read_pid(self.home)):
            raise RuntimeError("le service RFID n'est pas demarre")
        path = os.path.join(self.home, TAG_WRITE_FILENAME)
        try:
            os.remove(path)
        except OSError:
            pass
        self._write_command("write_tag", uid=uid, data=data.hex())
        deadline = time.time() + 20.0
        while time.time() < deadline:
            time.sleep(0.25)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    result = json.load(handle)
            except (OSError, ValueError):
                continue
            if result.get("state") == "done":
                return {"written": True, "bytes": result.get("bytes", len(data))}
            if result.get("state") == "error":
                raise RuntimeError(str(result.get("message") or "ecriture impossible"))
        raise RuntimeError("le service n'a pas repondu")

    def _cmd_tags_update(self, client, message):
        """Renames a badge, or changes its time limit / card parameters."""
        uid = str(message.get("uid") or "")
        changes = message.get("changes")
        if not uid or not isinstance(changes, dict):
            raise ValueError("badge ou modifications manquants")
        return {"entry": self._tags().update(uid, changes)}

    def _cmd_tags_add(self, client, message):
        system = str(message.get("system") or "").strip()
        game = str(message.get("game") or "").strip()
        chemin = str(message.get("path") or "").strip()
        if not game and chemin:
            # Picked from the game list: only the full path is known.
            game = relative_to_system(system, chemin)
        if not system or not game:
            raise ValueError("systeme et jeu obligatoires")
        if not chemin:
            # Without a path the frontend could not start the game: it is rebuilt
            # from the system and the file name.
            chemin = resolve_rom_path(system, game)
        entry = self._tags().put(
            str(message.get("uid") or ""),
            system,
            game,
            str(message.get("name") or ""),
            chemin,
        )
        if self.log:
            self.log.info("Badge ajoute via l'agent (%s / %s)" % (system, game))
        return {"entry": entry}

    def _cmd_tags_remove(self, client, message):
        uid = str(message.get("uid") or "")
        if not uid:
            raise ValueError("UID manquant")
        return {"removed": self._tags().delete(uid)}

    def _cmd_tags_export(self, client, message):
        store = self._tags()
        handle, path = tempfile.mkstemp(suffix=".csv", prefix="rfid-badges-")
        os.close(handle)
        try:
            store.export_csv(path)
            with open(path, "r", encoding="utf-8") as stream:
                return {"csv": stream.read()}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def _cmd_tags_import(self, client, message):
        text = str(message.get("csv") or "")
        if not text.strip():
            raise ValueError("CSV vide")
        handle, path = tempfile.mkstemp(suffix=".csv", prefix="rfid-import-")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(text)
            return {"stats": self._tags().import_csv(path)}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


#: Settings shown in the page's Settings tab (section, key, type...). The
#: labels are French on purpose: they are the translation keys of the page
#: (i18n/<code>.json). "advanced" settings are folded away by the page;
#: "when" ("section.key=value" or "!=") shows a setting only when it matters.
OPTIONS = (
    {"section": "launch", "key": "action", "type": "choice",
     "choices": ["launch", "none"], "default": "launch",
     "label": "Quand on pose un badge associé",
     "help": "Lancer le jeu, ou seulement biper (pratique pour vérifier ses badges sans lancer de partie)."},
    {"section": "launch", "key": "ignore_when_game_running", "type": "bool", "default": True,
     "label": "Ne pas interrompre une partie en cours",
     "help": "Un badge posé pendant une partie ne lance pas d'autre jeu."},
    {"section": "launch", "key": "stop_on_remove", "type": "bool", "default": False,
     "label": "Quitter le jeu quand on retire le badge",
     "help": "Comme une cartouche : retirer le badge ramène au menu de la Recalbox."},
    {"section": "button", "key": "arm_timeout_s", "type": "number", "min": 3, "max": 60,
     "default": 10, "label": "Temps pour poser le badge (secondes)",
     "help": "Après « Associer un badge à ce jeu » ou un appui court sur le bouton du boîtier."},
    {"section": "button", "key": "hold_press_s", "type": "number", "min": 1, "max": 10,
     "default": 3, "label": "Appui pour autoriser un ordinateur (secondes)",
     "help": "Durée pendant laquelle garder le bouton du boîtier enfoncé."},
    {"section": "feedback", "key": "sound", "type": "bool", "default": True,
     "label": "Bips sonores",
     "help": "Confirment l'association d'un badge et signalent les erreurs."},
    {"section": "time", "key": "default_limit_min", "type": "number", "min": 0, "max": 600,
     "default": 0, "label": "Temps de jeu par partie (minutes)",
     "help": "Pour les badges sans limite à eux. 0 = pas de limite. Prévient 5 minutes puis 1 minute avant la fin, puis quitte le jeu."},
    {"section": "screen", "key": "messages", "type": "bool", "default": True,
     "label": "Messages à l'écran pendant les parties",
     "help": "Temps restant, temps bonus, demande d'accès d'un appareil… Affichés par les jeux RetroArch (le menu de la Recalbox ne peut pas les afficher)."},
    {"section": "agent", "key": "web", "type": "bool", "default": True,
     "label": "Page pour téléphones et tablettes",
     "help": "La Recalbox sert la page à l'adresse http://recalbox.local:8765. Désactivé : seule la page enregistrée sur un ordinateur peut se connecter (un téléphone connecté par cette adresse sera coupé)."},
    {"section": "led", "key": "type", "type": "choice", "choices": ["none", "rgb", "ws2812"],
     "default": "none", "label": "Voyant",
     "help": "Une LED qui montre ce que fait le lecteur : prêt, association, erreur, fin du temps de jeu."},
    {"section": "led", "key": "idle", "type": "bool", "default": True, "when": "led.type!=none",
     "label": "Voyant allumé au repos",
     "help": "Vert quand tout est prêt. Désactivé : le voyant ne s'allume que pour signaler quelque chose."},
    {"section": "led", "key": "common", "type": "choice", "choices": ["cathode", "anode"], "when": "led.type=rgb",
     "default": "cathode", "label": "LED RGB : patte commune",
     "help": "La plus longue patte de la LED : reliée à la masse (cathode commune, le plus courant) ou au 3,3 V (anode commune)."},
    {"section": "led", "key": "count", "type": "number", "min": 1, "max": 150, "default": 1, "when": "led.type=ws2812",
     "label": "LED programmables : nombre de LED",
     "help": "Une seule LED, un anneau ou un bout de ruban : toutes prennent la même couleur."},
    {"section": "led", "key": "brightness", "type": "number", "min": 2, "max": 100, "default": 40, "when": "led.type=ws2812",
     "label": "LED programmables : luminosité (%)",
     "help": "Moins fort, c'est moins éblouissant et ça consomme moins."},
    {"section": "led", "key": "pin_red", "type": "number", "min": 2, "max": 27, "when": "led.type=rgb", "default": 22,
     "advanced": True, "label": "LED RGB : broche du rouge (GPIO)",
     "help": "Numéro GPIO (BCM), pas le numéro de broche. 22 = broche 15."},
    {"section": "led", "key": "pin_green", "type": "number", "min": 2, "max": 27, "when": "led.type=rgb", "default": 23,
     "advanced": True, "label": "LED RGB : broche du vert (GPIO)",
     "help": "23 = broche 16."},
    {"section": "led", "key": "pin_blue", "type": "number", "min": 2, "max": 27, "when": "led.type=rgb", "default": 24,
     "advanced": True, "label": "LED RGB : broche du bleu (GPIO)",
     "help": "24 = broche 18."},
    {"section": "rfid", "key": "poll_interval_ms", "type": "number", "min": 50, "max": 1000,
     "default": 150, "advanced": True,
     "label": "Fréquence de lecture (millisecondes)",
     "help": "Temps entre deux lectures : plus court, le lecteur réagit plus vite mais la Recalbox travaille un peu plus."},
    {"section": "rfid", "key": "same_tag_cooldown_s", "type": "number", "min": 0.5, "max": 30,
     "default": 2.5, "advanced": True,
     "label": "Délai avant de relancer le même badge (secondes)",
     "help": "Évite qu'un badge posé deux fois de suite lance deux fois le jeu."},
    {"section": "rfid", "key": "rearm_absent_ms", "type": "number", "min": 300, "max": 10000,
     "default": 1200, "advanced": True,
     "label": "Badge considéré comme retiré après (millisecondes)",
     "help": "Durée sans badge sur le lecteur avant de le considérer comme retiré."},
    {"section": "rfid", "key": "spi_speed_hz", "type": "number", "min": 100000, "max": 10000000,
     "default": 1000000, "advanced": True,
     "label": "Vitesse de liaison avec le lecteur (Hz)",
     "help": "Le réglage automatique (onglet Matériel) choisit la meilleure valeur. Pris en compte au redémarrage du service."},
    {"section": "general", "key": "log_level", "type": "choice",
     "choices": ["DEBUG", "INFO", "WARNING", "ERROR"], "default": "INFO", "advanced": True,
     "label": "Détail du journal",
     "help": "« normal » suffit ; « tout noter » aide à comprendre un problème."},
)


def option_value(cfg, option) -> str:
    section, key = option["section"], option["key"]
    defaut = option.get("default")
    if option["type"] == "bool":
        return "1" if cfg.get_bool(section, key, bool(defaut)) else "0"
    if option["type"] == "number":
        valeur = cfg.get_float(section, key, float(defaut or 0))
        if float(valeur).is_integer() and float(defaut or 0).is_integer():
            return str(int(valeur))
        return ("%g" % valeur)
    return cfg.get(section, key, str(defaut or ""))


def validate_option(option, valeur) -> str:
    """Checks a value before writing it; returns the form to store."""
    brut = str(valeur).strip()
    if option["type"] == "bool":
        if brut.lower() in ("1", "true", "oui", "on", "yes"):
            return "1"
        if brut.lower() in ("0", "false", "non", "off", "no", ""):
            return "0"
        raise ValueError("valeur oui/non attendue pour %s" % option["label"])
    if option["type"] == "choice":
        choix = [str(item) for item in option["choices"]]
        if brut not in choix:
            raise ValueError("%s : valeur parmi %s" % (option["label"], ", ".join(choix)))
        return brut
    try:
        nombre = float(brut.replace(",", "."))
    except ValueError:
        raise ValueError("%s : nombre attendu" % option["label"])
    if "min" in option and nombre < float(option["min"]):
        raise ValueError("%s : minimum %s" % (option["label"], option["min"]))
    if "max" in option and nombre > float(option["max"]):
        raise ValueError("%s : maximum %s" % (option["label"], option["max"]))
    if float(option.get("default") or 0).is_integer() and nombre.is_integer():
        return str(int(nombre))
    return "%g" % nombre


# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------
class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, agent: Agent):
        self.agent = agent
        super().__init__(address, handler)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        agent: Agent = self.server.agent  # type: ignore[attr-defined]
        sock = self.request
        sock.settimeout(AUTH_TIMEOUT)
        try:
            headers = self._read_headers(sock)
        except (OSError, ValueError):
            return
        origin = ""
        key = ""
        host = ""
        for line in headers.split("\r\n")[1:]:
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
            elif line.lower().startswith("origin:"):
                origin = line.split(":", 1)[1].strip()
            elif line.lower().startswith("host:"):
                host = line.split(":", 1)[1].strip()
        request_line = headers.split("\r\n", 1)[0]
        if not key and request_line.upper().startswith(("GET ", "HEAD ")):
            # Plain HTTP request: the management page, for phones and tablets.
            self._serve_page(agent, sock, request_line, host)
            return
        # Web origins are refused: only a local page (file://, origin "null"),
        # the page served by this agent (same origin), or a client without an
        # Origin header can connect.
        if origin and origin.lower() != "null" and not (same_origin(origin, host) and agent.web_enabled()):
            try:
                sock.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            if agent.log:
                agent.log.warning("Agent : origine refusee (%s)" % origin)
            return
        if not key or "upgrade" not in headers.lower():
            try:
                sock.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: %s\r\n\r\n" % accept
        )
        try:
            sock.sendall(response.encode("ascii"))
        except OSError:
            return
        sock.settimeout(None)
        client = _Client(sock, self.client_address)
        agent.register(client)
        keep = True

        def control(opcode, payload):
            if opcode == 0x9:  # ping -> pong
                _send_frame(sock, 0xA, payload)

        while keep and agent.running:
            try:
                opcode, payload = _read_message(client, control)
            except (ConnectionError, OSError, ProtocolError, struct.error):
                break
            if opcode == 0x8:  # close
                break
            if opcode != 0x1:
                continue
            try:
                message = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                client.send({"ok": False, "error": "JSON invalide"})
                continue
            keep = agent.process(client, message)
        agent.unregister(client)
        client.close()

    def _serve_page(self, agent, sock, request_line: str, host: str) -> None:
        """Serves the management page (http://recalbox.local:8765/)."""
        parts = request_line.split()
        target = parts[1] if len(parts) > 1 else "/"
        path = target.split("?", 1)[0].split("#", 1)[0]
        page = agent.web_page()
        status = "200 OK"
        body = b""
        kind = "text/html; charset=utf-8"
        if not is_private_address(self.client_address) or not local_host_header(host):
            status, body, kind = "403 Forbidden", b"", "text/plain"
        elif not agent.web_enabled():
            status, body, kind = "404 Not Found", b"page disabled", "text/plain"
        elif path not in ("/", "/index.html"):
            status, body, kind = "404 Not Found", b"not found", "text/plain"
        elif page is None:
            status = "503 Service Unavailable"
            body = ("<!doctype html><meta charset=utf-8><p>Page indisponible : "
                    "mettez le programme a jour.</p>").encode("utf-8")
        else:
            try:
                with open(page, "rb") as handle:
                    body = handle.read()
            except OSError:
                status, body = "500 Internal Server Error", b""
            # Tells the page it is served by the Recalbox itself.
            body = body.replace(b"<head>", b'<head>\n<meta name="rfid-agent" content="1">', 1)
        head = request_line.upper().startswith("HEAD ")
        response = (
            "HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
            "Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
            "Referrer-Policy: no-referrer\r\nConnection: close\r\n\r\n" % (status, kind, len(body))
        ).encode("ascii")
        try:
            sock.sendall(response + (b"" if head else body))
        except OSError:
            pass

    @staticmethod
    def _read_headers(sock) -> str:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(1)
            if not chunk:
                raise ConnectionError("connexion fermee")
            data += chunk
            if len(data) > 16384:
                raise ValueError("en-tetes trop longs")
        return data.decode("latin-1")


def _host_name(host: str) -> str:
    """``192.168.1.20:8765`` -> ``192.168.1.20``; ``[fe80::1]:8765`` -> ``fe80::1``."""
    host = str(host or "").strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host[1:]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def local_host_header(host: str) -> bool:
    """The page is only served under a local name or an IP address.

    Refusing other names blocks "DNS rebinding": a web site whose name
    suddenly points to the Recalbox would otherwise be treated as the
    Recalbox's own page.
    """
    name = _host_name(host)
    if not name:
        return False
    if name in LOCAL_HOSTNAMES:
        return True
    try:
        own = socket.gethostname().lower()
    except OSError:
        own = ""
    if own and name in (own, own + ".local"):
        return True
    try:
        socket.inet_pton(socket.AF_INET6 if ":" in name else socket.AF_INET, name)
        return True
    except (OSError, ValueError):
        return False


def same_origin(origin: str, host: str) -> bool:
    """True for the page served by this agent (Origin == http://<Host>)."""
    origin = str(origin or "").strip().lower().rstrip("/")
    return bool(host) and local_host_header(host) and origin == "http://" + str(host).strip().lower()


def lan_ip() -> str:
    """Local network address of the Recalbox (for the phone link)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet is sent: connect() only picks the outgoing interface.
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    except OSError:
        address = ""
    finally:
        probe.close()
    if not address or address.startswith("127."):
        address = _local_ip()
    return address


def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "recalbox.local"
