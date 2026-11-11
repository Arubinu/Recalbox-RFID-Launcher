"""Tests de la configuration."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support  # noqa: F401
from rfid.config import Config, ConfigError


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-config-")
        self.path = os.path.join(self.directory, "config.ini")

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_defauts_sans_fichier(self):
        config = Config(self.path)
        self.assertFalse(config.exists())
        self.assertEqual(config.get("rfid", "spi_device"), "/dev/spidev0.0")
        self.assertEqual(config.get_int("rfid", "reset_pin", -1), 25)
        self.assertEqual(config.get_int("button", "pin", 0), 17)
        self.assertTrue(config.get_bool("feedback", "sound", False))
        self.assertEqual(config.get_int("launch", "udp_port", 0), 1337)

    def test_creation_et_relcture(self):
        config = Config(self.path)
        self.assertTrue(config.create_default())
        self.assertTrue(os.path.isfile(self.path))
        self.assertFalse(config.create_default())  # ne doit pas ecraser

    def test_surcharge(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("[rfid]\nreset_pin = -1\nspi_speed_hz = 500000\n")
        config = Config(self.path)
        self.assertEqual(config.get_int("rfid", "reset_pin", 0), -1)
        self.assertEqual(config.get_int("rfid", "spi_speed_hz", 0), 500000)
        # Les cles absentes gardent leur defaut
        self.assertEqual(config.get("button", "pin"), "17")

    def test_valeurs_invalides(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("[rfid]\nspi_speed_hz = abc\n")
        config = Config(self.path)
        self.assertEqual(config.get_int("rfid", "spi_speed_hz", 1234), 1234)

    def test_section_list(self):
        config = Config(self.path)
        self.assertIn("rfid", config.section_list())
        self.assertIn("button", config.section_list())
        self.assertEqual(config.section("launch")["udp_port"], "1337")

    def test_fichier_invalide(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("ceci n'est pas un fichier ini\n")
        with self.assertRaises(ConfigError):
            Config(self.path)


if __name__ == "__main__":
    unittest.main()
