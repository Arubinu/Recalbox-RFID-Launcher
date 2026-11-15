"""Turning off and restarting: countdowns, power menu, nobody playing."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401
from rfid import power
from rfid import screen


class Clock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self):
        return self.now


class PowerTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rfid-power-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.state = os.path.join(self.dir, "state.json")
        self.request = os.path.join(self.dir, "request.json")
        self.wall = Clock()
        self.ran = []
        self.prepared = []
        self.ctl = power.Power(run=self.ran.append, wall=self.wall, state_path=self.state,
                               request_path=self.request, prepare=self.prepared.append)

    def ask(self, action, age=0.0):
        with open(self.request, "w", encoding="utf-8") as handle:
            json.dump({"action": action, "at": self.wall() - age}, handle)


class PowerTest(PowerTestCase):
    def test_carte_compte_a_rebours_puis_extinction(self):
        self.ctl.begin("poweroff", "card", uid="AA")
        state = power.read_state(self.state, wall=self.wall)
        self.assertEqual(state["source"], "card")
        self.assertEqual(state["until"], self.wall() + 10)
        self.wall.now += 9
        self.assertEqual(self.ctl.step("AA"), "")
        self.wall.now += 1
        self.assertEqual(self.ctl.step("AA"), "poweroff")
        self.assertEqual(self.ran, ["poweroff"])
        self.assertEqual(self.prepared, ["poweroff"], "le jeu en cours est quitte avant")
        self.assertFalse(os.path.exists(self.state))

    def test_retirer_la_carte_annule(self):
        self.ctl.begin("poweroff", "card", uid="AA")
        self.wall.now += 3
        self.assertEqual(self.ctl.step(None), "")
        self.assertIsNone(self.ctl.pending)
        self.assertIsNone(power.read_state(self.state, wall=self.wall))
        self.wall.now += 20
        self.ctl.step(None)
        self.assertEqual(self.ran, [])

    def test_menu_et_annulation(self):
        self.ctl.begin("reboot", "menu")
        self.assertEqual(self.ctl.pending["until"], self.wall() + 5)
        self.assertTrue(self.ctl.cancel("manette"))
        self.assertFalse(self.ctl.cancel())
        self.wall.now += 10
        self.ctl.step()
        self.assertEqual(self.ran, [])

    def test_demandes_de_l_ecran(self):
        self.ask("reboot")
        self.assertEqual(self.ctl.take_request(), "reboot")
        self.assertIsNone(self.ctl.take_request(), "lue une seule fois")
        self.ask("poweroff", age=60)
        self.assertIsNone(self.ctl.take_request(), "une vieille demande est ignoree")

    def test_choix_du_menu(self):
        self.assertEqual(power.menu_actions("both"), ("poweroff", "reboot"))
        self.assertEqual(power.menu_actions("poweroff"), ("poweroff",))
        self.assertEqual(power.menu_actions("off"), ())
        self.assertEqual(power.menu_actions("n'importe"), ("poweroff", "reboot"))


ES_INPUT = """<?xml version="1.0"?>
<inputList>
  <inputConfig type="keyboard" deviceName="Keyboard" deviceGUID="-1">
    <input name="start" type="key" id="13" value="1"/>
  </inputConfig>
  <inputConfig type="joystick" deviceName="8BitDo SN30" deviceGUID="0300ABCD">
    <input name="start" type="button" id="11" value="1"/>
    <input name="select" type="button" id="10" value="1"/>
    <input name="hotkey" type="button" id="10" value="1"/>
    <input name="a" type="button" id="0" value="1"/>
    <input name="up" type="hat" id="0" value="1"/>
    <input name="down" type="hat" id="0" value="4"/>
    <input name="joystick1up" type="axis" id="1" value="-1"/>
  </inputConfig>
</inputList>
"""


class PadSettingsTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp(prefix="rfid-pads-")
        self.addCleanup(shutil.rmtree, folder, True)
        self.path = os.path.join(folder, "es_input.cfg")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(ES_INPUT)

    def test_reglages_de_recalbox(self):
        settings = screen.pad_settings(self.path)
        self.assertEqual(len(settings), 1, "le clavier est ignore")
        inputs = screen.pad_inputs(settings, "0300abcd", "")
        self.assertEqual(screen.button_of(inputs, "start"), 11)
        self.assertEqual(screen.button_of(inputs, "select"), 10)
        self.assertIs(screen.pad_inputs(settings, "", "8BitDo SN30"), inputs, "trouve aussi par son nom")
        self.assertEqual(screen.pad_inputs(settings, "ffff", "Autre"), {})
        settings[0]["guid"] = "03004d2a1f08000001e4000010010000"
        self.assertIs(screen.pad_inputs(settings, "030000001f08000001e4000010010000", ""), settings[0]["inputs"],
                      "la somme du nom (SDL recent) est ignoree")
        self.assertEqual(screen.pad_settings(self.path + ".absent"), [])

    def test_noms_des_evenements(self):
        inputs = screen.pad_inputs(screen.pad_settings(self.path), "0300abcd", "")
        self.assertEqual(screen.event_names("button", 10, 1, inputs), {"select", "hotkey"})
        self.assertEqual(screen.event_names("hat", 0, (0, 1), inputs), {"up"})
        self.assertEqual(screen.event_names("hat", 0, (0, -1), inputs), {"down"})
        self.assertEqual(screen.event_names("axis", 1, -1, inputs), {"up", "joystick1up"})
        self.assertEqual(screen.event_names("axis", 1, 1, inputs), {"down"}, "le stick gauche aussi")
        self.assertEqual(screen.event_names("button", 3, 1, {}), {"a"}, "manette inconnue : un bouton valide")


class FakePads:
    """Events are SimpleNamespace(type, names, combo)."""

    pg = SimpleNamespace(JOYBUTTONDOWN=1, JOYHATMOTION=2, JOYAXISMOTION=3)

    def names(self, event):
        return set(event.names)

    def combo(self, event):
        return event.combo


def press(*names, combo=False):
    return SimpleNamespace(type=1, names=names, combo=combo)


def hat(*names):
    return SimpleNamespace(type=2, names=names, combo=False)


class PowerControlTest(unittest.TestCase):
    def make(self, menu="both", state=None):
        self.sent = []
        self.state = state
        self.clock = Clock()
        with mock.patch.object(screen, "setting", return_value=menu):
            control = screen.PowerControl("/nulle-part", "fr", FakePads(), clock=self.clock, wall=Clock(),
                                          send=self.sent.append, read=lambda: self.state)
            control.refresh_actions()
        return control

    def test_start_select_ouvre_le_menu(self):
        control = self.make()
        self.assertFalse(control.handle(press("start")))
        self.assertTrue(control.handle(press("start", combo=True)))
        self.assertEqual(control.menu.items, ["poweroff", "reboot", "cancel"])
        self.assertTrue(control.handle(hat("down")))
        self.assertEqual(control.menu.choice(), "reboot")
        self.clock.now += 1
        self.assertTrue(control.handle(press("a")))
        self.assertIsNone(control.menu)
        self.assertEqual(self.sent[-1], "reboot")

    def test_annuler_ne_demande_rien(self):
        control = self.make(menu="poweroff")
        control.handle(press("select", combo=True))
        self.assertEqual(control.menu.items, ["poweroff", "cancel"])
        control.handle(hat("up"))
        self.clock.now += 1
        control.handle(press("b"))
        self.assertNotIn("poweroff", self.sent)

    def test_start_et_select_ensemble_ne_valident_pas(self):
        """The two presses of the pair arrive together: the second one must not turn off."""
        control = self.make()
        for _ in range(2):
            self.clock.now += 5
            self.assertTrue(control.handle(press("select", combo=True)))  # both already held
            self.assertTrue(control.handle(press("start", combo=True)))
            self.assertTrue(control.handle(press("a")), "pression juste apres l'ouverture : ignoree")
            self.assertIsNotNone(control.menu)
            self.clock.now += 1
            self.assertTrue(control.handle(press("start")))
            self.assertIsNotNone(control.menu, "START ne valide pas")
            control.handle(hat("up"))
            self.assertEqual(control.menu.choice(), "cancel")
            control.handle(press("a"))
            self.assertIsNone(control.menu)
        self.assertNotIn("poweroff", self.sent)
        self.assertNotIn("reboot", self.sent)

    def test_menu_desactive_ou_jeu_montre(self):
        control = self.make(menu="off")
        self.assertFalse(control.handle(press("start", combo=True)))
        self.assertIsNone(control.menu)
        control = self.make()
        self.assertFalse(control.handle(press("start", combo=True), busy=True))
        self.assertIsNone(control.menu)

    def test_un_bouton_annule_le_compte_a_rebours(self):
        control = self.make(state={"action": "poweroff", "until": 1005.0, "source": "idle"})
        control.poll()
        self.assertTrue(control.handle(press("x")))
        self.assertEqual(self.sent, ["cancel"])
        title, detail = control.view()[1:3]
        self.assertEqual(title, "Extinction dans 5 s")
        self.assertIn("Personne ne joue", detail)

    def test_le_menu_se_ferme_seul(self):
        control = self.make()
        control.handle(press("start", combo=True))
        self.clock.now += screen.PowerMenu.TIMEOUT_S
        control.poll()
        self.assertIsNone(control.menu)

    def test_activite_signalee_au_service(self):
        control = self.make()
        control.handle(press("a"))
        control.handle(press("a"))
        self.assertEqual(self.sent, ["activity"], "une fois toutes les dix secondes")
        self.clock.now += control.ACTIVITY_S
        control.handle(press("a"))
        self.assertEqual(self.sent, ["activity", "activity"])


class ServiceTestCase(PowerTestCase):
    def service(self, config=""):
        from rfid import daemon as _daemon
        from rfid.config import Config

        path = os.path.join(self.dir, "config.ini")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(config)
        service = _daemon.Service.__new__(_daemon.Service)
        service.home = self.dir
        service.cfg = Config(path)
        service.log = mock.Mock()
        service.screen = mock.Mock()
        service.controller = mock.Mock()
        service.controller.game_running.return_value = False
        service.reader_mode = SimpleNamespace(state="screen", pending=None)
        service.power_ctl = self.ctl
        service._active_uid = None
        service.last_uid = None
        service._idle_since = time.monotonic()
        return service


class ServicePowerTest(ServiceTestCase):
    def test_carte_eteindre_avec_compte_a_rebours(self):
        service = self.service()
        service.last_uid = service._active_uid = "CC"
        service._power_off()
        self.assertEqual(self.ctl.pending["source"], "card")
        service.screen.say.assert_not_called()  # the reader screen shows the countdown
        service._active_uid = None
        service._power_step()
        self.assertIsNone(self.ctl.pending)
        service.screen.say.assert_called_with("power_cancelled")

    def test_carte_eteindre_pendant_un_jeu(self):
        service = self.service()
        service.reader_mode.state = "game"
        service.last_uid = "CC"
        service._power_off()
        service.screen.say.assert_called_with("power_card", n=10)

    def test_carte_eteindre_sans_compte_a_rebours(self):
        service = self.service("[display]\npoweroff_countdown = 0\n")
        service._power_off()
        self.assertEqual(self.ran, ["poweroff"])

    def test_menu_de_l_ecran(self):
        service = self.service()
        self.ask("reboot")
        service._power_step()
        self.assertEqual(self.ctl.pending["action"], "reboot")
        self.ask("cancel")
        service._power_step()
        self.assertIsNone(self.ctl.pending)
        service.screen.say.assert_called_with("reboot_cancelled")

    def test_menu_refuse(self):
        service = self.service("[display]\npower_menu = poweroff\n")
        self.ask("reboot")
        service._power_step()
        self.assertIsNone(self.ctl.pending)
        service.controller.game_running.return_value = True
        self.ask("poweroff")
        service._power_step()
        self.assertIsNone(self.ctl.pending, "pas pendant un jeu")

    def test_personne_ne_joue(self):
        service = self.service("[display]\nidle_off_min = 15\n")
        service._idle_since = time.monotonic() - 14 * 60
        service._power_step()
        self.assertIsNone(self.ctl.pending)
        service._idle_since = time.monotonic() - 15 * 60
        service._power_step()
        self.assertEqual(self.ctl.pending["source"], "idle")
        self.wall.now += 30
        service._power_step()
        self.assertEqual(self.ran, ["poweroff"])

    def test_personne_ne_joue_desactive_ou_carte_posee(self):
        service = self.service()
        service._idle_since = time.monotonic() - 3600
        service._power_step()
        self.assertIsNone(self.ctl.pending, "0 = jamais")
        service = self.service("[display]\nidle_off_min = 1\n")
        service._active_uid = "AA"
        service._idle_since = time.monotonic() - 3600
        service._power_step()
        self.assertIsNone(self.ctl.pending, "une carte posee")
        service._active_uid = None
        service.reader_mode.state = "recalbox"
        service._power_step()
        self.assertIsNone(self.ctl.pending, "seulement sur l'ecran du lecteur")


if __name__ == "__main__":
    unittest.main()
