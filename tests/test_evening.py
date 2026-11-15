"""Bedtime, refused games, "continue" card, trophies, hint line and dimming of the reader screen."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import support
from rfid import bedtime, refusals, screen, trophies
from rfid.config import Config
from rfid.controller import Controller
from rfid.players import Players
from rfid.playtime import PlayTimer
from rfid.storage import TagStore
from rfid.wsagent import validate_option
from test_players import IDLE, WEDNESDAY, FakeScreen


def at(hour, minute=0):
    """A wall time today at hour:minute (local time)."""
    now = time.localtime()
    return time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, minute, 0, 0, 0, -1))


class BedtimeTest(unittest.TestCase):
    def test_heures(self):
        self.assertEqual(bedtime.parse("21:30"), 21 * 60 + 30)
        self.assertIsNone(bedtime.parse(""))
        self.assertIsNone(bedtime.parse("25:00"))
        self.assertEqual(bedtime.clock_text(7 * 60), "07:00")

    def test_fenetre_qui_passe_minuit(self):
        span = (21 * 60, 7 * 60)
        self.assertTrue(bedtime.active(span, at(22)))
        self.assertTrue(bedtime.active(span, at(6, 59)))
        self.assertFalse(bedtime.active(span, at(7)))
        self.assertFalse(bedtime.active(span, at(20, 59)))
        self.assertAlmostEqual(bedtime.minutes_to_start(span, at(20, 55)), 5, delta=0.1)
        self.assertEqual(bedtime.minutes_to_start(span, at(23)), 0)

    def test_fenetre_dans_la_journee(self):
        span = (12 * 60, 14 * 60)
        self.assertTrue(bedtime.active(span, at(13)))
        self.assertFalse(bedtime.active(span, at(15)))
        self.assertIsNone(bedtime.minutes_to_start(None, at(15)))

    def test_reglage(self):
        option = {"type": "time", "label": "Heure"}
        self.assertEqual(validate_option(option, "9:05"), "09:05")
        self.assertEqual(validate_option(option, ""), "")
        with self.assertRaises(ValueError):
            validate_option(option, "demain")


class CardsTestCase(unittest.TestCase):
    CONFIG = "[players]\nenabled = 1\n"

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-evening-")
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
        self.store.put("6A0E0001", "snes", "Mario.smc", "Mario", path="/recalbox/share/roms/snes/Mario.smc")
        self.store.put("6A0E0002", "megadrive", "Sonic.md", "Sonic", path="/recalbox/share/roms/megadrive/Sonic.md")
        self.store.put_entry("1EA00001", {"kind": "action", "action": "player", "name": "Lea",
                                          "params": {"quota_min": 0, "period": "day"}})
        self.store.put_entry("70A00002", {"kind": "action", "action": "player", "name": "Tom",
                                          "params": {"quota_min": 0, "period": "day"}})
        self.store.put_entry("C0000001", {"kind": "action", "action": "continue"})
        self.controller = self.make(self.CONFIG)

    def make(self, text):
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.config.reload()
        return Controller(self.store, self.launcher, self.feedback, self.config, None,
                          state_provider=lambda: dict(IDLE), clock=self.clock, playtime=self.playtime,
                          screen=self.screen, players=self.players, home=self.home)

    def end_game(self):
        self.launcher.running = False
        self.players.finish()


class RefusalsAndBedtimeTest(CardsTestCase):
    def test_jeu_refuse_note(self):
        self.controller = self.make("[players]\nenabled = 1\nrequire = 1\n")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "player_needed")
        rows = refusals.read(self.home)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "player_needed")
        self.assertEqual(rows[0]["game"], "Mario")
        self.assertEqual(rows[0]["card"], "6A0E0001")
        refusals.clear(self.home)
        self.assertEqual(refusals.read(self.home), [])

    def test_heure_du_coucher_refuse_les_jeux(self):
        moment = time.localtime()
        now = moment.tm_hour * 60 + moment.tm_min
        start, end = (now - 30) % 1440, (now + 30) % 1440
        self.controller = self.make("[players]\nenabled = 1\n[time]\ncurfew_from = %s\ncurfew_to = %s\n"
                                    % (bedtime.clock_text(start), bedtime.clock_text(end)))
        self.assertEqual(self.controller.on_badge("6A0E0001"), "curfew")
        self.assertEqual(self.launcher.calls, [])
        self.assertEqual(refusals.read(self.home)[0]["reason"], "curfew")
        with mock.patch.object(Controller, "unlocked", new_callable=mock.PropertyMock, return_value=True):
            self.assertEqual(self.controller.on_badge("6A0E0001"), "launched", "la carte Deverrouiller l'ignore")


class ContinueCardTest(CardsTestCase):
    def test_reprend_le_dernier_jeu_du_joueur(self):
        self.controller.on_badge("1EA00001")
        self.assertEqual(self.controller.on_badge("6A0E0001"), "launched")
        self.end_game()
        self.controller.on_badge("70A00002")
        self.assertEqual(self.controller.on_badge("6A0E0002"), "launched")
        self.end_game()
        self.launcher.calls.clear()
        self.controller.on_badge("1EA00001")
        self.assertEqual(self.controller.on_badge("C0000001"), "launched")
        self.assertEqual(self.launcher.calls, [("snes", "/recalbox/share/roms/snes/Mario.smc")], "le jeu de Lea")
        self.assertEqual(self.players.current["uid"], "1EA00001")

    def test_sans_joueur_le_dernier_jeu(self):
        self.controller.on_badge("70A00002")
        self.controller.on_badge("6A0E0002")
        self.end_game()
        self.launcher.calls.clear()
        self.assertEqual(self.controller.on_badge("C0000001"), "launched")
        self.assertEqual(self.launcher.calls[0][0], "megadrive")

    def test_rien_a_reprendre(self):
        self.assertEqual(self.controller.on_badge("C0000001"), "nothing")
        self.assertIn("continue_none", [key for key, _values in self.screen.said])

    def test_garde_apres_redemarrage(self):
        self.controller.on_badge("6A0E0001")
        again = Players(self.home, wall=self.wall, clock=self.clock)
        self.assertEqual(again.last_game()["path"], "/recalbox/share/roms/snes/Mario.smc")


class TrophiesTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-trophies-")
        self.addCleanup(shutil.rmtree, self.home, True)

    @staticmethod
    def history(days, games_per_day=1, seconds=600):
        table = {}
        for number in range(days):
            day = "2026-11-%02d" % (1 + number)
            table[day] = {"sys%d|Jeu %d-%d" % (game % 4, number, game): seconds for game in range(games_per_day)}
        return table

    def test_mesures(self):
        values = trophies.measures(self.history(7, 2))
        self.assertEqual(values["streak"], 7)
        self.assertEqual(values["games"], 14)
        self.assertEqual(values["consoles"], 2)
        self.assertEqual(values["hours"], 2)
        broken = self.history(3)
        broken["2026-11-10"] = {"a|b": 600}
        self.assertEqual(trophies.measures(broken)["streak"], 3)

    def test_premiere_fois_silencieuse_puis_annonce(self):
        self.assertEqual(trophies.update(self.home, {"P1": self.history(3)}), [], "deja gagnes : pas d'annonce")
        self.assertIn("streak:3", trophies.read(self.home)["P1"])
        new = trophies.update(self.home, {"P1": self.history(7)})
        self.assertIn(("P1", "streak", 7), new)
        self.assertEqual(trophies.update(self.home, {"P1": self.history(7)}), [], "une seule fois")
        self.assertEqual(trophies.update(self.home, {"guest": self.history(9)}), [], "pas pour l'invite")

    def test_dernier(self):
        self.assertEqual(trophies.latest({"games:10": "2026-11-01", "streak:7": "2026-11-05", "streak:3": "2026-11-05"}),
                         ("streak", 7))
        self.assertIsNone(trophies.latest({}))


class HintLineTest(unittest.TestCase):
    def test_sequence(self):
        self.assertEqual(screen.hint_sequence("H", "", []), [("H", screen.TEXT, "card")])
        self.assertEqual([item[0] for item in screen.hint_sequence("H", "", ["a", "b"])], ["H", "a", "H", "b"])
        self.assertEqual([item[0] for item in screen.hint_sequence("H", "Note", ["a", "b"])],
                         ["H", "Note", "H", "a", "H", "Note", "H", "b"], "le mot du parent revient plus souvent")
        self.assertEqual(screen.hint_sequence("H", "Note", [])[1], ("Note", screen.NOTE_COLOUR, "note"))
        self.assertEqual(screen.hint_sequence("H", "", [("T", "trophy")])[1][2], "trophy")

    def test_rotation(self):
        self.assertEqual(screen.hint_slot(1, 123.0), (0, 1.0))
        self.assertEqual(screen.hint_slot(4, screen.HINT_S * 2 + 3)[0], 2)
        self.assertLess(screen.hint_slot(4, screen.HINT_S * 2 + 0.1)[1], 0.5, "fondu")

    def test_infos(self):
        home = tempfile.mkdtemp(prefix="rfid-infos-")
        self.addCleanup(shutil.rmtree, home, True)
        today = time.strftime("%Y-%m-%d")
        with open(os.path.join(home, "players.json"), "w", encoding="utf-8") as handle:
            json.dump({"usage": {}, "games": {"P1": {today: {"snes|Mario": 900, "snes|Zelda": 300}}}}, handle)
        infos = screen.screen_infos(home, {}, "fr", ("poweroff", "reboot"))
        self.assertIn(("START + SELECT : éteindre ou redémarrer", "info"), infos)
        self.assertIn(("Jeu de la semaine : Mario", "info"), infos)
        players = {"current": {"uid": "P1", "name": "Lea"}, "players": [{"uid": "P1", "name": "Lea"}]}
        with mock.patch.object(screen, "player_info", return_value={"uid": "P1", "name": "Lea"}):
            infos = screen.screen_infos(home, players, "fr", ())
        self.assertIn(("Jeu préféré de Lea : Mario", "info"), infos)

    def test_mot_du_parent(self):
        home = tempfile.mkdtemp(prefix="rfid-note-")
        self.addCleanup(shutil.rmtree, home, True)
        self.assertEqual(screen.read_note(home), "")
        with open(os.path.join(home, screen.NOTE_FILENAME), "w", encoding="utf-8") as handle:
            json.dump({"text": "Au lit à 20 h !"}, handle)
        self.assertEqual(screen.read_note(home), "Au lit à 20 h !")


class DimmerTest(unittest.TestCase):
    def test_reglage_comme_recalbox(self):
        folder = tempfile.mkdtemp(prefix="rfid-es-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "es_settings.cfg")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('<config>\n\t<int name="ScreenSaverTime" value="600000" />\n'
                         '\t<string name="ScreenSaverBehavior" value="black" />\n</config>\n')
        self.assertEqual(screen.recalbox_screensaver(path), (10.0, True))
        self.assertEqual(screen.dim_setting("recalbox", saver=lambda: (10.0, True)), (10.0, True))
        self.assertEqual(screen.dim_setting("15"), (15.0, False))
        self.assertEqual(screen.dim_setting("0"), (0.0, False))

    def test_s_assombrit_puis_se_rallume(self):
        clock = support.FakeClock(100.0)
        dimmer = screen.Dimmer("/nulle-part", clock=clock, read=lambda: (5.0, False))
        dimmer.step()
        clock.advance(299)
        dimmer.step()
        self.assertFalse(dimmer.dark)
        clock.advance(2)
        dimmer.step()
        clock.advance(2)
        dimmer.step()
        self.assertTrue(dimmer.dark)
        self.assertEqual(dimmer.alpha(), screen.DIM_ALPHA)
        dimmer.wake()
        clock.advance(0.5)
        dimmer.step()
        self.assertFalse(dimmer.dark)

    def test_desactive(self):
        clock = support.FakeClock(100.0)
        dimmer = screen.Dimmer("/nulle-part", clock=clock, read=lambda: (0.0, False))
        clock.advance(10 * 3600)
        dimmer.step()
        self.assertFalse(dimmer.dark)


if __name__ == "__main__":
    unittest.main()
