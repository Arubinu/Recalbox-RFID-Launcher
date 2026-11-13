"""Page password, screensaver memory of the selected game, phone page switch."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock

import support  # noqa: F401
from rfid import access, esbridge, wsagent
from rfid.config import Config
from test_wsagent import AgentTestCase, WsError

PLAYING_PAGE = {"Action": "gamelistbrowsing", "SystemId": "snes", "Game": "Mario",
                "GamePath": "/recalbox/share/roms/snes/Mario.smc", "State": "selected"}
SLEEPING = {"Action": "sleep", "System": "", "SystemId": "", "Game": "", "GamePath": "", "State": "selected"}


class ScreensaverTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-last-")
        self.addCleanup(shutil.rmtree, self.directory, True)
        patch = mock.patch.dict(os.environ, {"RFID_LAST_TARGET": os.path.join(self.directory, "last.json")})
        patch.start()
        self.addCleanup(patch.stop)

    def test_jeu_retenu_pendant_l_ecran_de_veille(self):
        target, remembered = esbridge.selected_target(PLAYING_PAGE)
        self.assertEqual((target.game, remembered), ("Mario.smc", False))
        target, remembered = esbridge.selected_target(SLEEPING)
        self.assertEqual((target.game, remembered), ("Mario.smc", True))

    def test_pas_de_jeu_hors_ecran_de_veille(self):
        esbridge.selected_target(PLAYING_PAGE)
        folder = dict(PLAYING_PAGE, IsFolder="1")
        self.assertEqual(esbridge.selected_target(folder), (None, False))

    def test_rien_de_retenu(self):
        self.assertEqual(esbridge.selected_target(SLEEPING), (None, False))


class PasswordStoreTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-access-")
        self.addCleanup(shutil.rmtree, self.home, True)

    def test_cycle(self):
        self.assertFalse(access.has_password(self.home))
        self.assertTrue(access.check(self.home, "anything"))
        access.set_password(self.home, "chocolat")
        self.assertTrue(access.has_password(self.home))
        self.assertTrue(access.check(self.home, "chocolat"))
        self.assertFalse(access.check(self.home, "Chocolat"))
        with open(os.path.join(self.home, access.ACCESS_FILENAME), encoding="utf-8") as handle:
            self.assertNotIn("chocolat", handle.read(), "jamais en clair")
        access.clear_password(self.home)
        self.assertFalse(access.has_password(self.home))

    def test_trop_court(self):
        with self.assertRaises(access.AccessError):
            access.set_password(self.home, "abc")


class PasswordPairingTest(AgentTestCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(wsagent, "process_alive", return_value=True)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(wsagent.Agent, "PASSWORD_DELAY_S", 0.0)
        patch.start()
        self.addCleanup(patch.stop)

    def press(self, client):
        request = client.call("pair.request")["request"]
        pending = wsagent.pairing.pending(self.home)
        wsagent.pairing.grant(self.home, pending, pending["created"] + 1.0)
        return request, client.call("pair.check", request=request)

    def test_bouton_puis_mot_de_passe(self):
        access.set_password(self.home, "chocolat")
        self.start_agent()
        client = self.client()
        request, check = self.press(client)
        self.assertEqual(check, {"accepted": True, "password": True}, "pas de jeton sans mot de passe")
        with self.assertRaises(WsError) as context:
            client.call("pair.password", request=request, password="vanille")
        self.assertIn("encore 4 essais", str(context.exception))
        token = client.call("pair.password", request=request, password="chocolat")["token"]
        self.assertEqual(token, self.agent.token)
        with self.assertRaises(WsError):
            client.call("pair.password", request=request, password="chocolat")   # single use

    def test_trop_d_essais(self):
        access.set_password(self.home, "chocolat")
        self.start_agent()
        client = self.client()
        request, _check = self.press(client)
        for _ in range(4):
            with self.assertRaises(WsError):
                client.call("pair.password", request=request, password="x")
        with self.assertRaises(WsError) as context:
            client.call("pair.password", request=request, password="x")
        self.assertIn("trop d'essais", str(context.exception))
        with self.assertRaises(WsError):
            client.call("pair.password", request=request, password="chocolat")

    def test_sans_mot_de_passe_le_bouton_suffit(self):
        self.start_agent()
        _request, check = self.press(self.client())
        self.assertTrue(check["token"])

    def test_definir_deconnecte_les_autres(self):
        me = self.authenticated_client()
        other = self.client()
        other.call("auth", token=self.agent.token)
        old = self.agent.token
        data = me.call("access.set", password="chocolat")
        self.assertNotEqual(data["token"], old)
        self.assertTrue(me.call("access.status")["password"], "celui qui definit reste connecte")
        with self.assertRaises(WsError):
            other.call("status")
        with self.assertRaises(WsError):
            me.call("access.set", password="nouveau1", current="faux")
        with self.assertRaises(WsError):
            me.call("access.clear", current="faux")
        me.call("access.clear", current="chocolat")
        self.assertFalse(me.call("access.status")["password"])


class WebSwitchTest(AgentTestCase):
    def test_page_desactivee(self):
        Config(self.config_path).create_default()
        Config(self.config_path).write_values({"agent.web": "0"})
        self.start_agent()
        os.makedirs(os.path.join(self.home, "web"), exist_ok=True)
        with open(os.path.join(self.home, "web", "index.html"), "w", encoding="utf-8") as handle:
            handle.write("<html><head></head></html>")
        import socket

        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        try:
            sock.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n")
            self.assertIn(b"404", sock.recv(100))
        finally:
            sock.close()
        self.assertFalse(self.agent.web_enabled())


if __name__ == "__main__":
    unittest.main()
