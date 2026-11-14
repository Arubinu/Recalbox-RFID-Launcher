"""Push button tests (simulated GPIO backend, simulated clock)."""

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

    def assert_short(self, button):
        """The short press comes once the double press delay passed."""
        self.assertIsNone(button.poll(), "attend un eventuel second appui")
        self.clock.advance(0.2)
        self.assertIsNone(button.poll())
        self.clock.advance(0.25)
        self.assertEqual(button.poll(), "short")
        self.assertIsNone(button.poll())

    def tap(self, button, duration=0.08):
        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        button.poll()
        self.clock.advance(duration)
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.02)
        return button.poll()

    def test_double_appui(self):
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()
        self.assertIsNone(self.tap(button))
        self.clock.advance(0.1)
        self.assertIsNone(button.poll())
        self.assertEqual(self.tap(button), "double")
        self.clock.advance(1.0)
        self.assertIsNone(button.poll(), "pas d'appui court en plus")

    def test_second_appui_trop_tard(self):
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()
        self.assertIsNone(self.tap(button))
        self.clock.advance(0.45)
        self.assertEqual(button.poll(), "short")
        self.assertIsNone(self.tap(button))
        self.clock.advance(0.45)
        self.assertEqual(button.poll(), "short")

    def test_second_appui_maintenu(self):
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()
        self.assertIsNone(self.tap(button))
        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        button.poll()
        self.clock.advance(0.35)
        self.assertEqual(button.poll(), "hold")
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(1.0)
        self.assertIsNone(button.poll())

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

        self.gpio.levels[17] = 0  # press
        self.assertIsNone(button.poll())
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())   # press confirmed: no gesture yet

        self.gpio.levels[17] = 1  # relachement
        self.assertIsNone(button.poll())
        self.clock.advance(0.02)
        self.assert_short(button)

    def test_appui_maintenu_valide_sans_relacher(self):
        """As soon as the press reaches 3 s, the validation is sent, finger still down."""
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()

        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())
        self.clock.advance(0.20)      # still below hold_press_s (0.30)
        self.assertIsNone(button.poll())
        self.clock.advance(0.12)      # past hold_press_s, still pressed
        self.assertEqual(button.poll(), "hold")
        # the press goes on: nothing else must be sent
        self.clock.advance(0.50)
        self.assertIsNone(button.poll())

        self.gpio.levels[17] = 1      # release: no second gesture
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
        self.assert_short(button)

    def test_appui_de_deux_secondes_ne_supprime_plus(self):
        """There is no long gesture any more: a 2 s press stays a simple press."""
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()

        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        button.poll()
        self.clock.advance(0.25)  # shorter than hold_press_s (0.30)
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.02)
        self.assert_short(button)

    def test_rebond_ignore(self):
        button = self.make_button()
        self.clock.advance(0.02)
        button.poll()

        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.002)  # bounce: state not stable yet
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.002)
        self.gpio.levels[17] = 0
        button.poll()
        self.clock.advance(0.02)
        self.assertIsNone(button.poll())  # press confirmed: the gesture comes on release
        self.gpio.levels[17] = 1
        button.poll()
        self.clock.advance(0.02)
        self.assert_short(button)

    def test_is_pressed(self):
        button = self.make_button()
        self.assertFalse(button.is_pressed())
        self.gpio.levels[17] = 0
        self.assertTrue(button.is_pressed())


if __name__ == "__main__":
    unittest.main()
