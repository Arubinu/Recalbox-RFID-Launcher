"""Card frames made by the user (pictures with a transparent window)."""

from __future__ import annotations

import base64
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401 - sets sys.path
from rfid import frames
from rfid.frames import FrameError, FrameStore

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 856 540"></svg>'
META = {"name": "Mega Drive noire", "systems": ["megadrive", "MegaDrive", "../x", "sega32x"],
        "orientation": "landscape", "window": {"x": 44, "y": 2.4, "w": 39.3, "h": 42.6}}


class FrameStoreTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-frames-")
        self.store = FrameStore(self.home, now=lambda: 1700000000)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_ajout_et_liste(self):
        frame = self.store.save(META, PNG)
        self.assertEqual(frame["systems"], ["megadrive", "sega32x"], "consoles nettoyees")
        self.assertEqual(frame["type"], "image/png")
        listed = self.store.list()
        self.assertEqual([item["id"] for item in listed], [frame["id"]])
        self.assertEqual(self.store.get(frame["id"]), ("image/png", PNG))
        self.assertTrue(os.path.isfile(os.path.join(self.home, "frames", frame["id"] + ".png")))

    def test_svg(self):
        frame = self.store.save(dict(META, name="Vectoriel"), SVG)
        self.assertEqual(frame["type"], "image/svg+xml")
        self.assertTrue(frame["id"] and frame["ext"] == ".svg")

    def test_refus(self):
        cases = {
            "format": (META, b"MZ\x90\x00 pas une image"),
            "vide": (META, b""),
            "sans nom": (dict(META, name="  "), PNG),
            "sans zone": (dict(META, window=None), PNG),
            "zone hors carte": (dict(META, window={"x": 200, "y": 0, "w": 10, "h": 10}), PNG),
            "zone non numerique": (dict(META, window={"x": "a", "y": 0, "w": 10, "h": 10}), PNG),
        }
        for label, (meta, data) in cases.items():
            with self.subTest(label):
                with self.assertRaises(FrameError):
                    self.store.save(meta, data)
        self.assertEqual(self.store.list(), [])

    def test_trop_volumineux(self):
        with self.assertRaises(FrameError):
            self.store.save(META, PNG + b"0" * frames.MAX_FRAME_BYTES)

    def test_modification_et_suppression(self):
        frame = self.store.save(META, PNG)
        updated = self.store.update(frame["id"], {"name": "Autre nom", "systems": ["genesis"]})
        self.assertEqual((updated["name"], updated["systems"]), ("Autre nom", ["genesis"]))
        self.assertEqual(updated["window"], frame["window"], "la zone ne change pas")
        self.assertTrue(self.store.delete(frame["id"]))
        self.assertEqual(self.store.list(), [])
        self.assertFalse(self.store.delete(frame["id"]))

    def test_identifiant_force(self):
        for bad in ("../../etc/passwd", "", "ABC", "a" * 40):
            with self.subTest(bad):
                with self.assertRaises(FrameError):
                    self.store.update(bad, {"name": "x"})
                self.assertIsNone(self.store.get(bad))
                self.assertFalse(self.store.delete(bad))


class AgentFramesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfid-frames-agent-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_commandes(self):
        from rfid import wsagent
        from rfid.config import Config
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        agent = wsagent.Agent(Config(os.path.join(home, "config.ini")), None, home=home, port=0)

        class Client:
            upload = None
        client = Client()
        with self.assertRaises(RuntimeError):
            agent._cmd_frames_save(client, {"meta": META})
        client.upload = bytearray(PNG)
        frame = agent._cmd_frames_save(client, {"meta": META})["frame"]
        self.assertIsNone(client.upload)
        self.assertEqual(len(agent._cmd_frames_list(client, {})["frames"]), 1)
        got = agent._cmd_frames_get(client, {"frame": frame["id"]})
        self.assertEqual(base64.b64decode(got["data"]), PNG)
        renamed = agent._cmd_frames_update(client, {"frame": frame["id"], "name": "Neuf"})["frame"]
        self.assertEqual(renamed["name"], "Neuf")
        with self.assertRaises(ValueError):
            agent._cmd_frames_update(client, {"frame": "../x", "name": "Neuf"})
        self.assertTrue(agent._cmd_frames_delete(client, {"frame": frame["id"]})["deleted"])


if __name__ == "__main__":
    unittest.main()
