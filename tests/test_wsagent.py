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

    def authenticated_client(self):
        self.start_agent()
        client = self.client()
        client.call("auth", token=self.agent.token)
        return client


class TokenTest(AgentTestCase):
    def test_creation_et_stabilite(self):
        path = os.path.join(self.home, "token.txt")
        first = wsagent.ensure_token(path)
        self.assertGreaterEqual(len(first), 8)
        self.assertEqual(wsagent.ensure_token(path), first)
        with open(path, "r", encoding="ascii") as handle:
            self.assertEqual(handle.read().strip(), first)

    def test_jeton_absent_recree(self):
        path = os.path.join(self.home, "token.txt")
        with open(path, "w", encoding="ascii") as handle:
            handle.write("")
        self.assertTrue(wsagent.ensure_token(path))


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
        self.assertEqual(data["agent"]["token"], self.agent.token)
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
