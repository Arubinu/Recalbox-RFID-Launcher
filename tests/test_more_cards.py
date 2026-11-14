"""Special cards: pause, save, sound, time left, collection; player change during a game."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest

import support
from rfid import audio
from rfid.config import Config
from rfid.controller import Controller
from rfid.players import Players
from rfid.playtime import PlayTimer
from rfid.storage import StorageError, TagStore, clean_params
from test_players import IDLE, WEDNESDAY, FakeScreen


class FakeSaver:
    def __init__(self):
        self.state_value = "PLAYING"
        self.toggles = 0
        self.saved = []

    def state(self):
        return self.state_value

    def toggle_pause(self):
        self.toggles += 1
        self.state_value = "PAUSED" if self.state_value == "PLAYING" else "PLAYING"

    def save(self, owner=""):
        self.saved.append(owner)
        return "/saves/x.state"


class CardsTest(unittest.TestCase):
    CONFIG = "[players]\nenabled = 1\n"

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-more-cards-")
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.launcher = support.FakeLauncher()
        self.feedback = support.FakeFeedback()
        self.clock = support.FakeClock()
        self.wall = support.FakeClock(WEDNESDAY)
        self.screen = FakeScreen()
        self.saver = FakeSaver()
        self.config = Config(os.path.join(self.directory, "config.ini"))
        self.playtime = PlayTimer(self.directory, clock=self.clock, wall=self.wall)
        self.players = Players(self.directory, wall=self.wall, clock=self.clock)
        self.store.put("6A0E0001", "snes", "Mario.smc", "Mario")
        self.store.put_entry("1EA00001", {"kind": "action", "action": "player", "name": "Lea",
                                          "params": {"quota_min": 30, "period": "day"}})
        self.store.put_entry("70A00002", {"kind": "action", "action": "player", "name": "Tom",
                                          "params": {"quota_min": 0, "period": "day"}})
        for uid, action in (("0A000001", "pause"), ("0A000002", "save"), ("0A000003", "sound"), ("0A000004", "time")):
            self.store.put_entry(uid, {"kind": "action", "action": action})
        self.controller = self.make(self.CONFIG)

    def make(self, text):
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.config.reload()
        return Controller(self.store, self.launcher, self.feedback, self.config, None,
                          state_provider=lambda: dict(IDLE), clock=self.clock, playtime=self.playtime,
                          screen=self.screen, players=self.players, saver=self.saver)

    def said(self):
        return [key for key, _values in self.screen.said]

    def play_as_lea(self):
        self.controller.on_badge("1EA00001")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "launched")

    def test_pause_arrete_le_temps(self):
        self.play_as_lea()
        self.clock.advance(60)
        self.assertEqual(self.controller.on_badge("0A000001"), "paused")
        left = self.playtime.remaining_s()
        used = self.players.used_s("1EA00001")
        self.clock.advance(600)
        self.assertEqual(self.playtime.remaining_s(), left, "le temps du jeu ne baisse plus")
        self.assertEqual(self.players.used_s("1EA00001"), used, "le temps du joueur n'avance plus")
        self.assertEqual(self.playtime.tick(), "", "pas de fin de temps pendant la pause")
        self.assertEqual(self.controller.on_badge("0A000001"), "resumed")
        self.clock.advance(60)
        self.assertAlmostEqual(self.players.used_s("1EA00001"), used + 60, delta=1)
        self.assertEqual(self.saver.toggles, 2)
        self.assertIn("paused", self.said())
        self.assertIn("resumed", self.said())

    def test_pause_sans_jeu(self):
        self.assertEqual(self.controller.on_badge("0A000001"), "nothing")
        self.launcher.running = True
        self.saver.state_value = ""  # stand-alone emulator: no RetroArch
        self.assertEqual(self.controller.on_badge("0A000001"), "nothing")

    def test_sauvegarde_immediate(self):
        self.play_as_lea()
        self.assertEqual(self.controller.on_badge("0A000002"), "saving")
        for _ in range(100):
            if "saved" in self.said():
                break
            time.sleep(0.01)
        self.assertEqual(self.saver.saved, ["1EA00001"], "la sauvegarde du joueur")
        self.assertIn("saved", self.said())

    def test_son(self):
        states = iter([True, False, None])
        self.controller.mixer = lambda: next(states)
        self.assertEqual(self.controller.on_badge("0A000003"), "muted")
        self.assertEqual(self.controller.on_badge("0A000003"), "unmuted")
        self.assertEqual(self.controller.on_badge("0A000003"), "failed")
        self.assertEqual(self.said(), ["sound_off", "sound_on"])

    def test_temps_restant(self):
        self.controller.on_badge("1EA00001")
        self.assertEqual(self.controller.on_badge("0A000004"), "time")
        key, values = self.screen.said[-1]
        self.assertEqual((key, values["name"], values["t"]), ("time_left", "Lea", "30 min"))
        self.players.pending = None
        self.controller.on_badge("0A000004")
        self.assertEqual(self.screen.said[-1][0], "time_unlimited", "l'invite sans limite")

    def test_changer_de_joueur_en_cours_de_partie(self):
        self.controller = self.make(self.CONFIG + "switch_on_card = 1\n")
        self.play_as_lea()
        self.assertEqual(self.controller.on_badge("70A00002"), "player_switched")
        self.assertEqual(self.players.current["uid"], "70A00002")
        self.assertIsNone(self.playtime.session, "Tom n'a pas de limite")
        self.assertEqual(self.screen.said[-1], ("player_switched", {"name": "Tom"}))

    def test_sans_l_option_la_carte_est_pour_la_partie_suivante(self):
        self.play_as_lea()
        self.assertEqual(self.controller.on_badge("70A00002"), "player")
        self.assertEqual(self.players.current["uid"], "1EA00001")
        self.assertEqual(self.screen.said[-1], ("player_next", {"name": "Tom"}))

    def test_collection(self):
        rom = os.path.join(self.directory, "Zelda.sfc")
        open(rom, "w").close()
        self.store.put_entry("0C000001", {"kind": "action", "action": "random", "params": {"games": [
            {"system": "snes", "path": rom, "name": "Zelda"},
            {"system": "snes", "path": os.path.join(self.directory, "absent.sfc"), "name": "Absent"}]}})
        self.controller = Controller(self.store, self.launcher, self.feedback, self.make("").cfg, None,
                                     state_provider=lambda: dict(IDLE), clock=self.clock, library=object())
        self.assertEqual(self.controller.on_badge("0C000001"), "launched")
        self.assertEqual(self.launcher.calls[-1][0], "snes")
        self.assertTrue(self.launcher.calls[-1][1].endswith("Zelda.sfc"))


class CollectionParamsTest(unittest.TestCase):
    def test_liste_nettoyee(self):
        params = clean_params("random", {"games": [{"system": "snes", "path": "/roms/snes/a.sfc"},
                                                   {"system": "../x", "path": "/roms/b"},
                                                   {"system": "snes", "path": "relatif.sfc"}, "texte"]})
        self.assertEqual(params["games"], [{"system": "snes", "path": "/roms/snes/a.sfc", "name": "a"}])
        self.assertNotIn("games", clean_params("random", {"system": "snes"}), "sans liste : comme avant")
        with self.assertRaises(StorageError):
            clean_params("random", {"system": "a/b"})


class AudioTest(unittest.TestCase):
    def test_bascule(self):
        calls = []

        class Reply:
            def __init__(self, text):
                self.stdout = text

        def run(argv, **kwargs):
            calls.append(argv[1])
            self.assertEqual(kwargs["env"]["XDG_RUNTIME_DIR"], "/run/user/0")
            return Reply("Mute: yes\n")

        self.assertTrue(audio.toggle_mute(run))
        self.assertEqual(calls, ["set-sink-mute", "get-sink-mute"])

        def broken(argv, **kwargs):
            raise OSError("pas de pactl")

        self.assertIsNone(audio.toggle_mute(broken))


if __name__ == "__main__":
    unittest.main()
