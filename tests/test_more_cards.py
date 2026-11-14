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
        self.controller = self.make(self.CONFIG + "switch_on_card = 0\n")
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


class PlayerRulesTest(CardsTest):
    """Time slots, allowed games and reward cards of the player cards."""

    def player(self, uid, **params):
        base = {"quota_min": 30, "period": "day"}
        base.update(params)
        self.store.put_entry(uid, {"kind": "action", "action": "player", "name": "Zoe", "params": base})

    def test_hors_plage_horaire(self):
        hour = time.localtime().tm_hour
        start, end = ("%02d:00" % ((hour + 2) % 24), "%02d:00" % ((hour + 3) % 24))
        if start >= end:
            start, end = "%02d:00" % ((hour + 1) % 24), "%02d:59" % ((hour + 1) % 24)
        self.player("2E000001", **{"from": start, "to": end})
        self.assertEqual(self.controller.on_badge("2E000001"), "player_schedule")
        self.assertEqual(self.screen.said[-1][0], "player_schedule")

    def test_jour_interdit(self):
        today = time.localtime().tm_wday
        self.player("2E000002", days=[(today + 1) % 7])
        self.assertEqual(self.controller.on_badge("2E000002"), "player_schedule")

    def test_plage_limite_la_partie(self):
        self.player("2E000003", **{"from": "00:00", "to": "24:00"})
        self.assertEqual(self.controller.on_badge("2E000003"), "player")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "launched")

    def test_jeux_autorises(self):
        self.player("2E000004", systems=["nes"])
        self.controller.on_badge("2E000004")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "player_not_allowed", "Mario est sur snes")
        self.assertIsNotNone(self.players.pending, "la carte joueur attend encore un jeu autorise")
        self.player("2E000005", systems=["snes"])
        self.controller.on_badge("2E000005")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "launched")

    def test_recompense(self):
        self.store.put_entry("4E000001", {"kind": "action", "action": "reward",
                                          "params": {"player": "1EA00001", "minutes": 20, "uses": 1}})
        before = self.controller.player_left("1EA00001", self.store.get("1EA00001"))
        self.assertEqual(self.controller.on_badge("4E000001"), "reward")
        after = self.controller.player_left("1EA00001", self.store.get("1EA00001"))
        self.assertAlmostEqual(after - before, 20 * 60, delta=1)
        self.assertEqual(self.screen.said[-1], ("reward", {"n": 20, "name": "Lea"}))
        self.assertEqual(self.controller.on_badge("4E000001"), "exhausted", "une fois par periode")
        reloaded = Players(self.directory, wall=self.wall, clock=self.clock)
        self.assertAlmostEqual(reloaded.extra_s("1EA00001"), 20 * 60, delta=1, msg="gardee dans players.json")

    def test_recompense_au_joueur_actif(self):
        self.store.put_entry("4E000002", {"kind": "action", "action": "reward", "params": {"minutes": 10, "uses": 0}})
        self.assertEqual(self.controller.on_badge("4E000002"), "player_needed")
        self.play_as_lea()
        left = self.playtime.remaining_s()
        self.assertEqual(self.controller.on_badge("4E000002"), "reward")
        self.assertAlmostEqual(self.playtime.remaining_s() - left, 600, delta=1, msg="la partie dure plus longtemps")

    def test_toast_temps_bientot_fini(self):
        self.controller.on_badge("1EA00001")
        self.controller.on_badge("6A0E0001")
        self.clock.advance(27 * 60)
        self.controller.stop_game("quit")
        self.assertEqual(self.controller.on_badge("1EA00001"), "player")
        self.assertEqual(self.screen.said[-1][0], "player_low")

    def test_parametres_nettoyes(self):
        params = clean_params("player", {"quota_min": 10, "days": [5, 6, "x", 9], "from": "9:00", "to": "20:30",
                                         "systems": ["snes", "a/b"], "games": [{"system": "nes", "path": "/r/a.nes"}]})
        self.assertEqual((params["days"], params["from"], params["to"], params["systems"]),
                         ([5, 6], "09:00", "20:30", ["snes"]))
        self.assertNotIn("days", clean_params("player", {"days": list(range(7))}), "tous les jours = pas de limite")
        with self.assertRaises(StorageError):
            clean_params("player", {"from": "20:00", "to": "08:00"})
        self.assertEqual(clean_params("reward", {"player": "1ea00001", "minutes": "30"})["player"], "1EA00001")


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
