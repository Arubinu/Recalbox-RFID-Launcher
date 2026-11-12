"""Tests de l'agent WebSocket (serveur réel, client WebSocket minimal)."""

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

import support  # noqa: F401  (ajoute app/ au sys.path)

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
        """Joue l'appui de 3 s : demande puis accord, comme le service."""
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
    """Aucun secret sur le partage : il vit dans un dossier prive (0600)."""

    def session_path(self):
        return os.path.join(wsagent.pairing.state_dir(self.home), wsagent.SESSION_FILENAME)

    def test_aucun_secret_sur_le_partage(self):
        self.start_agent()
        self.assertGreaterEqual(len(self.agent.token), 16)
        self.assertEqual(self.agent.token_path, "")
        self.assertFalse(os.path.isfile(os.path.join(self.home, "token.txt")))
        self.assertFalse(os.path.isfile(os.path.join(self.home, "paired.ok")))
        # ...et le secret de session est range dans le dossier prive dedie
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
        # Une mise a jour ou un redemarrage du service ne doit pas redemander
        # l'appui sur le bouton.
        self.start_agent()
        premier = self.agent.token
        self.agent.stop()
        time.sleep(0.2)
        self.agent = None
        self.start_agent()
        self.assertEqual(self.agent.token, premier)

    def test_secret_renouvele_apres_perte(self):
        # Redemarrage complet (tmpfs vide) : nouveau secret, donc nouvel appui.
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
    """Appairage : aucun jeton transmissible sans appui physique sur le bouton."""

    def test_commande_pair_supprimee(self):
        self.start_agent()
        with self.assertRaises(WsError) as context:
            self.client().call("pair")
        self.assertIn("bouton", str(context.exception).lower())

    def test_fichier_pair_request_ignore(self):
        # Une demande deposee sur le partage ne doit RIEN donner : c'est le trou
        # par lequel un poste du reseau pouvait recuperer le jeton sans appui.
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
    """Appairage confirme au bouton : demande, accord, jeton."""

    def fake_service(self):
        """Simule un service en cours (le PID courant est bien vivant)."""
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

        # Rien tant que le bouton n'a pas ete tenu.
        premier = client.call("pair.check", request=request_id)
        self.assertFalse(premier["accepted"])
        self.assertTrue(premier["pending"])

        # Le service enregistre l'appui long sur la demande en cours.
        pending = wsagent.pairing.pending(self.home)
        # L'appui commence apres la demande (marge anti-rejeu de 250 ms).
        self.assertTrue(wsagent.pairing.grant(self.home, pending, pending["created"] + 1.0))

        accepte = client.call("pair.check", request=request_id)
        self.assertTrue(accepte["accepted"])
        self.assertEqual(accepte["token"], self.agent.token)
        # L'accord est consomme : un second appel ne redonne pas le jeton.
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
        # L'appui commence apres la demande (marge anti-rejeu de 250 ms).
        self.assertTrue(wsagent.pairing.grant(self.home, pending, pending["created"] + 1.0))
        # Un autre client demande un jeton pour un identifiant qu'il invente.
        data = client.call("pair.check", request="AUTRE123")
        self.assertFalse(data["accepted"])
        self.assertNotIn("token", data)


class InstallerChoiceTest(AgentTestCase):
    """Le bon install.sh est choisi : partage si plus recent, jamais de retour arriere."""

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
    def test_handshake_non_websocket(self):
        self.start_agent()
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        try:
            sock.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
            response = sock.recv(200)
            self.assertIn(b"400", response)
        finally:
            sock.close()

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


class InstallTest(AgentTestCase):
    def setUp(self):
        super().setUp()
        # Le fil d'installation continue apres la reponse : on neutralise le
        # redemarrage de l'agent pour toute la duree des tests.
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
    """Une installation sans changement de version ne doit rien relancer."""

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
        """Prepare le dossier source, le programme installe et l'etat du service."""
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


class ReaderTestCommandTest(AgentTestCase):
    """Le test du lecteur passe par le service (seul proprietaire du bus SPI)."""

    def test_refuse_sans_service(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError) as context:
            client.call("reader.test", seconds=3)
        self.assertIn("service", str(context.exception))

    def test_duree_bornee(self):
        client = self.authenticated_client()
        with self.assertRaises(WsError):
            client.call("reader.test", seconds="beaucoup")
        # duree absurde mais service arrete : le refus vient du service
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


if __name__ == "__main__":
    unittest.main()
