"""Portable cards: the game written in the badge memory."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support
from fake_rc522 import FakeRc522Spi
from rfid import portable
from rfid.config import Config
from rfid.controller import Controller
from rfid.drivers.rc522 import Rc522, Rc522Error
from rfid.storage import TagStore

CLASSIC_UID = bytes.fromhex("A1B2C3D4")
NTAG_UID = bytes.fromhex("04112233445566")


def chip(spi):
    reader = Rc522(spi)
    reader.begin()
    return reader


class FormatTest(unittest.TestCase):
    def test_aller_retour(self):
        data = portable.encode("snes", "/recalbox/share/roms/snes/Jeux/Super Mario World.smc")
        self.assertEqual(data, "RL1|snes|Jeux/Super Mario World.smc".encode("utf-8") + b"\x00")
        self.assertEqual(portable.decode(data + b"\x00" * 30), ("snes", "Jeux/Super Mario World.smc"))

    def test_refus(self):
        with self.assertRaises(portable.PortableError):
            portable.encode("snes", "/recalbox/share/roms/snes/" + "x" * 120 + ".smc")
        with self.assertRaises(portable.PortableError):
            portable.encode("snes", "/recalbox/share/roms/snes/a|b.smc")
        self.assertIsNone(portable.decode(b"\xff\xfe\x00"))
        self.assertIsNone(portable.decode(b"RL1|../etc|passwd\x00"))
        self.assertIsNone(portable.decode(b"RL1|snes|../../etc/passwd\x00"))
        self.assertIsNone(portable.decode(b"NDEF\x00"))

    def test_jeu_present_ou_absent(self):
        directory = tempfile.mkdtemp(prefix="rfid-roms-")
        self.addCleanup(shutil.rmtree, directory, True)
        os.makedirs(os.path.join(directory, "snes"))
        open(os.path.join(directory, "snes", "Mario.smc"), "wb").close()
        entry = portable.entry_from(b"RL1|snes|Mario.smc\x00", roms_dirs=(directory,))
        self.assertFalse(entry["missing"])
        self.assertEqual(entry["name"], "Mario")
        self.assertTrue(entry["path"].endswith("snes/Mario.smc"))
        self.assertTrue(portable.entry_from(b"RL1|snes|Zelda.smc\x00", roms_dirs=(directory,))["missing"])


class DriverMemoryTest(unittest.TestCase):
    def test_mifare_classic(self):
        spi = FakeRc522Spi(CLASSIC_UID, card="classic")
        reader = chip(spi)
        payload = portable.encode("megadrive", "/recalbox/share/roms/megadrive/Sonic The Hedgehog (Europe).md")
        reader.write_memory(payload, CLASSIC_UID)
        self.assertTrue(spi.read_text().startswith(payload))
        self.assertTrue(reader.read_memory().startswith(payload))
        self.assertEqual(spi.status2 & 0x08, 0, "Crypto1 coupe apres l'operation")

    def test_ultralight(self):
        spi = FakeRc522Spi(NTAG_UID, card="ultralight", pages=45)
        reader = chip(spi)
        payload = portable.encode("nes", "/recalbox/share/roms/nes/Zelda.nes")
        reader.write_memory(payload, NTAG_UID)
        self.assertEqual(portable.decode(reader.read_memory()), ("nes", "Zelda.nes"))

    def test_ultralight_trop_petit(self):
        spi = FakeRc522Spi(NTAG_UID, card="ultralight", pages=16)
        reader = chip(spi)
        with self.assertRaises(Rc522Error) as context:
            reader.write_memory(b"x" * 60 + b"\x00", NTAG_UID)
        self.assertIn("trop petit", str(context.exception))

    def test_cle_inconnue(self):
        spi = FakeRc522Spi(CLASSIC_UID, card="classic", key=bytes.fromhex("112233445566"))
        reader = chip(spi)
        with self.assertRaises(Rc522Error) as context:
            reader.write_memory(b"RL1|nes|a.nes\x00", CLASSIC_UID)
        self.assertIn("protege", str(context.exception))

    def test_cle_d_usine_alternative(self):
        spi = FakeRc522Spi(CLASSIC_UID, card="classic", key=bytes.fromhex("A0A1A2A3A4A5"))
        reader = chip(spi)
        reader.write_memory(b"RL1|nes|a.nes\x00", CLASSIC_UID)
        self.assertEqual(portable.decode(reader.read_memory()), ("nes", "a.nes"))

    def test_mauvais_badge(self):
        reader = chip(FakeRc522Spi(CLASSIC_UID))
        with self.assertRaises(Rc522Error) as context:
            reader.write_memory(b"RL1|nes|a.nes\x00", bytes.fromhex("01020304"))
        self.assertIn("pas le bon badge", str(context.exception))

    def test_pas_de_badge(self):
        reader = chip(FakeRc522Spi(None))
        self.assertIsNone(reader.read_memory())
        with self.assertRaises(Rc522Error):
            reader.write_memory(b"RL1|nes|a.nes\x00")

    def test_badge_vierge(self):
        reader = chip(FakeRc522Spi(CLASSIC_UID))
        self.assertIsNone(portable.decode(reader.read_memory()))

    def test_lecture_uid_inchangee(self):
        spi = FakeRc522Spi(CLASSIC_UID)
        reader = chip(spi)
        reader.write_memory(b"RL1|nes|a.nes\x00")
        self.assertEqual(reader.read_uid(), CLASSIC_UID)


class ControllerPortableTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-portable-")
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.launcher = support.FakeLauncher()
        self.feedback = support.FakeFeedback()
        self.memory = None
        self.roms = os.path.join(self.directory, "roms")
        os.makedirs(os.path.join(self.roms, "snes"))
        open(os.path.join(self.roms, "snes", "Mario.smc"), "wb").close()
        self.controller = Controller(self.store, self.launcher, self.feedback,
                                     Config(os.path.join(self.directory, "config.ini")), None,
                                     state_provider=lambda: {}, clock=support.FakeClock(),
                                     card_reader=lambda: self.memory)

    def entry_patch(self):
        from unittest import mock

        original = portable.entry_from
        return mock.patch.object(portable, "entry_from",
                                 lambda data: original(data, roms_dirs=(self.roms,)))

    def test_badge_inconnu_mais_jeu_ecrit(self):
        self.memory = b"RL1|snes|Mario.smc\x00"
        with self.entry_patch():
            self.assertEqual(self.controller.on_badge("DEADBEEF"), "launched")
        self.assertTrue(self.launcher.calls[0][1].endswith("snes/Mario.smc"))
        self.assertEqual(self.store.count(), 0, "rien n'est ajoute a la liste")

    def test_jeu_absent_de_cette_recalbox(self):
        self.memory = b"RL1|snes|Zelda.smc\x00"
        with self.entry_patch():
            self.assertEqual(self.controller.on_badge("DEADBEEF"), "missing")
        self.assertEqual(self.launcher.calls, [])
        self.assertIn("error", self.feedback.events)

    def test_badge_vierge_reste_inconnu(self):
        self.memory = bytes(48)
        self.assertEqual(self.controller.on_badge("DEADBEEF"), "unknown")

    def test_la_liste_passe_avant_le_badge(self):
        self.store.put("DEADBEEF", "snes", "Other.smc", "Other", "/x/Other.smc")
        self.memory = b"RL1|snes|Mario.smc\x00"
        self.controller.on_badge("DEADBEEF")
        self.assertEqual(self.launcher.calls, [("snes", "/x/Other.smc")])


if __name__ == "__main__":
    unittest.main()
