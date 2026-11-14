"""Full backup and restore of the reader data."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile

import support  # noqa: F401 - sets sys.path
from rfid import backup


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


MANIFEST = json.dumps({"format": 1, "files": []})


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-backup-")
        write(os.path.join(self.home, "tags.json"), '{"tags": {"A1B2C3D4": {"system": "snes"}}}')
        write(os.path.join(self.home, "config.ini"), "[button]\npin = 17\n")
        write(os.path.join(self.home, "card-templates.json"), '{"templates": []}')
        write(os.path.join(self.home, "access.json"), '{"hash": "secret"}')
        write(os.path.join(self.home, "frames", "megadrive.png"), "png")
        write(os.path.join(self.home, "frames", "megadrive.json"), '{"system": "megadrive"}')
        write(os.path.join(self.home, "logs", "rfid.log"), "journal")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_contenu(self):
        data = backup.create(self.home, now=lambda: 1700000000)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read(backup.MANIFEST))
        self.assertEqual(names, {"tags.json", "config.ini", "card-templates.json",
                                 "frames/megadrive.png", "frames/megadrive.json", backup.MANIFEST})
        self.assertNotIn("access.json", names, "le mot de passe ne doit jamais sortir")
        self.assertEqual(manifest["format"], backup.FORMAT)

    def test_statistiques_lisibles(self):
        from rfid.storage import TagStore

        os.remove(os.path.join(self.home, "tags.json"))
        store = TagStore(os.path.join(self.home, "tags.json"))
        store.load()
        store.put_entry("1EA00001", {"kind": "action", "action": "player", "name": "Léa",
                                     "params": {"quota_min": 0, "period": "day"}})
        write(os.path.join(self.home, "players.json"), json.dumps({"usage": {}, "games": {
            "1EA00001": {"2026-11-14": {"gb|Retroid": 66}},
            "guest": {"2026-11-13": {"gb|Jeu; spécial": 30}}}}))
        data = backup.create(self.home)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            text = archive.read(backup.STATS_CSV).decode("utf-8-sig")
        self.assertEqual(text.splitlines(), [
            "date;player;console;game;minutes;seconds",
            "2026-11-14;Léa;gb;Retroid;1,1;66",
            '2026-11-13;guest;gb;"Jeu; spécial";0,5;30',
        ])
        self.assertNotIn(backup.STATS_CSV, backup.read(data), "jamais restaure : les donnees sont dans players.json")
        self.assertIn("players.json", backup.read(data))

    def test_pas_de_statistiques_sans_partie(self):
        with zipfile.ZipFile(io.BytesIO(backup.create(self.home))) as archive:
            self.assertNotIn(backup.STATS_CSV, archive.namelist())

    def test_aller_retour(self):
        data = backup.create(self.home)
        write(os.path.join(self.home, "tags.json"), '{"tags": {}}')
        write(os.path.join(self.home, "frames", "nes.png"), "autre")
        result = backup.restore(self.home, data)
        self.assertIn("A1B2C3D4", read_text(os.path.join(self.home, "tags.json")))
        # The frames folder of the backup replaces the current one.
        self.assertFalse(os.path.exists(os.path.join(self.home, "frames", "nes.png")))
        self.assertTrue(os.path.exists(os.path.join(self.home, "frames", "megadrive.png")))
        # The password is not touched; a copy of the replaced files is kept.
        self.assertIn("secret", read_text(os.path.join(self.home, "access.json")))
        copy = os.path.join(self.home, result["copy"])
        self.assertEqual(read_text(os.path.join(copy, "tags.json")), '{"tags": {}}')

    def test_copies_limitees(self):
        data = backup.create(self.home)
        for index in range(backup.KEEP_BACKUPS + 3):
            backup.restore(self.home, data, now=lambda i=index: 1700000000 + i)
        copies = os.listdir(os.path.join(self.home, backup.BACKUPS_DIR))
        self.assertEqual(len(copies), backup.KEEP_BACKUPS)

    def test_refus(self):
        cases = {
            "pas un zip": b"bonjour",
            "sans manifeste": make_zip({"tags.json": "{}"}),
            "nom inconnu": make_zip({backup.MANIFEST: MANIFEST, "access.json": "{}"}),
            "chemin": make_zip({backup.MANIFEST: MANIFEST, "frames/../../etc/passwd": "x"}),
            "extension": make_zip({backup.MANIFEST: MANIFEST, "frames/script.sh": "x"}),
            "json casse": make_zip({backup.MANIFEST: MANIFEST, "tags.json": "{pas du json"}),
            "ini casse": make_zip({backup.MANIFEST: MANIFEST, "config.ini": "pas de section"}),
            "plus recente": make_zip({backup.MANIFEST: json.dumps({"format": 99}), "tags.json": "{}"}),
            "vide": make_zip({backup.MANIFEST: MANIFEST}),
        }
        before = read_text(os.path.join(self.home, "tags.json"))
        for label, data in cases.items():
            with self.subTest(label):
                with self.assertRaises(backup.BackupError):
                    backup.restore(self.home, data)
        self.assertEqual(read_text(os.path.join(self.home, "tags.json")), before)
        self.assertFalse(os.path.exists(os.path.join(self.home, backup.BACKUPS_DIR)),
                         "une sauvegarde refusee ne doit rien toucher")


class AgentBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfid-backup-agent-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_commandes(self):
        import base64
        from unittest import mock
        from rfid import wsagent
        from rfid.config import Config
        home = os.path.join(self.tmp, "home")
        write(os.path.join(home, "tags.json"), '{"tags": {}}')
        agent = wsagent.Agent(Config(os.path.join(home, "config.ini")), None, home=home, port=0)
        exported = agent._cmd_backup_export(None, {})
        self.assertTrue(exported["name"].endswith(".zip"))
        data = base64.b64decode(exported["data"])

        class Client:
            upload = None
        client = Client()
        with self.assertRaises(RuntimeError):
            agent._cmd_backup_restore(client, {})
        client.upload = bytearray(b"pas une sauvegarde")
        with self.assertRaises(ValueError):
            agent._cmd_backup_restore(client, {})
        client.upload = bytearray(data)
        with mock.patch.object(agent, "_restart_service") as restart:
            result = agent._cmd_backup_restore(client, {})
            for _ in range(50):
                if restart.called:
                    break
                import time
                time.sleep(0.02)
        self.assertIn("tags.json", result["files"])
        self.assertTrue(restart.called, "le service doit relire ses fichiers")


if __name__ == "__main__":
    unittest.main()
