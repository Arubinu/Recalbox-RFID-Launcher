"""Special cards, time-limited games and bonus cards."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support
from rfid.config import Config
from rfid.controller import Controller
from rfid.esbridge import Target
from rfid.playtime import RESUME_WINDOW_S, PlayTimer
from rfid.storage import StorageError, TagStore

IDLE = {"State": "selected"}
PLAYING = {"State": "playing"}


class FakeScreen:
    def __init__(self):
        self.said = []

    def say(self, key, **values):
        self.said.append((key, values))
        return True


class FakeLight:
    def __init__(self):
        self.events = []

    def flash(self, event):
        self.events.append(event)


class FakeLibrary:
    def __init__(self, games):
        self.games = games
        self.calls = []

    def pick_random(self, system="", favorites_only=False, rng=None):
        self.calls.append((system, favorites_only))
        pool = [g for g in self.games if (not system or g["system"] == system) and (g["favorite"] or not favorites_only)]
        return pool[0] if pool else None


class StorageKindsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-kinds-")
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_carte_speciale_enregistree_et_relue(self):
        self.store.put_entry("A1B2C3D4", {"kind": "action", "action": "bonus",
                                          "params": {"minutes": 15, "uses": 2, "period_h": 24},
                                          "name": "Bonus"})
        reloaded = TagStore(self.store.path)
        reloaded.load()
        entry = reloaded.get("A1B2C3D4")
        self.assertEqual(entry["kind"], "action")
        self.assertEqual(entry["params"], {"minutes": 15, "uses": 2, "period_h": 24})
        self.assertEqual(entry["system"], "")

    def test_action_inconnue_refusee(self):
        with self.assertRaises(StorageError):
            self.store.put_entry("A1B2C3D4", {"kind": "action", "action": "format_c"})

    def test_parametres_bonus_bornes(self):
        with self.assertRaises(StorageError):
            self.store.put_entry("A1B2C3D4", {"kind": "action", "action": "bonus", "params": {"minutes": 999}})

    def test_limite_de_temps(self):
        self.store.put("A1B2C3D4", "snes", "Mario.smc")
        self.assertIsNone(self.store.get("A1B2C3D4")["limit_min"])
        self.store.update("A1B2C3D4", {"limit_min": 30})
        self.assertEqual(self.store.get("A1B2C3D4")["limit_min"], 30)
        self.store.update("A1B2C3D4", {"limit_min": ""})
        self.assertIsNone(self.store.get("A1B2C3D4")["limit_min"])
        with self.assertRaises(StorageError):
            self.store.update("A1B2C3D4", {"limit_min": -5})

    def test_renommer_garde_les_statistiques(self):
        self.store.put("A1B2C3D4", "snes", "Mario.smc")
        self.store.touch("A1B2C3D4")
        self.store.update("A1B2C3D4", {"name": "Mon Mario"})
        entry = self.store.get("A1B2C3D4")
        self.assertEqual(entry["name"], "Mon Mario")
        self.assertEqual(entry["hits"], 1)

    def test_csv_aller_retour_avec_cartes_speciales(self):
        self.store.put("A1B2C3D4", "snes", "Mario.smc", "Mario")
        self.store.update("A1B2C3D4", {"limit_min": 20})
        self.store.put_entry("B1B2C3D4", {"kind": "action", "action": "random",
                                          "params": {"system": "nes", "favorites": True}})
        path = os.path.join(self.directory, "export.csv")
        self.store.export_csv(path)
        other = TagStore(os.path.join(self.directory, "other.json"))
        other.load()
        stats = other.import_csv(path)
        self.assertEqual(stats["ajoutes"], 2)
        self.assertEqual(other.get("A1B2C3D4")["limit_min"], 20)
        self.assertEqual(other.get("B1B2C3D4")["params"], {"system": "nes", "favorites": True})

    def test_ancien_csv_toujours_lisible(self):
        path = os.path.join(self.directory, "old.csv")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("uid;system;game;name\nA1:B2:C3:D4;snes;Mario.smc;Mario\n")
        self.assertEqual(self.store.import_csv(path)["ajoutes"], 1)
        self.assertEqual(self.store.get("A1B2C3D4")["kind"], "game")


class SpecialCardsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-special-")
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.launcher = support.FakeLauncher()
        self.feedback = support.FakeFeedback()
        self.clock = support.FakeClock()
        self.wall = support.FakeClock(1_800_000_000.0)
        self.state = dict(IDLE)
        self.config = Config(os.path.join(self.directory, "config.ini"))
        self.screen = FakeScreen()
        self.light = FakeLight()
        self.powered_off = []
        self.library = FakeLibrary([
            {"system": "nes", "path": "/recalbox/share/roms/nes/Zelda.nes", "name": "Zelda", "favorite": True},
            {"system": "snes", "path": "/recalbox/share/roms/snes/Mario.smc", "name": "Mario", "favorite": False},
        ])
        self.playtime = PlayTimer(self.directory, clock=self.clock, wall=self.wall)
        self.controller = self.make()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def make(self, text=""):
        if text:
            with open(self.config.path, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.config.reload()
        return Controller(self.store, self.launcher, self.feedback, self.config, None,
                          state_provider=lambda: self.state, clock=self.clock,
                          library=self.library, playtime=self.playtime, screen=self.screen,
                          light=self.light, power=lambda: self.powered_off.append(True))

    def card(self, uid, action, params=None, **extra):
        entry = {"kind": "action", "action": action, "params": params or {}}
        entry.update(extra)
        self.store.put_entry(uid, entry)

    # ------------------------------------------------------------- association
    def test_association_d_une_carte_preparee(self):
        self.assertEqual(self.controller.arm_entry({"kind": "action", "action": "quit", "name": "Stop"}),
                         "armed_associate")
        self.assertEqual(self.controller.status()["target"], "Stop")
        self.assertEqual(self.controller.on_badge("C0FFEE01"), "bound")
        self.assertEqual(self.store.get("C0FFEE01")["action"], "quit")
        self.assertIn(("bound", {}), self.screen.said)

    def test_association_d_un_jeu_choisi_dans_la_page(self):
        target = Target(system="nes", game="Zelda.nes", name="Zelda", path="/recalbox/share/roms/nes/Zelda.nes")
        self.controller.arm_target(target)
        self.assertEqual(self.controller.on_badge("C0FFEE02"), "bound")
        self.assertEqual(self.store.get("C0FFEE02")["path"], "/recalbox/share/roms/nes/Zelda.nes")

    # --------------------------------------------------------------- actions
    def test_jeu_au_hasard(self):
        self.card("AA000001", "random", {"system": "", "favorites": True})
        self.assertEqual(self.controller.on_badge("AA000001"), "launched")
        self.assertEqual(self.launcher.calls, [("nes", "/recalbox/share/roms/nes/Zelda.nes")])
        self.assertEqual(self.library.calls, [("", True)])
        self.assertEqual(self.store.get("AA000001")["hits"], 1)

    def test_jeu_au_hasard_sans_jeu(self):
        self.card("AA000001", "random", {"system": "gba"})
        self.assertEqual(self.controller.on_badge("AA000001"), "nothing")
        self.assertIn("error", self.feedback.events)

    def test_quitter_pendant_une_partie(self):
        self.card("AA000002", "quit")
        self.launcher.running = True
        self.state = dict(PLAYING)
        self.assertEqual(self.controller.on_badge("AA000002"), "quit")
        self.assertFalse(self.launcher.running)

    def test_eteindre(self):
        self.card("AA000003", "poweroff")
        self.assertEqual(self.controller.on_badge("AA000003"), "poweroff")
        self.assertEqual(self.powered_off, [True])

    def test_un_jeu_ne_coupe_pas_une_partie(self):
        self.store.put("AA000004", "snes", "Mario.smc")
        self.state = dict(PLAYING)
        self.assertEqual(self.controller.on_badge("AA000004"), "ignored")

    # ------------------------------------------------------------- play time
    def test_limite_par_carte(self):
        self.store.put("AA000005", "snes", "Mario.smc", "Mario")
        self.store.update("AA000005", {"limit_min": 10})
        self.controller.on_badge("AA000005")
        self.assertEqual(int(self.playtime.remaining_s()), 600)

    def test_limite_generale(self):
        controller = self.make("[time]\ndefault_limit_min = 30\n")
        self.store.put("AA000006", "snes", "Mario.smc")
        controller.on_badge("AA000006")
        self.assertEqual(int(self.playtime.remaining_s()), 1800)
        self.store.put("AA000007", "snes", "Mario.smc")
        self.store.update("AA000007", {"limit_min": 0})
        controller.on_badge("AA000007")
        self.assertIsNone(self.playtime.remaining_s(), "0 = sans limite, meme avec un reglage general")

    def test_avertissements_puis_fin(self):
        self.playtime.start("AA", {"name": "Mario"}, 10)
        self.clock.advance(5 * 60 + 1)
        self.assertEqual(self.playtime.tick(), "warn300")
        self.assertEqual(self.playtime.tick(), "")
        self.clock.advance(4 * 60)
        self.assertEqual(self.playtime.tick(), "warn60")
        self.clock.advance(60)
        self.assertEqual(self.playtime.tick(), "expired")
        self.assertIsNone(self.playtime.session)
        self.assertEqual(self.playtime.last["reason"], "time")

    def test_partie_courte_sans_avertissement_inutile(self):
        self.playtime.start("AA", {"name": "Mario"}, 1)
        self.assertEqual(self.playtime.tick(), "")
        self.clock.advance(61)
        self.assertEqual(self.playtime.tick(), "expired")

    # ----------------------------------------------------------------- bonus
    def test_bonus_pendant_la_partie(self):
        self.card("B0000001", "bonus", {"minutes": 10, "uses": 2, "period_h": 24})
        self.store.put("AA000008", "snes", "Mario.smc")
        self.store.update("AA000008", {"limit_min": 5})
        self.controller.on_badge("AA000008")
        self.state = dict(PLAYING)
        self.assertEqual(self.controller.on_badge("B0000001"), "extended")
        self.assertEqual(int(self.playtime.remaining_s()), 15 * 60)
        self.assertIn(("bonus_left", {"n": 10, "k": 1}), self.screen.said)
        self.assertIn("bonus", self.light.events)

    def test_bonus_quota(self):
        self.card("B0000001", "bonus", {"minutes": 5, "uses": 1, "period_h": 24})
        self.playtime.start("AA", {"name": "Mario"}, 5)
        self.assertEqual(self.controller.on_badge("B0000001"), "extended")
        self.assertEqual(self.controller.on_badge("B0000001"), "exhausted")
        self.assertIn(("exhausted", {}), self.screen.said)
        # A new period gives the use back.
        self.wall.advance(24 * 3600 + 1)
        self.assertEqual(self.controller.on_badge("B0000001"), "extended")

    def test_bonus_quota_garde_au_redemarrage(self):
        self.card("B0000001", "bonus", {"minutes": 5, "uses": 1, "period_h": 24})
        self.playtime.start("AA", {"name": "Mario"}, 5)
        self.controller.on_badge("B0000001")
        again = PlayTimer(self.directory, clock=self.clock, wall=self.wall)
        self.assertEqual(again.bonus_left("B0000001", {"uses": 1, "period_h": 24}), 0)

    def test_horloge_remise_a_zero_oublie_les_utilisations(self):
        self.card("B0000001", "bonus", {"minutes": 5, "uses": 1, "period_h": 24})
        self.playtime.start("AA", {"name": "Mario"}, 5)
        self.controller.on_badge("B0000001")
        self.wall.now = 315_532_800.0          # 1980: no network time yet
        self.assertEqual(self.playtime.bonus_left("B0000001", {"uses": 1, "period_h": 24}), 1)

    def test_bonus_relance_le_jeu_qui_vient_de_finir(self):
        self.card("B0000001", "bonus", {"minutes": 10, "uses": 0, "period_h": 24})
        self.store.put("AA000009", "snes", "Mario.smc", "Mario", "/recalbox/share/roms/snes/Mario.smc")
        self.store.update("AA000009", {"limit_min": 5})
        self.controller.on_badge("AA000009")
        self.clock.advance(5 * 60 + 1)
        self.playtime.tick()                     # time up
        self.controller.stop_game("time")
        self.launcher.calls.clear()
        self.assertEqual(self.controller.on_badge("B0000001"), "resumed")
        self.assertEqual(self.launcher.calls, [("snes", "/recalbox/share/roms/snes/Mario.smc")])
        self.assertEqual(int(self.playtime.remaining_s()), 10 * 60)
        self.assertEqual(self.controller.last_action, "launched")

    def test_bonus_trop_tard(self):
        self.card("B0000001", "bonus", {"minutes": 10, "uses": 0, "period_h": 24})
        self.playtime.start("AA", {"name": "Mario"}, 1)
        self.clock.advance(61)
        self.playtime.tick()
        self.clock.advance(RESUME_WINDOW_S + 1)
        self.assertEqual(self.controller.on_badge("B0000001"), "nothing")

    def test_bonus_sans_jeu_limite(self):
        self.card("B0000001", "bonus", {"minutes": 10})
        self.assertEqual(self.controller.on_badge("B0000001"), "nothing")
        self.assertEqual(self.launcher.calls, [])

    def test_last_action_decrit_seulement_ce_badge(self):
        self.card("B0000001", "bonus", {"minutes": 10, "uses": 0})
        self.store.put("AA00000A", "snes", "Mario.smc")
        self.store.update("AA00000A", {"limit_min": 5})
        self.controller.on_badge("AA00000A")
        self.assertEqual(self.controller.last_action, "launched")
        self.state = dict(PLAYING)
        self.controller.on_badge("B0000001")
        self.assertEqual(self.controller.last_action, "", "la carte bonus ne tient pas le jeu")


if __name__ == "__main__":
    unittest.main()
