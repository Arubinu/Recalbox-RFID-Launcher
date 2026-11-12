"""Agent WebSocket : installation, mise à jour et gestion depuis `installer.html`.

Pourquoi un WebSocket plutôt qu'une page servie par la Recalbox ? Parce que
l'interface est un simple fichier HTML ouvert sur le PC (`file://`) : elle ne
partage pas l'origine de la Recalbox, donc `fetch()` y serait bloqué par le
navigateur, alors qu'un `WebSocket` est autorisé (vérifié : l'origine `null`
d'un fichier local est acceptée).

Tout est dans la bibliothèque standard : poignée de main HTTP, trames RFC 6455
et boucle de service. Seule une connexion authentifiée par un jeton peut agir.

Commandes (JSON, une réponse par `id`) :

* ``auth`` (jeton), ``status``, ``version``, ``log`` ;
* ``install`` (dossier du partage ou URL), ``upload.begin/chunk/end`` (ZIP) ;
* ``tags.list/add/remove/export/import`` ;
* ``associate``, ``scan`` (mode association / badge simulé) ;
* ``service`` (start/stop/restart), ``reboot``.

Événements serveur → client : ``{"event": "log"}``, ``{"event": "install"}``,
``{"event": "restart_agent"}``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
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
from .consts import AGENT_COMMAND_FILENAME, DB_FILENAME, TOKEN_FILENAME
from .daemon import process_alive, read_pid, read_status, recalbox_version, acquire_lock, release_lock
from .esbridge import current_target, read_state, supports_start_command
from .storage import StorageError, TagStore, normalize_uid, pretty_uid

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE = 4 * 1024 * 1024
MAX_UPLOAD = 64 * 1024 * 1024
AUTH_FAILURES = 3
AUTH_TIMEOUT = 20.0
DEFAULT_PORT = 8765
PAIRING_FILENAME = "pairing.json"
PAIRING_MINUTES = 15
USERSCRIPT = "/recalbox/share/userscripts/recalbox-rfid(permanent).py3"
AGENT_USERSCRIPT = "/recalbox/share/userscripts/recalbox-rfid-agent(permanent).py3"


# ---------------------------------------------------------------------------
# Appairage : recuperer le jeton sans partage reseau ni copier-coller
# ---------------------------------------------------------------------------
def is_private_address(address) -> bool:
    """Vrai si la connexion vient du reseau local (appairage autorise)."""
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
    # IPv6 lien-local et uniques locales (fd00::/8, fc00::/7)
    return host.startswith(("fe80:", "fd", "fc"))


def pairing_path(home: str) -> str:
    return os.path.join(home, PAIRING_FILENAME)


def open_pairing_window(home: str, minutes: int = PAIRING_MINUTES) -> float:
    """Ouvre une fenetre d'appairage (usage unique) et renvoie son echeance."""
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
        with open(pairing_path(home), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return float(data.get("until") or 0) > time.time()
    except (OSError, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Jeton partagé
# ---------------------------------------------------------------------------
def ensure_token(path: str) -> str:
    """Lit (ou crée) le jeton d'accès de l'agent."""
    try:
        with open(path, "r", encoding="ascii") as handle:
            token = handle.read().strip()
        if token:
            return token
    except OSError:
        pass

    token = secrets.token_hex(8).upper()
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # Fichier existant mais vide ou illisible : on le remplace.
        try:
            with open(path, "r", encoding="ascii") as handle:
                existing = handle.read().strip()
            if existing:
                return existing
        except OSError:
            pass
        try:
            with open(path, "w", encoding="ascii") as handle:
                handle.write(token + "\n")
            return token
        except OSError:
            return token
    except OSError:
        return token
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        handle.write(token + "\n")
    return token


def find_source(share: str = "/recalbox/share", home: str = None):
    """Cherche le dossier du projet (app/main.py + install.sh) sur le partage."""
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
    """Une connexion cliente : tampon de lecture, envoi sérialisé, état."""

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
    """Serveur WebSocket et logique de gestion."""

    def __init__(self, cfg, log, home: str, source: str = None, db: str = None, port: int = None):
        self.cfg = cfg
        self.log = log
        self.home = os.path.abspath(home)
        self.source = os.path.abspath(source) if source else None
        self.db_path = db or os.path.join(self.home, DB_FILENAME)
        self.port = int(port) if port is not None else cfg.get_int("agent", "port", DEFAULT_PORT)
        self.token_path = os.path.join(self.home, TOKEN_FILENAME)
        existed = os.path.isfile(self.token_path)
        self.token = ensure_token(self.token_path)
        # Premier demarrage (jeton cree) : on laisse une fenetre d'appairage, le
        # temps que la page recupere le jeton sans partage reseau.
        if not existed:
            open_pairing_window(self.home)
        self._store = TagStore(self.db_path, log)
        self._store_guard = threading.Lock()
        self._install_lock = threading.Lock()
        self._install_running = False
        self.server = None
        self.running = False
        self._lock = None

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
                "Agent WebSocket pret sur ws://%s:%d (jeton : %s)"
                % (_local_ip(), self.port, self.token_path)
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
        candidates = []
        if self.source:
            candidates.append(os.path.join(self.source, "install.sh"))
        candidates.append(os.path.join(self.home, "install.sh"))
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return None

    def main_py(self) -> str:
        return os.path.join(self.home, "app", "main.py")

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
        target = current_target(read_state())
        frontend = supports_start_command() if os.path.exists("/usr/bin/emulationstation") else None
        return {
            "app_version": __version__,
            "home": self.home,
            "source": self.source,
            "installed": installed,
            "installed_version": installed_version,
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
                }
                if target
                else None
            ),
            "install": {"running": self._install_running},
            "agent": {
                "port": self.port,
                "token": self.token,
                "token_path": self.token_path,
                "pairing": pairing_is_open(self.home),
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

    def _after_install(self, client: _Client) -> None:
        # Démarre le service (le script permanent le fera aussi au prochain boot).
        try:
            if os.path.isfile(self.main_py()):
                subprocess.Popen(
                    [sys.executable, self.main_py(), "start", "--home", self.home],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        except OSError:
            pass
        client.send({"event": "restart_agent", "in": 2})
        threading.Timer(2.0, self._reexec).start()

    def _reexec(self) -> None:
        """Recharge l'agent avec le code fraîchement installé."""
        if "agent" not in sys.argv[1:3]:
            # Sécurité : ne jamais remplacer un autre programme (tests, CLI...).
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
        """Traite un message ; retourne False pour fermer la connexion."""
        if not isinstance(message, dict):
            client.send({"ok": False, "error": "objet JSON attendu"})
            return True
        request_id = message.get("id")
        command = str(message.get("cmd") or "").strip()

        if command == "pair":
            return self._handle_pair(client, request_id)

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
            client.send({"id": request_id, "ok": False, "error": "jeton invalide"})
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
        except Exception as exc:  # noqa: BLE001 - l'agent ne doit jamais tomber
            if self.log:
                self.log.error("Agent : erreur sur %s : %s" % (command, exc))
            client.send({"id": request_id, "ok": False, "error": "erreur interne : %s" % exc})
        return True

    # ------------------------------------------------------------- appairage
    def _handle_pair(self, client, request_id) -> bool:
        """Donne le jeton une seule fois, sur le reseau local, fenetre limitee."""
        source = getattr(client, "address", "")
        if not is_private_address(source):
            client.send({
                "id": request_id,
                "ok": False,
                "error": "appairage refuse : adresse hors du reseau local",
            })
            return True
        if not pairing_is_open(self.home):
            client.send({
                "id": request_id,
                "ok": False,
                "error": "appairage ferme : redemarrez la Recalbox, ou lancez rfidctl pair",
            })
            return True
        close_pairing_window(self.home)
        if self.log:
            self.log.warning("Agent : appairage depuis %s (jeton transmis une fois)" % (source,))
        client.send({"id": request_id, "ok": True, "data": {"token": self.token}})
        return True

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

    def _cmd_install(self, client, message):
        installer = self.installer()
        if installer is None:
            raise RuntimeError(
                "install.sh introuvable : copiez le dossier du projet sur le partage "
                "(\\\\RECALBOX\\share) puis rechargez cette page"
            )
        url = str(message.get("url") or "").strip()
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
            # Le demon est un processus separe : l'agent reste disponible.
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
        mode = str(message.get("mode") or "associate")
        if mode not in ("associate", "delete"):
            raise ValueError("mode inconnu")
        if not process_alive(read_pid(self.home)):
            raise RuntimeError("le service RFID n'est pas demarre")
        self._write_command("arm_" + mode)
        return {"armed": mode}

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
                    "hits": entry.get("hits", 0),
                    "last_used": entry.get("last_used") or "",
                }
            )
        return {"count": len(items), "tags": items}

    def _cmd_tags_add(self, client, message):
        system = str(message.get("system") or "").strip()
        game = str(message.get("game") or "").strip()
        if not system or not game:
            raise ValueError("systeme et jeu obligatoires")
        entry = self._tags().put(
            str(message.get("uid") or ""),
            system,
            game,
            str(message.get("name") or ""),
            str(message.get("path") or ""),
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
        key = ""
        for line in headers.split("\r\n")[1:]:
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
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
        keep = True
        while keep and agent.running:
            try:
                fin, opcode, payload = _read_frame(client)
            except (ConnectionError, OSError, ProtocolError, struct.error):
                break
            if opcode == 0x8:  # close
                break
            if opcode == 0x9:  # ping
                try:
                    _send_frame(sock, 0xA, payload)
                except OSError:
                    break
                continue
            if opcode in (0xA,):  # pong
                continue
            if opcode != 0x1:
                continue
            try:
                message = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                client.send({"ok": False, "error": "JSON invalide"})
                continue
            keep = agent.process(client, message)
        client.close()

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


def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "recalbox.local"
