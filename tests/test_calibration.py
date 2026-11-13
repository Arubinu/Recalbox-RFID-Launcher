"""Automatic reader tuning tests (computations, no hardware)."""

from __future__ import annotations

import unittest

import support  # noqa: F401
from rfid import calibration


class SettingsTest(unittest.TestCase):
    def test_valeurs_typiques(self):
        reglages = calibration.settings_from(
            {"best_speed": 4000000, "read_ms": 47.2, "absence_ms": 1620}
        )
        self.assertEqual(reglages["rfid.spi_speed_hz"], "4000000")
        self.assertEqual(reglages["rfid.poll_interval_ms"], "77")
        self.assertEqual(reglages["rfid.rearm_absent_ms"], "2430")

    def test_cadence_bornee(self):
        self.assertEqual(calibration.poll_interval_ms(1), calibration.POLL_MIN_MS)
        self.assertEqual(calibration.poll_interval_ms(5000), calibration.POLL_MAX_MS)
        self.assertEqual(calibration.poll_interval_ms(None), calibration.POLL_MIN_MS)

    def test_delai_d_absence_borne(self):
        self.assertEqual(calibration.absence_ms(10), calibration.ABSENCE_MIN_MS)
        self.assertEqual(calibration.absence_ms(99999), calibration.ABSENCE_MAX_MS)
        self.assertEqual(calibration.absence_ms(1000), 1500)

    def test_vitesse_inconnue_retombe_sur_le_defaut(self):
        reglages = calibration.settings_from({"best_speed": 12345678})
        self.assertEqual(reglages["rfid.spi_speed_hz"], str(calibration.SPEED_FALLBACK))
        self.assertEqual(calibration.settings_from({})["rfid.spi_speed_hz"], "1000000")

    def test_mesures_absentes(self):
        reglages = calibration.settings_from(None)
        self.assertEqual(reglages["rfid.poll_interval_ms"], str(calibration.POLL_MIN_MS))
        self.assertEqual(reglages["rfid.rearm_absent_ms"], str(calibration.ABSENCE_MIN_MS))

    def test_valeurs_non_numeriques(self):
        reglages = calibration.settings_from({"read_ms": "beaucoup", "absence_ms": "?"})
        self.assertEqual(reglages["rfid.poll_interval_ms"], str(calibration.POLL_MIN_MS))
        self.assertEqual(reglages["rfid.rearm_absent_ms"], str(calibration.ABSENCE_MIN_MS))

    def test_les_defauts_sont_les_valeurs_livrees(self):
        self.assertEqual(calibration.DEFAULTS["rfid.spi_speed_hz"], "1000000")
        self.assertEqual(calibration.DEFAULTS["rfid.poll_interval_ms"], "150")
        self.assertEqual(calibration.DEFAULTS["rfid.rearm_absent_ms"], "1200")
        self.assertEqual(set(calibration.DEFAULTS), set(calibration.settings_from({})))


class LabelsTest(unittest.TestCase):
    def test_vitesses_lisibles(self):
        self.assertEqual(calibration.speed_label(4000000), "4 MHz")
        self.assertEqual(calibration.speed_label(500000), "500 kHz")
        self.assertEqual(calibration.speed_label(1000000), "1 MHz")
        self.assertEqual(calibration.speed_label(None), "?")

    def test_verdict_de_presence(self):
        self.assertEqual(calibration.presence_verdict({"reqa_ok": 20, "wupa_ok": 20}), "reqa+wupa")
        self.assertEqual(calibration.presence_verdict({"reqa_ok": 20, "wupa_ok": 0}), "reqa")
        self.assertEqual(calibration.presence_verdict({"reqa_ok": 0, "wupa_ok": 20}), "wupa")
        self.assertEqual(calibration.presence_verdict({}), "muet")

    def test_erreurs_parlees(self):
        self.assertIn("lecteur", calibration.error_text("no_reader"))
        self.assertEqual(calibration.error_text("inconnu"), "inconnu")


if __name__ == "__main__":
    unittest.main()
