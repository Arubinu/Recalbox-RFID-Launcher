"""Save before quitting, resume at the next launch (RetroArch network commands)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support
from rfid.config import Config
from rfid.controller import Controller
from rfid.savegame import GameSaver, parse_status
from rfid.storage import TagStore


class FakeRetroArch:
    """Answers like RetroArch 1.22 and writes the save state in the current slot."""

    def __init__(self, folder, name="Tuff", slot="", running=True):
        self.folder = folder
        self.name = name
        self.slot = slot
        self.running = running
        self.sent = []
        self.writes = True

    def __call__(self, command, wait):
        self.sent.append(command)
        if not self.running:
            return None
        if command == "GET_STATUS":
            return "GET_STATUS PLAYING Gambatte,%s,crc32=e9140a3b\n" % self.name
        if command == "SAVE_STATE" and self.writes:
            base = os.path.join(self.folder, self.name + ".state" + self.slot)
            with open(base, "wb") as handle:
                handle.write(b"NEW")
            with open(base + ".png", "wb") as handle:
                handle.write(b"NEWPNG")
        if command == "SAVE_FILES":
            return "OK\n"
        return None


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class GameSaverTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-save-")
        self.saves = os.path.join(self.home, "saves", "gb")
        os.makedirs(self.saves)
        self.cfg = os.path.join(self.home, "retroarchcustom.cfg")
        self.write_cfg()
        self.clock = Clock()
        self.retroarch = FakeRetroArch(self.saves)
        self.shown = []
        self.saver = GameSaver(query=self.retroarch, cfg_path=self.cfg, sleep=self.clock.sleep,
                               clock=self.clock, show=self.shown.append)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def write_cfg(self, auto_load="false"):
        with open(self.cfg, "w", encoding="utf-8") as handle:
            handle.write('savestate_directory = "%s"\nsavestate_auto_load = %s\n' % (self.saves, auto_load))

    def path(self, name):
        return os.path.join(self.saves, name)

    def put(self, name, data):
        with open(self.path(name), "wb") as handle:
            handle.write(data)

    def read(self, name):
        with open(self.path(name), "rb") as handle:
            return handle.read()

    def test_lecture_du_statut(self):
        self.assertEqual(parse_status("GET_STATUS PLAYING Gambatte,Tuff,crc32=e9140a3b\n"),
                         {"core": "Gambatte", "name": "Tuff"})
        self.assertEqual(parse_status("GET_STATUS PLAYING Genesis Plus GX,Sonic, The Hedgehog (USA),crc32=1"),
                         {"core": "Genesis Plus GX", "name": "Sonic, The Hedgehog (USA)"})
        self.assertIsNone(parse_status("GET_STATUS CONTENTLESS"))
        self.assertIsNone(parse_status(None))

    def test_sauvegarde_sans_toucher_l_emplacement_du_joueur(self):
        self.put("Tuff.state", b"MINE")
        self.put("Tuff.state.png", b"MINEPNG")
        auto = self.saver.save()
        self.assertEqual(auto, self.path("Tuff.state.auto"))
        self.assertEqual(self.read("Tuff.state.auto"), b"NEW")
        self.assertEqual(self.read("Tuff.state"), b"MINE", "la sauvegarde du joueur est remise")
        self.assertEqual(self.read("Tuff.state.png"), b"MINEPNG")
        self.assertEqual(self.retroarch.sent[:3], ["GET_STATUS", "SAVE_FILES", "SAVE_STATE"])

    def test_emplacement_vide_reste_vide(self):
        self.retroarch.slot = "3"
        self.saver.save()
        self.assertEqual(self.read("Tuff.state.auto"), b"NEW")
        self.assertEqual(sorted(os.listdir(self.saves)), ["Tuff.state.auto"])

    def test_sauvegarde_auto_precedente_remplacee(self):
        self.put("Tuff.state.auto", b"OLD")
        self.saver.save()
        self.assertEqual(self.read("Tuff.state.auto"), b"NEW")

    def test_emulateur_hors_retroarch(self):
        self.retroarch.running = False
        self.assertEqual(self.saver.save(), "")
        self.assertEqual(self.retroarch.sent, ["GET_STATUS"])

    def test_rien_ecrit(self):
        self.retroarch.writes = False
        self.put("Tuff.state", b"MINE")
        self.assertEqual(self.saver.save(), "")
        self.assertFalse(os.path.exists(self.path("Tuff.state.auto")))
        self.assertEqual(self.read("Tuff.state"), b"MINE")
        self.assertLess(self.clock.now, 1000.0 + 10, "attente bornee")

    def test_reprise(self):
        self.put("Tuff.state.auto", b"NEW")
        self.assertTrue(self.saver.resume("Tuff"))
        self.assertIn("LOAD_STATE_SLOT -1", self.retroarch.sent)
        self.assertEqual(self.shown, ["game_resumed"])

    def test_pas_de_reprise_sans_sauvegarde(self):
        self.assertFalse(self.saver.resume("Tuff"))
        self.assertNotIn("LOAD_STATE_SLOT -1", self.retroarch.sent)

    def test_pas_de_reprise_si_recalbox_la_fait(self):
        self.put("Tuff.state.auto", b"NEW")
        self.write_cfg(auto_load="true")
        self.assertFalse(self.saver.resume("Tuff"))
        self.assertNotIn("LOAD_STATE_SLOT -1", self.retroarch.sent)

    def test_autre_jeu_pas_repris(self):
        self.put("Tuff.state.auto", b"NEW")
        self.assertFalse(self.saver.resume("Retroid", timeout_s=5))
        self.assertNotIn("LOAD_STATE_SLOT -1", self.retroarch.sent)


class FakeSaver:
    def __init__(self):
        self.saved = 0

    def save(self):
        self.saved += 1
        return "x"


class ControllerSaveTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-ctrl-save-")
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.config = Config(os.path.join(self.directory, "config.ini"))
        self.saver = FakeSaver()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def controller(self):
        return Controller(self.store, support.FakeLauncher(), support.FakeFeedback(), self.config, None,
                          state_provider=dict, clock=support.FakeClock(), saver=self.saver)

    def test_option_desactivee_par_defaut(self):
        self.controller().stop_game()
        self.assertEqual(self.saver.saved, 0)

    def test_sauvegarde_avant_de_quitter(self):
        with open(os.path.join(self.directory, "config.ini"), "w", encoding="utf-8") as handle:
            handle.write("[launch]\nsave_on_quit = 1\n")
        self.config.reload()
        controller = self.controller()
        controller.stop_game("removed")
        controller.stop_game("time")
        self.assertEqual(self.saver.saved, 2)
        controller.stop_game("refused")
        self.assertEqual(self.saver.saved, 2, "un jeu refuse n'est jamais sauvegarde")


if __name__ == "__main__":
    unittest.main()
