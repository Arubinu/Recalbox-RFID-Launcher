"""Player cards: time counted per person, one card per game."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import tempfile
import time
import unittest

import support
from rfid import players as players_module
from rfid.config import Config
from rfid.controller import Controller
from rfid.players import GUEST, Players, period_days
from rfid.playtime import PlayTimer
from rfid.storage import StorageError, TagStore

IDLE = {"State": "selected"}
#: A Wednesday at noon (local time), so that "week" covers three days.
WEDNESDAY = time.mktime((2026, 11, 11, 12, 0, 0, 0, 0, -1))


class FakeScreen:
    def __init__(self):
        self.said = []

    def say(self, key, **values):
        self.said.append((key, values))
        return True


class PlayersUnitTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-players-")
        self.clock = support.FakeClock()
        self.wall = support.FakeClock(WEDNESDAY)
        self.players = Players(self.home, wall=self.wall, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_periodes(self):
        self.assertEqual(period_days("day", WEDNESDAY), ["2026-11-11"])
        self.assertEqual(period_days("week", WEDNESDAY), ["2026-11-11", "2026-11-10", "2026-11-09"])

    def test_temps_compte_et_enregistre(self):
        self.players.begin("P1", {"name": "Lea"})
        self.clock.advance(600)
        self.assertAlmostEqual(self.players.used_s("P1"), 600)
        self.assertAlmostEqual(self.players.remaining_s("P1", 30), 1200)
        self.players.finish()
        reloaded = Players(self.home, wall=self.wall, clock=self.clock)
        self.assertAlmostEqual(reloaded.used_s("P1"), 600)
        self.assertIsNone(reloaded.remaining_s("P1", 0), "0 = pas de limite")

    def test_sauvegarde_pendant_la_partie(self):
        self.players.begin("P1", {"name": "Lea"})
        self.clock.advance(players_module.SAVE_EVERY_S + 1)
        self.players.tick()
        with open(os.path.join(self.home, players_module.PLAYERS_FILENAME), encoding="utf-8") as handle:
            saved = json.load(handle)["usage"]["P1"]
        self.assertGreater(sum(saved.values()), players_module.SAVE_EVERY_S)

    def test_nouveau_jour_nouvelle_periode(self):
        self.players.begin("P1", {"name": "Lea"})
        self.clock.advance(1800)
        self.players.finish()
        self.wall.advance(86400)
        self.assertEqual(self.players.used_s("P1", "day"), 0)
        self.assertAlmostEqual(self.players.used_s("P1", "week"), 1800)

    def test_carte_valable_une_fois_et_peu_de_temps(self):
        self.players.arm("P1", {"name": "Lea"})
        self.assertEqual(self.players.take_pending()["uid"], "P1")
        self.assertIsNone(self.players.take_pending(), "une carte par partie")
        self.players.arm("P1", {"name": "Lea"})
        self.clock.advance(players_module.ARM_WINDOW_S + 1)
        self.assertIsNone(self.players.take_pending())

    def test_invite(self):
        self.players.begin("", {})
        self.clock.advance(120)
        self.assertAlmostEqual(self.players.used_s(""), 120)
        self.assertAlmostEqual(self.players.used_s(GUEST), 120)

    def test_statistiques_par_jeu(self):
        self.players.begin("P1", {"name": "Lea"}, game={"system": "snes", "name": "Mario"})
        self.clock.advance(600)
        self.players.begin("", {}, via="menu", game={"system": "megadrive", "name": "Sonic"})
        self.clock.advance(120)
        self.players.begin("P1", {"name": "Lea"})  # unknown game: counted, not in the stats
        self.clock.advance(60)
        self.players.finish()
        self.players.reset("P1")
        rows = players_module.stats_rows(self.home)
        self.assertEqual(sorted((r["uid"], r["system"], r["game"], r["seconds"]) for r in rows),
                         [("P1", "snes", "Mario", 600), (GUEST, "megadrive", "Sonic", 120)])
        self.assertEqual({r["date"] for r in rows}, {"2026-11-11"})
        self.assertEqual(self.players.used_s("P1", "week"), 0, "la remise a zero ne touche que le quota")

    def test_statistiques_fichier_absent_ou_ancien(self):
        self.assertEqual(players_module.stats_rows(self.home), [])
        with open(os.path.join(self.home, players_module.PLAYERS_FILENAME), "w", encoding="utf-8") as handle:
            json.dump({"usage": {"P1": {"2026-11-11": 60}}}, handle)
        self.assertEqual(players_module.stats_rows(self.home), [])
        self.assertAlmostEqual(Players(self.home, wall=self.wall, clock=self.clock).used_s("P1"), 60)

    def test_remise_a_zero(self):
        self.players.begin("P1", {"name": "Lea"})
        self.clock.advance(900)
        self.players.finish()
        self.players.reset("P1")
        self.assertEqual(self.players.used_s("P1", "week"), 0)


class PlayerCardsTest(unittest.TestCase):
    CONFIG = "[players]\nenabled = 1\n"

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-player-cards-")
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.launcher = support.FakeLauncher()
        self.feedback = support.FakeFeedback()
        self.clock = support.FakeClock()
        self.wall = support.FakeClock(WEDNESDAY)
        self.screen = FakeScreen()
        self.config = Config(os.path.join(self.directory, "config.ini"))
        self.playtime = PlayTimer(self.directory, clock=self.clock, wall=self.wall)
        self.players = Players(self.directory, wall=self.wall, clock=self.clock)
        self.store.put("6A0E0001", "snes", "Mario.smc", "Mario")
        self.store.put_entry("1EA00001", {"kind": "action", "action": "player", "name": "Lea",
                                          "params": {"quota_min": 30, "period": "day"}})
        self.store.put_entry("70A00002", {"kind": "action", "action": "player", "name": "Tom",
                                          "params": {"quota_min": 0, "period": "day"}})
        self.controller = self.make(self.CONFIG)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def make(self, text):
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.config.reload()
        return Controller(self.store, self.launcher, self.feedback, self.config, None,
                          state_provider=lambda: dict(IDLE), clock=self.clock,
                          playtime=self.playtime, screen=self.screen, players=self.players)

    def end_game(self):
        self.controller.stop_game("quit")

    def test_nouvelle_partie_meme_joueur(self):
        self.assertEqual(self.controller.on_badge("1EA00001"), "player")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "launched")
        self.assertEqual(self.players.current["game"], {"system": "snes", "name": "Mario"})
        player = (self.players.current["uid"], self.players.current["entry"])
        self.controller.stop_game("new")
        self.assertIsNone(self.players.current)
        self.assertEqual(self.controller.new_game("6a0e0001", player), "launched")
        self.assertEqual(self.players.current["uid"], "1EA00001", "la nouvelle partie reste a Lea")
        self.assertEqual(self.controller.new_game("1EA00001"), "no_card", "pas une carte de jeu")

    def test_deverrouille_rien_n_est_bloque(self):
        free = [False]
        controller = Controller(self.store, self.launcher, self.feedback,
                                self.make("[players]\nenabled = 1\nrequire = 1\n").cfg, None,
                                state_provider=lambda: dict(IDLE), clock=self.clock,
                                playtime=self.playtime, screen=self.screen, players=self.players,
                                unlocked=lambda: free[0])
        self.assertEqual(controller.on_badge("6A0E0001"), "player_needed")
        free[0] = True
        self.assertEqual(controller.on_badge("6A0E0001"), "launched", "deverrouille : pas de carte joueur exigee")
        self.assertEqual(self.players.current["uid"], GUEST, "le temps reste compte")

    def test_carte_deverrouiller(self):
        self.store.put_entry("0FE00001", {"kind": "action", "action": "unlock", "name": "Parents"})
        calls = []
        controller = Controller(self.store, self.launcher, self.feedback, self.config, None,
                                state_provider=lambda: dict(IDLE), clock=self.clock,
                                players=self.players, unlock=lambda: calls.append(1) or "unlock")
        self.assertEqual(controller.on_badge("0FE00001"), "unlock")
        self.assertEqual(calls, [1])
        self.assertEqual(self.store.get("0FE00001")["params"], {})

    def test_parametres_de_la_carte(self):
        with self.assertRaises(StorageError):
            self.store.put_entry("1EA00009", {"kind": "action", "action": "player", "params": {"period": "year"}})
        self.store.put_entry("1EA00009", {"kind": "action", "action": "player", "params": {"quota_min": "45"}})
        self.assertEqual(self.store.get("1EA00009")["params"], {"quota_min": 45, "period": "day"})

    def test_desactive_par_defaut(self):
        controller = self.make("")
        self.assertEqual(controller.on_badge("1EA00001"), "disabled")
        self.assertEqual(controller.on_badge("6A0E0001"), "launched")
        self.assertIsNone(self.players.current, "rien n'est compte quand l'option est coupee")

    def test_carte_joueur_puis_jeu(self):
        self.assertEqual(self.controller.on_badge("1EA00001"), "player")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "launched")
        self.assertEqual(self.players.current["uid"], "1EA00001")
        # The game lasts at most the 30 minutes left to Lea.
        self.assertAlmostEqual(self.playtime.remaining_s(), 1800)

    def test_le_joueur_suivant_doit_reposer_sa_carte(self):
        self.controller.on_badge("1EA00001")
        self.controller.on_badge("6A0E0001")
        self.clock.advance(600)
        self.end_game()
        self.assertAlmostEqual(self.players.used_s("1EA00001"), 600)
        # Next game without a card: counted for the guest, not for Lea.
        self.controller.on_badge("6A0E0001")
        self.assertEqual(self.players.current["uid"], GUEST)

    def test_temps_epuise_refuse(self):
        self.controller.on_badge("1EA00001")
        self.controller.on_badge("6A0E0001")
        self.clock.advance(1800)
        self.end_game()
        self.assertEqual(self.controller.on_badge("1EA00001"), "exhausted")
        self.assertEqual(self.screen.said[-1][0], "player_exhausted")

    def test_carte_illimitee(self):
        self.controller.on_badge("70A00002")
        self.controller.on_badge("6A0E0001")
        self.assertEqual(self.players.current["uid"], "70A00002")
        self.assertIsNone(self.playtime.remaining_s(), "pas de limite pour Tom")

    def test_carte_joueur_exigee(self):
        controller = self.make(self.CONFIG + "require = 1\n")
        self.assertEqual(controller.on_badge("6A0E0001"), "player_needed")
        self.assertEqual(self.launcher.calls, [])
        controller.on_badge("70A00002")
        self.assertEqual(controller.on_badge("6A0E0001"), "launched")

    def test_temps_de_l_invite(self):
        controller = self.make(self.CONFIG + "guest_quota_min = 10\n")
        controller.on_badge("6A0E0001")
        self.assertAlmostEqual(self.playtime.remaining_s(), 600)
        self.clock.advance(600)
        controller.stop_game("time")
        self.assertEqual(controller.on_badge("6A0E0001"), "exhausted")
        self.assertEqual(self.screen.said[-1][0], "guest_exhausted")

    def test_carte_posee_pendant_un_jeu_du_menu(self):
        """Game started from the menu, then the player card: the game is hers."""
        self.launcher.running = True
        self.assertEqual(self.controller.on_badge("1EA00001"), "player_game")
        self.assertEqual(self.players.current["via"], "reader")
        self.assertAlmostEqual(self.playtime.remaining_s(), 1800)
        self.assertEqual(self.screen.said[-1], ("player_hello", {"name": "Lea", "n": 30}))


class MenuGamesTest(unittest.TestCase):
    """The service watches the games started from the Recalbox menu."""

    def setUp(self):
        from rfid import daemon
        from unittest import mock
        self.directory = tempfile.mkdtemp(prefix="rfid-menu-games-")
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.store.put_entry("1EA00001", {"kind": "action", "action": "player", "name": "Lea",
                                          "params": {"quota_min": 30, "period": "day"}})
        self.launcher = support.FakeLauncher()
        self.feedback = support.FakeFeedback()
        self.clock = support.FakeClock()
        self.wall = support.FakeClock(WEDNESDAY)
        self.screen = FakeScreen()
        self.config = Config(os.path.join(self.directory, "config.ini"))
        self.playtime = PlayTimer(self.directory, clock=self.clock, wall=self.wall)
        self.players = Players(self.directory, wall=self.wall, clock=self.clock)
        service = daemon.Service.__new__(daemon.Service)
        service.home = self.directory
        service.store = self.store
        service.screen = self.screen
        service.feedback = self.feedback
        service.light = None
        service.playtime = self.playtime
        service.players = self.players
        service.log = mock.Mock()
        service._active_uid = None
        service._absent_since = None
        service._absent_hits = 0
        service._launched_uid = None
        service._stop_pending = None
        service._stop_on_remove = False
        service._next_player_check = 0.0
        service._players_gone = 0
        service._refusing = False
        service._expire_at = None
        self.service = service
        self._time = mock.patch.object(daemon.time, "monotonic", side_effect=lambda: self.clock.now)
        self._time.start()

    def tearDown(self):
        self._time.stop()
        shutil.rmtree(self.directory, ignore_errors=True)

    def configure(self, text):
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write("[players]\nenabled = 1\n" + text)
        self.config.reload()
        self.service.controller = Controller(
            self.store, self.launcher, self.feedback, self.config, None,
            state_provider=lambda: dict(IDLE), clock=self.clock,
            playtime=self.playtime, screen=self.screen, players=self.players)

    def step(self):
        self.clock.advance(2.1)
        self.service._players_step()

    def test_jeu_du_menu_sans_carte_bloque(self):
        self.configure("require = 1\n")
        self.launcher.running = True
        self.step()
        self.assertEqual(self.screen.said[-1][0], "player_needed")
        self.assertIsNotNone(self.service._expire_at, "le jeu sera quitte apres le message")

    def test_jeu_du_menu_compte_pour_l_invite(self):
        self.configure("")
        self.launcher.running = True
        self.step()
        self.assertEqual(self.players.current["uid"], GUEST)
        self.assertIsNone(self.service._expire_at)

    def test_jeu_du_menu_avec_la_carte_posee_puis_retrait(self):
        self.configure("require = 1\n")
        self.service._active_uid = "1EA00001"
        self.launcher.running = True
        self.step()
        self.assertEqual(self.players.current["uid"], "1EA00001")
        self.assertEqual(self.players.current["via"], "reader")
        self.assertAlmostEqual(self.playtime.remaining_s(), 1800)
        # The card is lifted: the game ends.
        self.service._release_latch()
        self.assertIsNotNone(self.service._stop_pending)
        self.assertEqual(self.screen.said[-1][0], "player_left")

    def test_carte_soulevee_avant_le_jeu_du_menu(self):
        """Placed then lifted, the card does not count for a menu game."""
        self.configure("require = 1\n")
        self.service.controller.on_badge("1EA00001")
        self.launcher.running = True
        self.step()
        self.assertEqual(self.screen.said[-1][0], "player_needed")
        self.assertIsNone(self.players.pending, "la carte ne sert plus a la partie suivante")

    def test_temps_epuise_bloque_le_menu(self):
        self.configure("")
        self.service._active_uid = "1EA00001"
        self.players.begin("1EA00001", self.store.get("1EA00001"))
        self.clock.advance(1800)
        self.players.finish()
        self.launcher.running = True
        self.step()
        self.assertEqual(self.screen.said[-1][0], "player_exhausted")

    def test_fin_de_partie_enregistree(self):
        self.configure("")
        self.launcher.running = True
        self.step()
        self.clock.advance(300)
        self.launcher.running = False
        for _ in range(3):
            self.step()
        self.assertIsNone(self.players.current)
        self.assertGreater(self.players.used_s(GUEST), 300)


if __name__ == "__main__":
    unittest.main()
