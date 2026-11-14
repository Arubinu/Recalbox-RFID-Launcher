"""Player avatars (page -> Recalbox -> reader screen) and the player shown on the screen."""

from __future__ import annotations

import base64
import io
import os
import shutil
import tempfile
import unittest
import zipfile

import support  # noqa: F401  (adds app/ to sys.path)
from rfid import avatars, backup, screen
from rfid.storage import StorageError, TagStore
from test_wsagent import AgentTestCase, WsError

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class AvatarFilesTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-avatars-")
        self.addCleanup(shutil.rmtree, self.home, True)

    def test_aller_retour(self):
        avatars.save(self.home, "a1:b2:c3:d4", JPEG)
        self.assertEqual(avatars.load(self.home, "A1B2C3D4"), JPEG)
        self.assertIn("A1B2C3D4", avatars.versions(self.home))
        self.assertTrue(avatars.delete(self.home, "A1B2C3D4"))
        self.assertIsNone(avatars.load(self.home, "A1B2C3D4"))
        self.assertFalse(avatars.delete(self.home, "A1B2C3D4"))

    def test_refus(self):
        with self.assertRaises(avatars.AvatarError):
            avatars.save(self.home, "A1B2C3D4", b"\x89PNG....")
        with self.assertRaises(avatars.AvatarError):
            avatars.save(self.home, "A1B2C3D4", JPEG + b"\x00" * avatars.MAX_BYTES)
        with self.assertRaises(StorageError):
            avatars.save(self.home, "../../etc", JPEG)

    def test_dans_la_sauvegarde(self):
        avatars.save(self.home, "A1B2C3D4", JPEG)
        data = backup.create(self.home)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIn("avatars/A1B2C3D4.jpg", archive.namelist())
        avatars.delete(self.home, "A1B2C3D4")
        backup.restore(self.home, data)
        self.assertEqual(avatars.load(self.home, "A1B2C3D4"), JPEG)


class AvatarCommandsTest(AgentTestCase):
    def setUp(self):
        super().setUp()
        store = TagStore(os.path.join(self.home, "tags.json"))
        store.put_entry("A1B2C3D4", {"kind": "action", "action": "player", "name": "Lea",
                                     "params": {"quota_min": 60, "period": "day"}})
        store.put("B1B2C3D4", "snes", "jeu.smc", "Jeu")

    def test_cycle(self):
        client = self.authenticated_client()
        data = base64.b64encode(JPEG).decode("ascii")
        self.assertFalse(client.call("players.avatar_get", uid="A1B2C3D4")["found"])
        client.call("players.avatar_set", uid="A1B2C3D4", data=data)
        self.assertEqual(client.call("players.avatar_get", uid="A1B2C3D4")["data"], data)
        self.assertTrue(client.call("players.avatar_delete", uid="A1B2C3D4")["deleted"])
        self.assertFalse(client.call("players.avatar_get", uid="A1B2C3D4")["found"])

    def test_refus(self):
        client = self.authenticated_client()
        data = base64.b64encode(JPEG).decode("ascii")
        with self.assertRaises(WsError):
            client.call("players.avatar_set", uid="B1B2C3D4", data=data)  # a game card
        with self.assertRaises(WsError):
            client.call("players.avatar_set", uid="A1B2C3D4", data="pas du base64 !")

    def test_retire_avec_la_carte(self):
        client = self.authenticated_client()
        client.call("players.avatar_set", uid="A1B2C3D4", data=base64.b64encode(JPEG).decode("ascii"))
        client.call("tags.remove", uid="A1B2C3D4")
        self.assertIsNone(avatars.load(self.home, "A1B2C3D4"))


class PlayerShownTest(unittest.TestCase):
    ROW = {"uid": "A1B2C3D4", "name": "Lea", "period": "day", "quota_min": 60, "used_s": 2100,
           "remaining_s": 1500, "avatar": 7}

    def test_joueur_en_cours_avec_limite(self):
        info = screen.player_info({"current": {"uid": "A1B2C3D4", "name": "Lea"}, "players": [self.ROW]}, "fr")
        self.assertEqual((info["name"], info["detail"], info["avatar"]), ("Lea", "25 min restantes", 7))
        self.assertAlmostEqual(info["ratio"], 1500 / 3600.0)

    def test_carte_posee_montre_le_temps(self):
        """Between two games (reader screen), the waiting player's time is shown."""
        info = screen.player_info({"pending": "Lea", "pending_uid": "A1B2C3D4", "players": [self.ROW]}, "fr")
        self.assertEqual(info["detail"], "25 min restantes")
        self.assertEqual(info["uid"], "A1B2C3D4")

    def test_sans_limite_le_temps_joue(self):
        row = dict(self.ROW, quota_min=0, remaining_s=None, period="week")
        info = screen.player_info({"pending": "Lea", "pending_uid": "A1B2C3D4", "players": [row]}, "fr")
        self.assertEqual(info["detail"], "35 min jouées cette semaine")
        self.assertIsNone(info["ratio"])
        row["used_s"] = 0
        info = screen.player_info({"pending": "Lea", "pending_uid": "A1B2C3D4", "players": [row]}, "fr")
        self.assertEqual(info["detail"], "prochaine partie")

    def test_invite_limite(self):
        info = screen.player_info({"guest": {"quota_min": 30, "remaining_s": 600}, "players": []}, "fr")
        self.assertEqual((info["name"], info["detail"]), ("Invité", "10 min restantes"))
        self.assertIsNone(screen.player_info({"players": []}, "fr"))


if __name__ == "__main__":
    unittest.main()
