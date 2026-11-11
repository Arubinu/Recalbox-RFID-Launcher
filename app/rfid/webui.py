"""Interface web : installer, mettre à jour et gérer les badges depuis un navigateur.

L'objectif est qu'aucune ligne de commande ne soit nécessaire : la page est servie
par le service (ou par un script d'amorçage avant l'installation) et permet de

* installer / mettre à jour le programme (ZIP envoyé depuis le navigateur ou URL) ;
* redémarrer Recalbox ;
* voir l'état du matériel (SPI, lecteur, bouton) et du service ;
* gérer les badges (ajout, suppression, export/import CSV) ;
* armer l'association d'un badge au jeu sélectionné dans Recalbox.

Aucune dépendance : ``http.server`` de la bibliothèque standard, page HTML unique
sans ressource externe (fonctionne hors ligne).
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .consts import DB_FILENAME
from .daemon import process_alive, read_pid, read_status, recalbox_version
from .esbridge import current_target, read_state, supports_start_command
from .storage import StorageError, TagStore, normalize_uid, pretty_uid

USERSCRIPT = "/recalbox/share/userscripts/recalbox-rfid(permanent).py3"
WEB_USERSCRIPT = "/recalbox/share/userscripts/recalbox-rfid-web(permanent).py3"

#: Corps maximal accepté (ZIP de mise à jour).
MAX_BODY = 64 * 1024 * 1024

INDEX_CANDIDATES = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html"),
)


def _iso(timestamp=None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp or time.time()))


class WebUI:
    """Serveur HTTP de l'interface de gestion."""

    def __init__(self, cfg, log, home=None, source=None, db=None, port=None, host=None):
        self.cfg = cfg
        self.log = log
        self.home = os.path.abspath(home) if home else ""
        if not self.home:
            from .consts import home_dir

            self.home = home_dir()
        self.source = os.path.abspath(source) if source else None
        self.db_path = db or os.path.join(self.home, DB_FILENAME)
        self.host = host or cfg.get("web", "host", "0.0.0.0")
        self.port = int(port or cfg.get_int("web", "port", 8080))
        self.password = cfg.get("web", "password", "")

        self.server = None
        self.thread = None
        self._store = TagStore(self.db_path, log)
        self._store_guard = threading.Lock()
        self._install_guard = threading.Lock()
        self._install = {
            "state": "idle",
            "started": "",
            "finished": "",
            "output": "",
            "code": None,
            "mode": "",
        }

    # ------------------------------------------------------------------ cycle
    def start(self) -> bool:
        if self.server is not None:
            return True
        try:
            server = ThreadingHTTPServer((self.host, self.port), _RequestHandler)
        except OSError as exc:
            if self.log:
                self.log.warning(
                    "Interface web impossible sur le port %d : %s "
                    "(changez 'port' dans la section [web] de config.ini)"
                    % (self.port, exc)
                )
            return False
        server.daemon_threads = True
        server.webui = self
        self.server = server
        self.thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="webui",
            daemon=True,
        )
        self.thread.start()
        if self.log:
            self.log.info("Interface web : %s" % self.url())
        return True

    def stop(self) -> None:
        server, self.server = self.server, None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:  # noqa: BLE001
                pass

    def serve_forever(self) -> int:
        """Bloque le processus courant (commande ``web``)."""
        if not self.start():
            return 1
        if self.log:
            self.log.info("Ouvrez %s dans un navigateur" % self.url())
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
        return 0

    def url(self) -> str:
        address = self.host
        if address in ("0.0.0.0", "", "::"):
            address = self._local_ip()
        return "http://%s:%d" % (address, self.port)

    @staticmethod
    def _local_ip() -> str:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "recalbox.local"

    # --------------------------------------------------------------- utilitaire
    def _tags(self) -> TagStore:
        with self._store_guard:
            self._store.reload_if_changed()
            return self._store

    def main_py(self) -> str:
        return os.path.join(self.home, "app", "main.py")

    def installer(self):
        """Cherche install.sh : d'abord la source (amorçage), puis l'installation."""
        candidates = []
        if self.source:
            candidates.append(os.path.join(self.source, "install.sh"))
        candidates.append(os.path.join(self.home, "install.sh"))
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return None

    def _index_path(self):
        for candidate in INDEX_CANDIDATES:
            if os.path.isfile(candidate):
                return candidate
        return None

    # ------------------------------------------------------------------- API
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
        frontend = None
        if os.path.exists("/usr/bin/emulationstation"):
            frontend = supports_start_command()

        return {
            "app_version": __version__,
            "home": self.home,
            "source": self.source,
            "installed": installed,
            "installed_version": installed_version,
            "recalbox": recalbox_version(),
            "spi": os.path.exists("/dev/spidev0.0"),
            "userscript": os.path.isfile(USERSCRIPT) or os.path.isfile(WEB_USERSCRIPT),
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
            "install": dict(self._install),
            "web": {"port": self.port, "url": self.url()},
        }

    def tags(self) -> dict:
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

    def add_tag(self, payload: dict) -> dict:
        uid = payload.get("uid", "")
        system = payload.get("system", "")
        game = payload.get("game", "")
        name = payload.get("name", "")
        path = payload.get("path", "")
        if not system or not game:
            raise ValueError("systeme et jeu obligatoires")
        entry = self._tags().put(uid, system, game, name, path)
        if self.log:
            self.log.info("Badge %s ajoute depuis l'interface web (%s/%s)" % (uid, system, game))
        return {"ok": True, "uid": normalize_uid(uid), "entry": entry}

    def delete_tag(self, uid: str) -> dict:
        removed = self._tags().delete(uid)
        return {"ok": removed}

    def export_csv(self) -> str:
        store = self._tags()
        handle, path = tempfile.mkstemp(suffix=".csv", prefix="rfid-badges-")
        os.close(handle)
        try:
            store.export_csv(path)
            with open(path, "r", encoding="utf-8") as stream:
                return stream.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def import_csv(self, text: str) -> dict:
        handle, path = tempfile.mkstemp(suffix=".csv", prefix="rfid-import-")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(text)
            return self._tags().import_csv(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------- commandes
    def queue_command(self, command: str, **extra) -> dict:
        """Dépose une commande pour le service (association, scan simulé...)."""
        pid = read_pid(self.home)
        if not process_alive(pid):
            return {"ok": False, "error": "le service n'est pas demarre"}
        path = os.path.join(self.home, "web-command.json")
        payload = {"cmd": command, "ts": time.time()}
        payload.update(extra)
        temporary = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, path)
        return {"ok": True}

    def service_action(self, action: str) -> dict:
        if action not in ("start", "stop", "restart"):
            raise ValueError("action inconnue")
        if not os.path.isfile(self.main_py()):
            return {"ok": False, "error": "le programme n'est pas installe"}
        command = [sys.executable, self.main_py(), action, "--home", self.home]
        if action in ("stop", "restart"):
            # Le service sert cette page : on repond avant de l'arreter.
            threading.Timer(
                0.8,
                lambda: subprocess.Popen(
                    command,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ),
            ).start()
            return {"ok": True, "message": "demande envoyee (%s)" % action}
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, text=True
        )
        return {"ok": result.returncode == 0, "output": result.stdout or ""}

    def reboot(self) -> dict:
        threading.Timer(
            1.5,
            lambda: subprocess.Popen(
                ["sh", "-c", "sync; reboot"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
        ).start()
        return {"ok": True, "message": "Recalbox redemarre dans 2 secondes"}

    # ------------------------------------------------------------ installation
    def install_state(self) -> dict:
        return dict(self._install)

    def start_install(self, url=None, zip_bytes=None) -> dict:
        with self._install_guard:
            if self._install.get("state") == "running":
                raise RuntimeError("une installation est deja en cours")
            self._install = {
                "state": "running",
                "started": _iso(),
                "finished": "",
                "output": "",
                "code": None,
                "mode": "zip" if zip_bytes is not None else ("url" if url else "local"),
            }
        threading.Thread(
            target=self._install_worker, args=(url, zip_bytes), name="install", daemon=True
        ).start()
        return {"ok": True}

    def _install_worker(self, url=None, zip_bytes=None) -> None:
        output = ""
        code = -1
        started = time.time()
        try:
            installer = None
            if zip_bytes is not None:
                installer = self._installer_from_zip(zip_bytes)
            if installer is None:
                installer = self.installer()
            if installer is None:
                raise RuntimeError(
                    "install.sh introuvable : copiez le dossier du projet sur le partage "
                    "(\\\\RECALBOX\\share) puis rechargez cette page"
                )
            command = ["sh", installer, "--upgrade", "--no-restart", "--home", self.home]
            if url:
                command += ["--from-url", url]
            if self.log:
                self.log.info("Installation demandee depuis l'interface web (%s)" % installer)
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=900,
                text=True,
            )
            output = result.stdout or ""
            code = result.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout if isinstance(exc.stdout, str) else "") + "\n(temps depasse)"
            code = -1
        except FileNotFoundError as exc:
            output = (
                "Impossible de lancer l'installateur (%s).\n"
                "/bin/sh est necessaire : cette page doit tourner sur Recalbox."
                % exc
            )
            code = -1
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            output = str(exc)
            code = -1
        finally:
            self._install = {
                "state": "ok" if code == 0 else "error",
                "started": _iso(started),
                "finished": _iso(),
                "output": output[-40000:],
                "code": code,
                "mode": self._install.get("mode", ""),
            }
            self._append_install_log(output)
            if self.log:
                self.log.info("Installation web terminee (code %s)" % code)

    def _installer_from_zip(self, zip_bytes) -> str:
        folder = tempfile.mkdtemp(prefix="rfid-update-")
        archive = os.path.join(folder, "update.zip")
        with open(archive, "wb") as handle:
            handle.write(zip_bytes)
        extracted = os.path.join(folder, "src")
        os.makedirs(extracted, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        for root, _directories, files in os.walk(extracted):
            if "install.sh" in files:
                return os.path.join(root, "install.sh")
        raise RuntimeError("le fichier ZIP ne contient pas install.sh")

    def _append_install_log(self, output: str) -> None:
        if not output:
            return
        path = os.path.join(self.home, "logs", "install.log")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.isfile(path) and os.path.getsize(path) > 200000:
                os.replace(path, path + ".1")
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("\n===== %s =====\n" % _iso())
                handle.write(output)
                handle.write("\n")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Serveur HTTP
# ---------------------------------------------------------------------------
class _RequestHandler(BaseHTTPRequestHandler):
    server_version = "RecalboxRFID/" + __version__
    sys_version = ""

    # ------------------------------------------------------------------ log
    def log_message(self, fmt, *args):  # noqa: A003 - signature imposee
        ui = getattr(self.server, "webui", None)
        if ui is not None and ui.log is not None:
            ui.log.debug("web: " + (fmt % args))

    # --------------------------------------------------------------- helpers
    @property
    def ui(self) -> WebUI:
        return self.server.webui

    def _authorized(self) -> bool:
        password = self.ui.password
        if not password:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:].strip()).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            return False
        return decoded.partition(":")[2] == password

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urllib.parse.urlsplit(origin)
        except ValueError:
            return False
        return parsed.netloc == (self.headers.get("Host") or "")

    def _body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("Content-Length invalide")
        if length > MAX_BODY:
            raise ValueError("corps trop volumineux")
        return self.rfile.read(length) if length else b""

    def _json_body(self) -> dict:
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type not in ("application/json", "text/json"):
            raise ValueError("Content-Type application/json attendu")
        raw = self._body()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("objet JSON attendu")
        return payload

    def _send(self, code: int, payload: bytes, content_type: str, extra=None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._json({"error": message}, code)

    # ------------------------------------------------------------- méthodes
    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_HEAD(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")

    def do_DELETE(self):  # noqa: N802
        self._dispatch("DELETE")

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -------------------------------------------------------------- dispatch
    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)
        ui = self.ui

        if not self._authorized():
            self._send(
                401,
                b"Mot de passe requis",
                "text/plain; charset=utf-8",
                {"WWW-Authenticate": 'Basic realm="Recalbox RFID"'},
            )
            return
        if method in ("POST", "DELETE") and not self._origin_ok():
            self._error(403, "origine refusee")
            return

        try:
            if method == "GET":
                self._route_get(route, query)
            elif method == "POST":
                self._route_post(route)
            elif method == "DELETE":
                self._route_delete(route)
        except ValueError as exc:
            self._error(400, str(exc))
        except RuntimeError as exc:
            self._error(409, str(exc))
        except StorageError as exc:
            # Essentiellement des UID ou des entrees invalides.
            self._error(400, "badge invalide : %s" % exc)
        except Exception as exc:  # noqa: BLE001 - on ne casse pas le serveur
            if ui.log:
                ui.log.error("web: erreur sur %s : %s" % (route, exc))
            self._error(500, "erreur interne : %s" % exc)

    def _route_get(self, route: str, query: dict) -> None:
        ui = self.ui
        if route in ("/", "/index.html"):
            path = ui._index_path()  # noqa: SLF001
            if not path:
                self._send(500, b"index.html introuvable", "text/plain; charset=utf-8")
                return
            with open(path, "rb") as handle:
                self._send(200, handle.read(), "text/html; charset=utf-8")
            return
        if route == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if route == "/api/status":
            self._json(ui.status())
            return
        if route == "/api/tags":
            self._json(ui.tags())
            return
        if route == "/api/current":
            status = ui.status()
            self._json({"current": status["current"]})
            return
        if route == "/api/install/status":
            self._json(ui.install_state())
            return
        if route == "/api/export":
            text = ui.export_csv()
            self._send(
                200,
                text.encode("utf-8"),
                "text/csv; charset=utf-8",
                {"Content-Disposition": 'attachment; filename="badges-rfid.csv"'},
            )
            return
        if route == "/api/log":
            name = (query.get("name") or ["service"])[0]
            base = ui.home if ui.home else "."
            filename = {
                "service": os.path.join(base, "logs", "rfid.log"),
                "install": os.path.join(base, "logs", "install.log"),
                "startup": os.path.join(base, "logs", "service.out"),
            }.get(name)
            if not filename:
                self._error(404, "journal inconnu")
                return
            try:
                with open(filename, "r", encoding="utf-8", errors="replace") as handle:
                    lines = handle.readlines()[-200:]
            except OSError:
                lines = ["(journal vide : %s)" % filename]
            self._send(200, "".join(lines).encode("utf-8"), "text/plain; charset=utf-8")
            return
        self._error(404, "route inconnue")

    def _route_post(self, route: str) -> None:
        ui = self.ui
        if route == "/api/install":
            payload = self._json_body()
            url = (payload.get("url") or "").strip()
            self._json(ui.start_install(url=url or None))
            return
        if route == "/api/upload":
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type not in ("application/zip", "application/x-zip-compressed", "application/octet-stream"):
                raise ValueError("envoyez le fichier ZIP (application/zip)")
            data = self._body()
            if not data:
                raise ValueError("fichier vide")
            self._json(ui.start_install(zip_bytes=data))
            return
        if route == "/api/tags":
            self._json(ui.add_tag(self._json_body()))
            return
        if route == "/api/tags/delete":
            payload = self._json_body()
            uid = payload.get("uid") or ""
            if not uid:
                raise ValueError("UID manquant")
            self._json(ui.delete_tag(uid))
            return
        if route == "/api/import":
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type not in ("text/csv", "text/plain", "application/octet-stream"):
                raise ValueError("envoyez un fichier CSV")
            text = self._body().decode("utf-8-sig", "replace")
            self._json({"ok": True, "stats": ui.import_csv(text)})
            return
        if route == "/api/associate":
            payload = self._json_body()
            mode = payload.get("mode") or "associate"
            if mode not in ("associate", "delete"):
                raise ValueError("mode inconnu")
            self._json(ui.queue_command("arm_" + mode))
            return
        if route == "/api/scan":
            payload = self._json_body()
            uid = payload.get("uid") or ""
            if not uid:
                raise ValueError("UID manquant")
            self._json(ui.queue_command("simulate_scan", uid=normalize_uid(uid)))
            return
        if route == "/api/service":
            payload = self._json_body()
            self._json(ui.service_action(payload.get("action") or ""))
            return
        if route == "/api/reboot":
            self._json(ui.reboot())
            return
        self._error(404, "route inconnue")

    def _route_delete(self, route: str) -> None:
        ui = self.ui
        if route.startswith("/api/tags/"):
            uid = urllib.parse.unquote(route[len("/api/tags/"):])
            if not uid:
                raise ValueError("UID manquant")
            self._json(ui.delete_tag(uid))
            return
        self._error(404, "route inconnue")


def start_from_config(cfg, log, home=None, source=None, db=None):
    """Démarre l'interface web et retourne l'instance (ou None)."""
    if not cfg.get_bool("web", "enabled", True):
        if log:
            log.info("Interface web desactivee dans la configuration")
        return None
    ui = WebUI(cfg, log, home=home, source=source, db=db)
    if ui.start():
        return ui
    return None
