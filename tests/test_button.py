"""Tests du bouton poussoir (backend GPIO simule, horloge simulee)."""

from __future__ import annotations

import unittest

import support
from rfid.drivers.button import Button


class ButtonTest(unittest.TestCase):
    def setUp(self):
        self.gpio = support.FakeGpio()
        self.clock = support.FakeClock()

    def make_button(self, **kwargs):
        return Button(
            self.gpio,
            17,
            debounce_s=0.01,
            hold_press_s=0.30,
            clock=self.clock,
            **kwargs
        )

    def test_aucun_gestionnaire(self):
        button = Button(None, 0)
        self.assertFalse(button.available)
        self.assertIsNone(button.poll())

    def test_repos(self):
        button = self.make_button()
        self.assertTrue(button.available)
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())

    def test_appui_court(self):
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()  # etat stable

        self.gpio.levels[17] = 0  # appui
        self.assertIsNone(button.poll())
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())   # appui confirme : pas encore de geste

        self.gpio.levels[17] = 1  # relachement
        self.assertIsNone(button.poll())
        self.clock.advance(0.02)
        self.assertEqual(button.poll(), "short")

    def test_appui_maintenu_valide_sans_relacher(self):
        """Des que l'appui atteint 3 s, la validation part, doigt encore pose."""
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()

        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())
        self.clock.advance(0.20)      # encore sous hold_press_s (0.30)
        self.assertIsNone(button.poll())
        self.clock.advance(0.12)      # depasse hold_press_s, toujours appuye
        self.assertEqual(button.poll(), "hold")
        # l'appui continue : plus rien ne doit partir
        self.clock.advance(0.50)
        self.assertIsNone(button.poll())

        self.gpio.levels[17] = 1      # relachement : pas de second geste
        button.poll()
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())

    def test_relachement_avant_3_s_associe(self):
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()

        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        button.poll()
        self.clock.advance(0.10)
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.02)
        self.assertEqual(button.poll(), "short")

    def test_appui_de_deux_secondes_ne_supprime_plus(self):
        """Il n'y a plus de geste long : un appui de 2 s reste un simple appui."""
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()

        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        button.poll()
        self.clock.advance(0.25)  # plus court que hold_press_s (0.30)
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.02)
        self.assertEqual(button.poll(), "short")

    def test_rebond_ignore(self):
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()

        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.002)  # rebond : etat pas encore stable
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.002)
        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())  # appui confirme : le geste viendra au relachement
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.02)
        self.assertEqual(button.poll(), "short")

    def test_is_pressed(self):
        button = self.make_button()
        self.assertFalse(button.is_pressed())
        self.gpio.levels[17] = 0
        self.assertTrue(button.is_pressed())


if __name__ == "__main__":
    unittest.main()
