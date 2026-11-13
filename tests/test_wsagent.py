"""WebSocket agent tests (real server, minimal WebSocket client)."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import zipfile
from unittest import mock

import support  # noqa: F401  (adds app/ to sys.path)

from rfid import wsagent
from rfid.config import Config
from rfid.storage import pretty_uid

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WsError(Exception):
    pass


class WsClient:
    """Client WebSocket minimal (masque client, trames serveur non masquees)."""

    def __init__(self, host, port, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.buffer = bytearray()
        self.counter = 0
        self.events = []
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET / HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (host, port, key)
        )
        self.sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WsError("handshake ferme")
            response += chunk
        head, _, rest = response.partition(b"\r\n\r\n")
        self.buffer.extend(rest)
        self.head = head.decode("latin-1")
        if "101" not in self.head.split("\r\n")[0]:
            raise WsError("handshake refuse : %s" % self.head.split("\r\n")[0])
        expected = base64.b64encode(hashlib_sha1(key)).decode()
        if expected.lower() not in self.head.lower():
            raise WsError("Sec-WebSocket-Accept invalide")

    # ------------------------------------------------------------------ E/S
    def _read(self, count):
        while len(self.buffer) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WsError("connexion fermee")
            self.buffer.extend(chunk)
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data

    def _read_frame(self):
        first = self._read(2)
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read(8))[0]
        masked = first[1] & 0x80
        mask = self._read(4) if masked else b""
        payload = self._read(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return opcode, payload

    def send(self, payload):
        data = json.dumps(payload).encode("utf-8")
        mask = b"\x01\x02\x03\x04"
        header = bytearray([0x81])
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv(self):
        while True:
            opcode, payload = self._read_frame()
            if opcode == 0x8:
                raise WsError("ferme par le serveur")
            if opcode == 0x9:
                continue
            if opcode == 0x1:
                return json.loads(payload.decode("utf-8"))

    def next_event(self, timeout=5.0):
        if self.events:
            return self.events.pop(0)
        end = time.time() + timeout
        while time.time() < end:
            message = self.recv()
            if "event" in message:
                return message
            self.events.append(message)
        raise WsError("aucun evenement")

    def call(self, command, timeout=10.0, **payload):
        self.counter += 1
        request = {"id": self.counter, "cmd": command}
        request.update(payload)
        self.send(request)
        end = time.time() + timeout
        while time.time() < end:
            message = self.recv()
            if "event" in message:
                self.events.append(message)
                continue
            if message.get("id") == self.counter:
                if not message.get("ok"):
                    raise WsError(message.get("error") or "erreur")
                return message.get("data")
        raise WsError("delai depasse")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def hashlib_sha1(key: str) -> bytes:
    import hashlib

    return hashlib.sha1((key + GUID).encode()).digest()


class FakeProcess:
    def __init__(self, lines=(), code=0):
        self.stdout = iter(list(lines))
        self._code = code

    def wait(self):
        return self._code


class AgentTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfid-agent-")
        self.home = os.path.join(self.tmp, "home")
        self.share = os.path.join(self.tmp, "share")
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.share, exist_ok=True)
        self.config_path = os.path.join(self.home, "config.ini")
        self.agent = None
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        if self.agent is not None:
            self.agent.stop()
            time.sleep(0.2)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start_agent(self):
        config = Config(self.config_path)
        self.agent = wsagent.Agent(config, None, home=self.home, port=0)
        thread = threading.Thread(target=self.agent.serve_forever, daemon=True)
        thread.start()
        for _ in range(100):
            if self.agent.server is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(self.agent.server, "agent non demarre")
        self.port = self.agent.server.server_address[1]
        return self.agent

    def client(self):
        client = WsClient("127.0.0.1", self.port)
        self.clients.append(client)
        return client

    def button_pair(self, client):
        """Plays the 3 s press: request then grant, like the service."""
        request = client.call("pair.request")["request"]
        pending = wsagent.pairing.pending(self.home)
        wsagent.pairing.grant(self.home, pending, pending["created"] + 1.0)
        return client.call("pair.check", request=request)

    def authenticated_client(self):
        self.start_agent()
        client = self.client()
        client.call("auth", token=self.agent.token)
        return client


class SessionSecretTest(AgentTestCase):
    """No secret on the share: it lives in a private folder (0600)."""

    def session_path(self):
        return os.path.join(wsagent.pairing.state_dir(self.home), wsagent.SESSION_FILENAME)

    def test_aucun_secret_sur_le_partage(self):
        self.start_agent()
        self.assertGreaterEqual(len(self.agent.token), 16)
        self.assertEqual(self.agent.token_path, "")
        self.assertFalse(os.path.isfile(os.path.join(self.home, "token.txt")))
        self.assertFalse(os.path.isfile(os.path.join(self.home, "paired.ok")))
        # ...and the session secret is stored in the dedicated private folder
        self.assertEqual(
            os.path.dirname(self.session_path()), wsagent.pairing.state_dir(self.home)
        )

    def test_secret_garde_hors_du_partage(self):
        self.start_agent()
        chemin = self.session_path()
        self.assertTrue(os.path.isfile(chemin), chemin)
        with open(chemin, encoding="ascii") as handle:
            self.assertEqual(handle.read().strip(), self.agent.token)
        if os.name != "nt":
            self.assertEqual(os.stat(chemin).st_mode & 0o777, 0o600)

    def test_secret_conserve_apres_redemarrage_du_service(self):
        # An update or a service restart must not ask for the button press again.
        self.start_agent()
        premier = self.agent.token
        self.agent.stop()
        time.sleep(0.2)
        self.agent = None
        self.start_agent()
        self.assertEqual(self.agent.token, premier)

    def test_secret_renouvele_apres_perte(self):
        # Full reboot (empty tmpfs): new secret, so a new press.
        self.start_agent()
        premier = self.agent.token
        self.agent.stop()
        time.sleep(0.2)
        self.agent = None
        os.remove(self.session_path())
        self.start_agent()
        self.assertNotEqual(self.agent.token, premier)

    def test_anciens_fichiers_supprimes(self):
        for name in ("token.txt", wsagent.PAIRED_FILENAME):
            with open(os.path.join(self.home, name), "w", encoding="ascii") as handle:
                handle.write("VIEUXJETON\n")
        self.start_agent()
        self.assertFalse(os.path.isfile(os.path.join(self.home, "token.txt")))
        self.assertFalse(os.path.isfile(os.path.join(self.home, wsagent.PAIRED_FILENAME)))


class PairingTest(AgentTestCase):
    """Pairing: no token can be handed over without a physical press on the button."""

    def test_commande_pair_supprimee(self):
        self.start_agent()
        with self.assertRaises(WsError) as context:
            self.client().call("pair")
        self.assertIn("bouton", str(context.exception).lower())

    def test_fichier_pair_request_ignore(self):
        # A request dropped on the share must give NOTHING: that is the hole a
        # computer on the network could use to get the token without a press.
        with open(os.path.join(self.home, "pair-request"), "w", encoding="utf-8") as handle:
            handle.write("\n")
        self.start_agent()
        with self.assertRaises(WsError):
            self.client().call("pair")

    def test_auth_sans_secret_refusee(self):
        self.start_agent()
        with self.assertRaises(WsError) as context:
            self.client().call("auth", token="")
        self.assertIn("appairage", str(context.exception).lower())

    def test_auth_reussie_ferme_la_fenetre(self):
        self.start_agent()
        self.assertTrue(wsagent.pairing_is_open(self.home))
        self.client().call("auth", token=self.agent.token)
        self.assertFalse(wsagent.pairing_is_open(self.home))

    def test_adresse_privee(self):
        self.assertTrue(wsagent.is_private_address(("192.168.42.46", 5555)))
        self.assertTrue(wsagent.is_private_address(("10.0.0.2", 1)))
        self.assertTrue(wsagent.is_private_address(("172.20.1.1", 1)))
        self.assertTrue(wsagent.is_private_address(("127.0.0.1", 1)))
        self.assertFalse(wsagent.is_private_address(("8.8.8.8", 53)))
        self.assertFalse(wsagent.is_private_address(("172.40.0.1", 1)))


class ButtonPairingTest(AgentTestCase):
    """Pairing confirmed with the button: request, grant, token."""

    def fake_service(self):
        """Simulates a running service (the current PID is indeed alive)."""
        with open(os.path.join(self.home, "rfid.pid"), "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))

    def test_demande_refusee_sans_service(self):
        self.start_agent()
        client = self.client()
        with self.assertRaises(WsError) as context:
            client.call("pair.request")
        self.assertIn("service", str(context.exception))

    def test_demande_puis_validation_au_bouton(self):
        self.fake_service()
        self.start_agent()
        client = self.client()
        data = client.call("pair.request")
        request_id = data["request"]
        self.assertEqual(len(request_id), 8)
        self.assertGreater(data["seconds"], 0)

        # Nothing until the button has been held.
        premier = client.call("pair.check", request=request_id)
        self.assertFalse(premier["accepted"])
        self.assertTrue(premier["pending"])

        # The service records the long press on the pending request.
        pending = wsagent.pairing.pending(self.home)
        # The press starts after the request (250 ms anti-replay margin).
        self.assertTrue(wsagent.pairing.grant(self.home, pending, pending["created"] + 1.0))

        accepte = client.call("pair.check", request=request_id)
        self.assertTrue(accepte["accepted"])
        self.assertEqual(accepte["token"], self.agent.token)
        # The grant is consumed: a second call does not give the token again.
        self.assertFalse(client.call("pair.check", request=request_id)["accepted"])

    def test_une_seule_demande_a_la_fois(self):
        self.fake_service()
        self.start_agent()
        premier = self.client()
        premier.call("pair.request")
        second = self.client()
        with self.assertRaises(WsError) as context:
            second.call("pair.request")
        self.assertIn("deja en attente", str(context.exception))

    def test_accord_d_une_autre_demande_ignore(self):
        self.fake_service()
        self.start_agent()
        client = self.client()
        premiere = client.call("pair.request")["request"]
        pending = wsagent.pairing.pending(self.home)
        # The press starts after the request (250 ms anti-replay margin).
        self.assertTrue(wsagent.pairing.grant(self.home, pending, pending["created"] + 1.0))
        # Another client asks for a token for an id it makes up.
        data = client.call("pair.check", request="AUTRE123")
        self.assertFalse(data["accepted"])
        self.assertNotIn("token", data)


class InstallerChoiceTest(AgentTestCase):
    """The right install.sh is picked: the share if newer, never a downgrade."""

    def prepare(self, installed, shared):
        source = os.path.join(self.tmp, "share-src")
        os.makedirs(source, exist_ok=True)
        with open(os.path.join(source, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        with open(os.path.join(source, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write(shared + "\n")
        with open(os.path.join(self.home, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        with open(os.path.join(self.home, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write(installed + "\n")
        self.agent = wsagent.Agent(Config(self.config_path), None, home=self.home, port=0)
        self.agent.source = source
        return self.agent

    def test_partage_plus_recent(self):
        agent = self.prepare("2.0.2", "2.2.0")
        self.assertEqual(agent.installer(), os.path.join(agent.source, "install.sh"))

    def test_partage_plus_ancien_ignore(self):
        agent = self.prepare("2.2.0", "1.8.2")
        self.assertEqual(agent.installer(), os.path.join(self.home, "install.sh"))

    def test_versions_egales_utilisent_le_partage(self):
        agent = self.prepare("2.2.0", "2.2.0")
        self.assertEqual(agent.installer(), os.path.join(agent.source, "install.sh"))

    def test_version_key(self):
        self.assertEqual(wsagent.version_key("2.10.1"), (2, 10, 1))
        self.assertGreater(wsagent.version_key("2.10.0"), wsagent.version_key("2.9.9"))
        self.assertEqual(wsagent.version_key(""), ())


class ProtocolTest(AgentTestCase):
    def _http(self, request: bytes) -> bytes:
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        try:
            sock.sendall(request)
            data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    return data
                data += chunk
        finally:
            sock.close()

    def test_handshake_non_websocket(self):
        self.start_agent()
        response = self._http(b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        self.assertIn(b"400", response[:40])

    def test_page_refusee_sous_un_nom_inconnu(self):
        """DNS rebinding: a foreign host name never gets the page."""
        self.start_agent()
        response = self._http(b"GET / HTTP/1.1\r\nHost: evil.example:8765\r\n\r\n")
        self.assertIn(b"403", response[:40])

    def test_page_servie_au_telephone(self):
        self.start_agent()
        os.makedirs(os.path.join(self.home, "web"), exist_ok=True)
        with open(os.path.join(self.home, "web", "index.html"), "w", encoding="utf-8") as handle:
            handle.write("<!DOCTYPE html><html><head><title>t</title></head><body>ok</body></html>")
        response = self._http(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n")
        self.assertIn(b"200 OK", response[:40])
        self.assertIn(b'<meta name="rfid-agent" content="1">', response)
        self.assertIn(b"no-store", response)
        missing = self._http(b"GET /secret.json HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        self.assertIn(b"404", missing[:40])

    def test_authentification_requise(self):
        self.start_agent()
        client = self.client()
        with self.assertRaises(WsError) as context:
            client.call("status")
        self.assertIn("authentification", str(context.exception))

    def test_jeton_invalide_ferme_la_connexion(self):
        self.start_agent()
        client = self.client()
        for _ in range(3):
            client.send({"id": 1, "cmd": "auth", "token": "mauvais"})
            message = client.recv()
            self.assertFalse(message["ok"])
        with self.assertRaises((WsError, OSError)):
            client.recv()

    def test_commande_inconnue(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError) as context:
            client.call("bidule")
        self.assertIn("inconnue", str(context.exception))


class StatusTest(AgentTestCase):
    def test_status(self):
        client = self.authenticated_client()
        data = client.call("status")
        self.assertIn("app_version", data)
        self.assertFalse(data["installed"])
        self.assertTrue(data["agent"]["session"], "session attendue ouverte")
        self.assertNotIn("token", data["agent"])
        self.assertEqual(data["tags"], 0)

    def test_version(self):
        client = self.authenticated_client()
        self.assertIn("version", client.call("version"))


class TagsTest(AgentTestCase):
    def test_cycle_complet(self):
        client = self.authenticated_client()
        client.call("tags.add", uid="a1:b2:c3:d4", system="snes", game="jeu.smc", name="Jeu")
        listing = client.call("tags.list")
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["tags"][0]["pretty"], "A1:B2:C3:D4")

        exported = client.call("tags.export")["csv"]
        self.assertIn("uid;system;game;name", exported)

        client.call("tags.remove", uid="A1B2C3D4")
        self.assertEqual(client.call("tags.list")["count"], 0)

        stats = client.call("tags.import", csv=exported)["stats"]
        self.assertEqual(stats["ajoutes"], 1)
        self.assertEqual(client.call("tags.list")["count"], 1)

    def test_uid_invalide(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("tags.add", uid="ZZ", system="snes", game="jeu.smc")

    def test_champs_manquants(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("tags.add", uid="A1B2C3D4", system="snes")

    def test_jeu_choisi_dans_la_liste(self):
        """The page sends only the full path of the picked game."""
        client = self.authenticated_client()
        client.call("tags.add", uid="A1B2C3D4", system="snes",
                    path="/recalbox/share/roms/snes/Platform/Mario World.smc", name="Mario World")
        tag = client.call("tags.list")["tags"][0]
        self.assertEqual(tag["game"], "Platform/Mario World.smc")
        self.assertEqual(tag["path"], "/recalbox/share/roms/snes/Platform/Mario World.smc")


class InstallTest(AgentTestCase):
    def setUp(self):
        super().setUp()
        # The install thread goes on after the answer: the agent restart is
        # disabled for the whole duration of the tests.
        self._after_patch = mock.patch.object(
            wsagent.Agent, "_after_install", lambda self, client: None
        )
        self._after_patch.start()
        self.installer = os.path.join(self.home, "install.sh")
        with open(self.installer, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")

    def tearDown(self):
        self._after_patch.stop()
        super().tearDown()

    def test_installation_en_flux(self):
        client = self.authenticated_client()
        recorded = {}

        def fake_popen(command, **kwargs):
            recorded["command"] = command
            return FakeProcess(["ligne 1", "ligne 2"], 0)

        with mock.patch.object(wsagent.subprocess, "Popen", fake_popen):
            started = client.call("install")
            self.assertTrue(started["started"])
            events = []
            for _ in range(6):
                events.append(client.next_event())
                if events[-1].get("event") == "install" and events[-1].get("state") != "running":
                    break

        kinds = [event["event"] for event in events]
        self.assertIn("log", kinds)
        self.assertIn("install", kinds)
        self.assertEqual(events[-1]["state"], "ok")
        self.assertIn("--no-restart", recorded["command"])
        self.assertIn("--upgrade", recorded["command"])

    def test_installation_en_echec(self):
        client = self.authenticated_client()
        with mock.patch.object(wsagent.subprocess, "Popen", lambda *a, **k: FakeProcess(["boum"], 2)):
            client.call("install")
            state = None
            for _ in range(8):
                event = client.next_event()
                if event.get("event") == "install" and event.get("state") != "running":
                    state = event["state"]
                    break
        self.assertEqual(state, "error")

    def test_aucun_installateur(self):
        os.remove(self.installer)
        client = self.authenticated_client()
        with self.assertRaises(WsError) as context:
            client.call("install")
        self.assertIn("install.sh", str(context.exception))

    def test_upload_zip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("recalbox-rfid/install.sh", "#!/bin/sh\n")
        payload = buffer.getvalue()

        client = self.authenticated_client()
        recorded = {}

        def fake_popen(command, **kwargs):
            recorded["command"] = command
            return FakeProcess(["ok"], 0)

        client.call("upload.begin", size=len(payload))
        chunk = 4096
        for offset in range(0, len(payload), chunk):
            data = base64.b64encode(payload[offset:offset + chunk]).decode()
            client.call("upload.chunk", data=data)
        with mock.patch.object(wsagent.subprocess, "Popen", fake_popen):
            client.call("upload.end")
            client.next_event()
        self.assertTrue(recorded["command"][1].endswith("install.sh"))
        self.assertIn("rfid-update-", recorded["command"][1])

    def test_upload_trop_long(self):
        client = self.authenticated_client()
        client.call("upload.begin", size=10)
        with self.assertRaises(WsError):
            client.call("upload.chunk", data=base64.b64encode(b"x" * 20).decode())


class InstallSkipTest(AgentTestCase):
    """An installation without a version change must restart nothing."""

    def setUp(self):
        super().setUp()
        self._after_patch = mock.patch.object(
            wsagent.Agent, "_after_install", lambda self, client: None
        )
        self._after_patch.start()

    def tearDown(self):
        self._after_patch.stop()
        super().tearDown()

    def prepare(self, installed, shared, service, running_service=True):
        """Prepares the source folder, the installed program and the service state."""
        source = os.path.join(self.tmp, "share-src")
        os.makedirs(os.path.join(source, "app"), exist_ok=True)
        for base, version in ((source, shared), (self.home, installed)):
            for name, text in (
                ("install.sh", "#!/bin/sh\n"),
                ("VERSION", version + "\n"),
                (os.path.join("app", "main.py"), "#\n"),
            ):
                path = os.path.join(base, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
        with open(os.path.join(self.home, "status.json"), "w", encoding="utf-8") as handle:
            json.dump({"version": service}, handle)
        self.source = source

    def start(self):
        config = Config(self.config_path)
        self.agent = wsagent.Agent(config, None, home=self.home, port=0)
        self.agent.source = self.source
        thread = threading.Thread(target=self.agent.serve_forever, daemon=True)
        thread.start()
        for _ in range(100):
            if self.agent.server is not None:
                break
            time.sleep(0.05)
        self.port = self.agent.server.server_address[1]
        client = self.client()
        client.call("auth", token=self.agent.token)
        return client

    def test_meme_version_ne_relance_rien(self):
        self.prepare("2.5.2", "2.5.2", "2.5.2")
        client = self.start()
        with mock.patch.object(wsagent.subprocess, "Popen", side_effect=AssertionError("relance")):
            data = client.call("install")
        self.assertTrue(data.get("skipped"))
        self.assertEqual(data.get("installed_version"), "2.5.2")

    def test_service_en_retard_relance(self):
        self.prepare("2.5.2", "2.5.2", "2.4.0")
        client = self.start()
        recorded = {}

        def fake_popen(command, **kwargs):
            recorded["command"] = command
            return FakeProcess(["ok"], 0)

        with mock.patch.object(wsagent.subprocess, "Popen", fake_popen):
            data = client.call("install")
        self.assertTrue(data.get("started"))
        self.assertIn("--upgrade", recorded["command"])

    def test_version_plus_recente_relance(self):
        self.prepare("2.4.0", "2.5.2", "2.4.0")
        client = self.start()
        recorded = {}

        def fake_popen(command, **kwargs):
            recorded["command"] = command
            return FakeProcess(["ok"], 0)

        with mock.patch.object(wsagent.subprocess, "Popen", fake_popen):
            data = client.call("install")
        self.assertTrue(data.get("started"))
        self.assertTrue(recorded["command"][1].startswith(self.source))

    def test_force_reinstalle(self):
        self.prepare("2.5.2", "2.5.2", "2.5.2")
        client = self.start()

        def fake_popen(command, **kwargs):
            return FakeProcess(["ok"], 0)

        with mock.patch.object(wsagent.subprocess, "Popen", fake_popen):
            data = client.call("install", force=True)
        self.assertTrue(data.get("started"))

    def test_status_expose_la_version_source(self):
        self.prepare("2.5.2", "2.5.2", "2.5.2")
        client = self.start()
        data = client.call("status")
        self.assertEqual(data.get("source_version"), "2.5.2")
        self.assertEqual(data.get("installed_version"), "2.5.2")


class RestartAfterInstallTest(AgentTestCase):
    """After an installation, the service must reload the new code."""

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.home, "app"), exist_ok=True)
        with open(os.path.join(self.home, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("#\n")
        self.service = wsagent.Agent(Config(self.config_path), None, home=self.home, port=0)

    def test_service_arrete_demarre(self):
        recorded = {}
        with mock.patch.object(wsagent.subprocess, "run", lambda command, **k: recorded.update(command=command)):
            self.service._restart_service()
        self.assertEqual(recorded["command"][2], "start")

    def test_service_actif_redemarre(self):
        with open(os.path.join(self.home, "rfid.pid"), "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
        recorded = {}
        with mock.patch.object(wsagent.subprocess, "run", lambda command, **k: recorded.update(command=command)):
            self.service._restart_service()
        self.assertEqual(recorded["command"][2], "restart")

    def test_sans_programme_aucun_lancement(self):
        os.remove(os.path.join(self.home, "app", "main.py"))
        with mock.patch.object(wsagent.subprocess, "run", side_effect=AssertionError("lancement")):
            self.service._restart_service()


class ReaderTestCommandTest(AgentTestCase):
    """The reader test goes through the service (sole owner of the SPI bus)."""

    def test_refuse_sans_service(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError) as context:
            client.call("reader.test", seconds=3)
        self.assertIn("service", str(context.exception))

    def test_duree_bornee(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("reader.test", seconds="beaucoup")
        # absurd duration but service stopped: the refusal comes from the service
        with self.assertRaises(WsError):
            client.call("reader.test", seconds=500)


class ServiceTest(AgentTestCase):
    def test_association_sans_service(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError) as context:
            client.call("associate", mode="associate")
        self.assertIn("service", str(context.exception))

    def test_service_sans_programme(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError) as context:
            client.call("service", action="start")
        self.assertIn("installe", str(context.exception))

    def test_action_inconnue(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("service", action="explode")

    def test_redemarrage_recalbox(self):
        client = self.authenticated_client()
        with mock.patch.object(wsagent.subprocess, "Popen", lambda *a, **k: FakeProcess([], 0)):
            data = client.call("reboot")
        self.assertIn("message", data)


class ConfigCommandTest(AgentTestCase):
    """Settings exposed in the page's Settings tab."""

    def setUp(self):
        super().setUp()
        Config(self.config_path).create_default()

    def lire(self, nom="config.ini"):
        with open(os.path.join(self.home, nom), "r", encoding="utf-8") as handle:
            return handle.read()

    def test_liste_les_options_avec_leur_valeur(self):
        client = self.authenticated_client()
        data = client.call("config.get")
        options = {o["full"]: o for o in data["options"]}
        self.assertIn("launch.stop_on_remove", options)
        self.assertIn("launch.action", options)
        self.assertIn("button.hold_press_s", options)
        self.assertEqual(options["launch.stop_on_remove"]["value"], "0")
        self.assertEqual(options["rfid.rearm_absent_ms"]["value"], "1200")
        self.assertEqual(options["launch.action"]["type"], "choice")
        self.assertIn("launch", options["launch.action"]["choices"])
        self.assertTrue(options["launch.stop_on_remove"]["label"])

    def test_enregistre_une_valeur(self):
        client = self.authenticated_client()
        data = client.call("config.set", values={"launch.stop_on_remove": "1"})
        self.assertEqual(data["saved"], ["launch.stop_on_remove"])
        self.assertFalse(data["reloaded"])  # service stopped: nothing to reload
        self.assertTrue(Config(self.config_path).get_bool("launch", "stop_on_remove", False))
        apres = client.call("config.get")
        valeurs = {o["full"]: o["value"] for o in apres["options"]}
        self.assertEqual(valeurs["launch.stop_on_remove"], "1")

    def test_conserve_les_commentaires_du_fichier(self):
        avant = self.lire()
        commentaires = [l for l in avant.split("\n") if l.strip().startswith("#")]
        client = self.authenticated_client()
        client.call("config.set", values={"rfid.rearm_absent_ms": "2500"})
        apres = self.lire()
        restants = [l for l in apres.split("\n") if l.strip().startswith("#")]
        self.assertEqual(len(restants), len(commentaires))
        self.assertIn("rearm_absent_ms = 2500", apres)

    def test_valeurs_normalisees(self):
        client = self.authenticated_client()
        client.call(
            "config.set",
            values={"launch.stop_on_remove": "oui", "feedback.sound": "non", "button.arm_timeout_s": 12.0},
        )
        cfg = Config(self.config_path)
        self.assertTrue(cfg.get_bool("launch", "stop_on_remove", False))
        self.assertFalse(cfg.get_bool("feedback", "sound", True))
        self.assertIn("arm_timeout_s = 12", self.lire())

    def test_option_inconnue_refusee(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("config.set", values={"launch.inconnue": "1"})

    def test_choix_invalide_refuse(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("config.set", values={"launch.action": "explosion"})

    def test_nombre_hors_bornes_refuse(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("config.set", values={"button.hold_press_s": "99"})
        self.assertIn("hold_press_s = 3", self.lire())

    def test_nombre_invalide_refuse(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("config.set", values={"rfid.rearm_absent_ms": "beaucoup"})

    def test_booleen_invalide_refuse(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("config.set", values={"feedback.sound": "peut-etre"})

    def test_sans_valeur_refuse(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("config.set", values={})

    def test_rechargement_du_service(self):
        with open(os.path.join(self.home, "rfid.pid"), "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
        client = self.authenticated_client()
        with mock.patch.object(wsagent.os, "kill") as tue:
            data = client.call("config.set", values={"feedback.sound": "0"})
        self.assertTrue(data["reloaded"])
        tue.assert_called_once()

    def test_acces_authentifie_obligatoire(self):
        self.start_agent()
        client = self.client()
        with self.assertRaises(WsError):
            client.call("config.get")


class CalibrationCommandTest(AgentTestCase):
    """Automatic reader measurement: start, follow-up, cancel, reset."""

    def setUp(self):
        super().setUp()
        Config(self.config_path).create_default()
        self.calibration_path = os.path.join(self.home, "calibration.json")

    def ecrire_etat(self, **valeurs):
        etat = {"phase": "idle", "finished": True, "instruct": "", "measures": {},
                "applied": {}, "error": ""}
        etat.update(valeurs)
        with open(self.calibration_path, "w", encoding="utf-8") as handle:
            json.dump(etat, handle)
        return etat

    def commande_deposee(self):
        path = os.path.join(self.home, "agent-command.json")
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def service_actif(self):
        with open(os.path.join(self.home, "rfid.pid"), "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
        with open(os.path.join(self.home, "status.json"), "w", encoding="utf-8") as handle:
            json.dump({"version": wsagent.__version__}, handle)

    def test_refuse_sans_service(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError) as contexte:
            client.call("calibrate.start")
        self.assertIn("service", str(contexte.exception))

    def test_lance_la_mesure(self):
        self.service_actif()
        client = self.authenticated_client()
        data = client.call("calibrate.start")
        self.assertTrue(data["started"])
        commande = self.commande_deposee()
        self.assertEqual(commande["cmd"], "calibrate_start")

    def test_refuse_si_une_mesure_tourne(self):
        self.service_actif()
        self.ecrire_etat(phase="read", finished=False)
        client = self.authenticated_client()
        with self.assertRaises(WsError) as contexte:
            client.call("calibrate.start")
        self.assertIn("deja en cours", str(contexte.exception))

    def test_relance_apres_une_mesure_terminee(self):
        self.service_actif()
        self.ecrire_etat(phase="done", finished=True)
        client = self.authenticated_client()
        self.assertTrue(client.call("calibrate.start")["started"])

    def test_etat_absent(self):
        client = self.authenticated_client()
        data = client.call("calibrate.status")
        self.assertEqual(data["phase"], "idle")

    def test_etat_transmis(self):
        self.ecrire_etat(phase="remove", finished=False, instruct="remove_badge",
                         measures={"read_ms": 47.2})
        client = self.authenticated_client()
        data = client.call("calibrate.status")
        self.assertEqual(data["instruct"], "remove_badge")
        self.assertEqual(data["measures"], {"read_ms": 47.2})

    def test_annulation(self):
        self.service_actif()
        client = self.authenticated_client()
        self.assertTrue(client.call("calibrate.cancel")["cancelled"])
        self.assertEqual(self.commande_deposee()["cmd"], "calibrate_cancel")

    def test_reinitialisation(self):
        self.service_actif()
        client = self.authenticated_client()
        # The service writes the "reset" state while the agent waits.
        def repondre(*args, **kwargs):
            self.ecrire_etat(phase="reset", applied={"rfid.poll_interval_ms": ["80", "150"]})
            return None

        with mock.patch.object(wsagent.Agent, "_write_command", side_effect=repondre):
            data = client.call("calibrate.reset", timeout=15)
        self.assertEqual(data["applied"]["rfid.poll_interval_ms"], ["80", "150"])

    def test_acces_authentifie_obligatoire(self):
        self.start_agent()
        client = self.client()
        with self.assertRaises(WsError):
            client.call("calibrate.status")


def _frame(opcode, payload, fin=True):
    """Masked client frame, as a browser sends it."""
    mask = b"\x0a\x0b\x0c\x0d"
    head = bytearray([(0x80 if fin else 0) | opcode])
    length = len(payload)
    if length < 126:
        head.append(0x80 | length)
    elif length < 65536:
        head.append(0x80 | 126)
        head += struct.pack("!H", length)
    else:
        head.append(0x80 | 127)
        head += struct.pack("!Q", length)
    return bytes(head) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class FragmentationTest(unittest.TestCase):
    """Chromium splits large messages: the agent must reassemble them."""

    def setUp(self):
        self.left, self.right = socket.socketpair()
        self.client = wsagent._Client(self.right, ("test", 0))

    def tearDown(self):
        self.left.close()
        self.right.close()

    def test_message_fragmente_reassemble(self):
        data = json.dumps({"id": 7, "cmd": "upload.chunk", "data": "A" * 150000}).encode()
        parts = [data[:60000], data[60000:120000], data[120000:]]
        self.left.sendall(
            _frame(0x1, parts[0], fin=False)
            + _frame(0x0, parts[1], fin=False)
            + _frame(0x0, parts[2], fin=True)
        )
        opcode, payload = wsagent._read_message(self.client)
        self.assertEqual(opcode, 0x1)
        self.assertEqual(json.loads(payload)["id"], 7)

    def test_ping_entre_deux_fragments(self):
        pings = []
        self.left.sendall(
            _frame(0x1, b'{"id": 1,', fin=False)
            + _frame(0x9, b"ping")
            + _frame(0x0, b' "cmd": "status"}', fin=True)
        )
        opcode, payload = wsagent._read_message(self.client, lambda op, p: pings.append((op, p)))
        self.assertEqual(json.loads(payload), {"id": 1, "cmd": "status"})
        self.assertEqual(pings, [(0x9, b"ping")])

    def test_message_simple_inchange(self):
        self.left.sendall(_frame(0x1, b'{"id": 2}'))
        self.assertEqual(wsagent._read_message(self.client), (0x1, b'{"id": 2}'))

    def test_continuation_orpheline_refusee(self):
        self.left.sendall(_frame(0x0, b"reste", fin=True))
        with self.assertRaises(wsagent.ProtocolError):
            wsagent._read_message(self.client)

    def test_fermeture_renvoyee(self):
        self.left.sendall(_frame(0x8, b""))
        self.assertEqual(wsagent._read_message(self.client)[0], 0x8)


class FakeLibrary:
    def systems(self, force=False):
        return [{"id": "snes", "name": "Super Nintendo", "manufacturer": "", "region": ""}]

    def search(self, query="", system="", limit=60):
        return [{"system": "snes", "path": "/recalbox/share/roms/snes/Mario.smc", "name": "Mario",
                 "favorite": False, "genre": ""}][:limit]

    def game_image(self, system, path):
        return ("image/png", b"PNG") if path.endswith("Mario.smc") else None

    def system_logo(self, system, kind="logo", region=""):
        return ("image/svg+xml", b"<svg/>")


class CardsCommandsTest(AgentTestCase):
    """Library, special cards and card templates, from the page."""

    def client_with_library(self):
        client = self.authenticated_client()
        self.agent.library = FakeLibrary()
        return client

    def test_recherche_et_images(self):
        client = self.client_with_library()
        self.assertEqual(client.call("games.systems")["systems"][0]["id"], "snes")
        self.assertEqual(client.call("games.search", query="mar")["games"][0]["name"], "Mario")
        image = client.call("media.image", system="snes", path="/recalbox/share/roms/snes/Mario.smc")
        self.assertEqual(base64.b64decode(image["data"]), b"PNG")
        self.assertFalse(client.call("media.image", system="snes", path="/x.smc")["found"])
        self.assertEqual(client.call("media.logo", system="snes")["svg"], "<svg/>")

    def test_associer_un_jeu_choisi(self):
        client = self.authenticated_client()
        recorded = {}
        with mock.patch.object(wsagent, "process_alive", return_value=True), \
                mock.patch.object(wsagent.Agent, "_write_command",
                                  lambda self, command, **extra: recorded.update(command=command, **extra)):
            client.call("associate", mode="associate",
                        target={"system": "snes", "path": "/recalbox/share/roms/snes/Mario.smc", "name": "Mario"})
        self.assertEqual(recorded["command"], "arm_target")
        self.assertEqual(recorded["target"]["path"], "/recalbox/share/roms/snes/Mario.smc")

    def test_creer_une_carte_speciale(self):
        client = self.authenticated_client()
        recorded = {}
        with mock.patch.object(wsagent, "process_alive", return_value=True), \
                mock.patch.object(wsagent.Agent, "_write_command",
                                  lambda self, command, **extra: recorded.update(command=command, **extra)):
            data = client.call("associate", mode="card",
                               entry={"kind": "action", "action": "bonus", "params": {"minutes": 15}})
            with self.assertRaises(WsError) as context:
                client.call("associate", mode="card", entry={"kind": "action", "action": "rm -rf"})
        self.assertEqual(recorded["command"], "arm_entry")
        self.assertEqual(data["entry"]["params"]["minutes"], 15)
        self.assertIn("inconnue", str(context.exception))

    def test_modifier_un_badge(self):
        client = self.authenticated_client()
        client.call("tags.add", uid="A1B2C3D4", system="snes", game="Mario.smc")
        entry = client.call("tags.update", uid="A1B2C3D4", changes={"limit_min": 25, "name": "Mario"})["entry"]
        self.assertEqual(entry["limit_min"], 25)
        listed = client.call("tags.list")["tags"][0]
        self.assertEqual((listed["kind"], listed["limit_min"], listed["name"]), ("game", 25, "Mario"))

    def test_modeles_de_carte(self):
        client = self.authenticated_client()
        saved = client.call("cards.template.save", template={"name": "Penché", "orientation": "portrait",
                                                              "template": "cartouche", "layers": {}})["template"]
        self.assertTrue(saved["id"])
        self.assertEqual([t["name"] for t in client.call("cards.templates")["templates"]], ["Penché"])
        client.call("cards.template.save", template=dict(saved, name="Renommé"))
        self.assertEqual([t["name"] for t in client.call("cards.templates")["templates"]], ["Renommé"])
        self.assertTrue(client.call("cards.template.delete", template=saved["id"])["removed"])
        self.assertEqual(client.call("cards.templates")["templates"], [])
        with self.assertRaises(WsError):
            client.call("cards.template.save", template={"name": "", "layers": {}})
        with self.assertRaises(WsError):
            client.call("cards.template.save", template={"name": "gros", "blob": "x" * 70000})

    def test_ecrire_le_jeu_dans_le_badge(self):
        client = self.authenticated_client()
        client.call("tags.add", uid="A1B2C3D4", system="snes", game="Mario.smc",
                    path="/recalbox/share/roms/snes/Mario.smc")
        recorded = {}

        def service(agent, command, **extra):
            recorded.update(command=command, **extra)
            with open(os.path.join(self.home, "tag-write.json"), "w", encoding="utf-8") as handle:
                json.dump({"state": "done", "bytes": 19}, handle)

        with mock.patch.object(wsagent, "process_alive", return_value=True), \
                mock.patch.object(wsagent.Agent, "_write_command", service):
            data = client.call("tags.write", uid="A1:B2:C3:D4", timeout=15)
        self.assertTrue(data["written"])
        self.assertEqual(recorded["command"], "write_tag")
        self.assertEqual(bytes.fromhex(recorded["data"]), b"RL1|snes|Mario.smc\x00")

    def test_une_carte_speciale_ne_s_ecrit_pas(self):
        client = self.authenticated_client()
        self.agent._tags().put_entry("B1B2C3D4", {"kind": "action", "action": "quit"})
        with self.assertRaises(WsError):
            client.call("tags.write", uid="B1B2C3D4")

    def test_status_donne_l_adresse_du_telephone(self):
        client = self.authenticated_client()
        agent_info = client.call("status")["agent"]
        self.assertIn("ip", agent_info)
        self.assertFalse(agent_info["web"])


class SameOriginTest(unittest.TestCase):
    def test_page_servie_par_l_agent(self):
        self.assertTrue(wsagent.same_origin("http://192.168.1.20:8765", "192.168.1.20:8765"))
        self.assertTrue(wsagent.same_origin("http://recalbox.local:8765", "recalbox.local:8765"))
        self.assertFalse(wsagent.same_origin("http://evil.example:8765", "evil.example:8765"))
        self.assertFalse(wsagent.same_origin("https://192.168.1.20:8765", "192.168.1.20:8765"))
        self.assertFalse(wsagent.same_origin("http://192.168.1.20:8765", ""))

    def test_noms_locaux(self):
        self.assertTrue(wsagent.local_host_header("[fe80::1]:8765"))
        self.assertTrue(wsagent.local_host_header("RECALBOX:8765"))
        self.assertFalse(wsagent.local_host_header("192.168.1.20.nip.io:8765"))


if __name__ == "__main__":
    unittest.main()
