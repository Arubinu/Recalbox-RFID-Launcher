"""Several players per game, and the controllers allowed."""

from __future__ import annotations

import os
import tempfile
import shutil
import unittest
from unittest import mock

import support
from rfid import pads
from rfid.config import Config
from rfid.controller import CHAIN_S, Controller
from rfid.players import Players
from rfid.playtime import PlayTimer
from rfid.storage import TagStore
from test_players import IDLE, WEDNESDAY, FakeScreen

LEA, TOM, MAX = "1EA00001", "70A00002", "3A800003"


class GroupTestCase(unittest.TestCase):
    CONFIG = "[players]\nenabled = 1\nmulti = remove\n"

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-group-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.store = TagStore(os.path.join(self.home, "tags.json"))
        self.store.load()
        self.launcher = support.FakeLauncher()
        self.feedback = support.FakeFeedback()
        self.clock = support.FakeClock()
        self.wall = support.FakeClock(WEDNESDAY)
        self.screen = FakeScreen()
        self.config = Config(os.path.join(self.home, "config.ini"))
        self.playtime = PlayTimer(self.home, clock=self.clock, wall=self.wall)
        self.players = Players(self.home, wall=self.wall, clock=self.clock)
        self.store.put("6A0E0001", "snes", "Mario.smc", "Mario", path="/roms/snes/Mario.smc")
        for uid, name, quota in ((LEA, "Lea", 60), (TOM, "Tom", 20), (MAX, "Max", 0)):
            self.store.put_entry(uid, {"kind": "action", "action": "player", "name": name,
                                       "params": {"quota_min": quota, "period": "day"}})
        self.limits = []
        patcher = mock.patch.object(pads, "set_max_users", side_effect=self.limits.append)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.controller = self.make(self.CONFIG)

    def make(self, text):
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.config.reload()
        return Controller(self.store, self.launcher, self.feedback, self.config, None,
                          state_provider=lambda: dict(IDLE), clock=self.clock, playtime=self.playtime,
                          screen=self.screen, players=self.players, home=self.home)

    def group(self):
        return [uid for uid, _entry in self.controller.waiting_group()[0]]

    def said(self):
        return [key for key, _values in self.screen.said]


class RemoveModeTest(GroupTestCase):
    def test_les_cartes_s_additionnent(self):
        self.assertEqual(self.controller.on_badge(LEA), "player")
        self.assertEqual(self.controller.on_badge(TOM), "player_added")
        self.assertEqual(self.group(), [LEA, TOM])
        self.assertEqual(self.screen.said[-1], ("players_next", {"names": "Lea & Tom"}))

    def test_reposer_retire_le_joueur(self):
        self.controller.on_badge(LEA)
        self.controller.on_badge(TOM)
        self.assertEqual(self.controller.on_badge(LEA), "player_removed")
        self.assertEqual(self.group(), [TOM], "pour passer de Lea a Tom")
        self.assertEqual(self.controller.on_badge(TOM), "player_off")
        self.assertEqual(self.group(), [])

    def test_le_temps_compte_pour_chacun(self):
        self.controller.on_badge(LEA)
        self.controller.on_badge(TOM)
        self.assertEqual(self.controller.on_badge("6A0E0001"), "launched")
        self.assertEqual(self.players.playing_uids(), [LEA, TOM])
        self.assertAlmostEqual(self.playtime.remaining_s(), 20 * 60, delta=1, msg="le plus court des deux")
        self.clock.advance(300)
        self.players.finish()
        self.assertAlmostEqual(self.players.used_s(LEA), 300, delta=1)
        self.assertAlmostEqual(self.players.used_s(TOM), 300, delta=1)

    def test_refuse_si_un_joueur_n_a_plus_de_temps(self):
        self.controller.on_badge(LEA)
        self.controller.on_badge(TOM)
        self.players.usage[TOM] = {self.players._period_key("day")[2:]: 20 * 60}  # used up meanwhile
        self.assertEqual(self.controller.on_badge("6A0E0001"), "exhausted")
        self.assertEqual(self.screen.said[-1], ("player_exhausted", {"name": "Tom"}))
        self.assertEqual(self.group(), [LEA, TOM], "le groupe attend toujours")


class OtherModesTest(GroupTestCase):
    def test_solo(self):
        self.controller = self.make("[players]\nenabled = 1\nmulti = solo\n")
        self.controller.on_badge(LEA)
        self.controller.on_badge(TOM)
        self.assertEqual(self.controller.on_badge(TOM), "player_solo")
        self.assertEqual(self.group(), [TOM])
        self.assertEqual(self.controller.on_badge(TOM), "player_off")
        self.assertEqual(self.group(), [])

    def test_a_la_suite(self):
        self.controller = self.make("[players]\nenabled = 1\nmulti = chain\n")
        self.controller.on_badge(LEA)
        self.clock.advance(CHAIN_S - 1)
        self.assertEqual(self.controller.on_badge(TOM), "player_added")
        self.clock.advance(CHAIN_S + 1)
        self.assertEqual(self.controller.on_badge(MAX), "player", "plus tard : nouveau groupe")
        self.assertEqual(self.group(), [MAX])

    def test_desactive_une_carte_remplace_l_autre(self):
        self.controller = self.make("[players]\nenabled = 1\n")
        self.controller.on_badge(LEA)
        self.assertEqual(self.controller.on_badge(TOM), "player")
        self.assertEqual(self.group(), [TOM])


class PadsTest(GroupTestCase):
    def test_une_manette_par_joueur(self):
        self.controller = self.make("[players]\nenabled = 1\nmulti = remove\npads = players\n")
        self.controller.on_badge(LEA)
        self.controller.on_badge(TOM)
        self.assertEqual(self.limits[-1], 2)
        self.controller.on_badge("6A0E0001")
        self.assertEqual(self.limits[-1], 2)
        self.players.finish()
        self.players.kept = None
        self.controller.sync_pads()
        self.assertEqual(self.limits[-1], 1, "sans joueur : une seule manette")

    def test_toutes_les_manettes(self):
        self.controller.on_badge(LEA)
        self.controller.sync_pads()
        self.assertIsNone(self.limits[-1])

    def test_bloc_du_fichier(self):
        folder = tempfile.mkdtemp(prefix="rfid-pads-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "overrides.cfg")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('video_smooth = "true"\n')
        pads.set_block(['input_max_users = "2"'], pads.BEGIN, pads.END, path)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn('input_max_users = "2"', content)
        self.assertIn('video_smooth = "true"', content)
        self.assertFalse(pads.set_block(['input_max_users = "2"'], pads.BEGIN, pads.END, path), "deja ecrit")
        pads.set_block(None, pads.BEGIN, pads.END, path)
        self.assertEqual(open(path, encoding="utf-8").read(), 'video_smooth = "true"\n')


if __name__ == "__main__":
    unittest.main()
