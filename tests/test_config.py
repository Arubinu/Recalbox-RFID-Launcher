"""Configuration tests."""

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
        self.assertFalse(config.create_default())  # must not overwrite

    def test_surcharge(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("[rfid]\nreset_pin = -1\nspi_speed_hz = 500000\n")
        config = Config(self.path)
        self.assertEqual(config.get_int("rfid", "reset_pin", 0), -1)
        self.assertEqual(config.get_int("rfid", "spi_speed_hz", 0), 500000)
        # Missing keys keep their default
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


class WriteValuesTest(unittest.TestCase):
    """Rewriting keys without losing the file comments."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-config-w-")
        self.path = os.path.join(self.directory, "config.ini")
        self.config = Config(self.path)
        self.config.create_default()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def lire(self) -> str:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_modifie_une_cle_existante(self):
        changees = self.config.write_values({"rfid.rearm_absent_ms": "2500"})
        self.assertEqual(changees, ["rfid.rearm_absent_ms"])
        self.assertEqual(self.config.get_int("rfid", "rearm_absent_ms", 0), 2500)
        self.assertEqual(Config(self.path).get_int("rfid", "rearm_absent_ms", 0), 2500)

    def test_conserve_les_commentaires(self):
        avant = self.lire()
        commentaires = [l for l in avant.split("\n") if l.strip().startswith("#")]
        self.config.write_values({"rfid.rearm_absent_ms": "2500"})
        apres = self.lire()
        restants = [l for l in apres.split("\n") if l.strip().startswith("#")]
        self.assertEqual(restants, commentaires)
        self.assertIn("rearm_absent_ms = 2500", apres)
        self.assertNotIn("rearm_absent_ms = 1200", apres)

    def test_ajoute_une_cle_absente_dans_sa_section(self):
        self.config.write_values({"launch.jamais_vue": "42"})
        self.assertEqual(self.config.get_int("launch", "jamais_vue", 0), 42)
        texte = self.lire()
        position_section = texte.index("[launch]")
        self.assertGreater(texte.index("jamais_vue = 42"), position_section)

    def test_cree_la_section_manquante(self):
        self.config.write_values({"nouvelle.cle": "valeur"})
        self.assertEqual(self.config.get("nouvelle", "cle"), "valeur")
        self.assertIn("[nouvelle]", self.lire())

    def test_plusieurs_valeurs_d_un_coup(self):
        changees = self.config.write_values(
            {"launch.stop_on_remove": "1", "feedback.sound": "0"}
        )
        self.assertEqual(sorted(changees), ["feedback.sound", "launch.stop_on_remove"])
        self.assertTrue(self.config.get_bool("launch", "stop_on_remove", False))
        self.assertFalse(self.config.get_bool("feedback", "sound", True))

    def test_cle_sans_section_refusee(self):
        with self.assertRaises(ConfigError):
            self.config.write_values({"rearm_absent_ms": "1"})

    def test_fichier_absent_cree(self):
        os.remove(self.path)
        self.config.write_values({"rfid.rearm_absent_ms": "900"})
        self.assertTrue(os.path.isfile(self.path))
        self.assertEqual(Config(self.path).get_int("rfid", "rearm_absent_ms", 0), 900)

    def test_pas_de_fichier_temporaire_residuel(self):
        self.config.write_values({"rfid.rearm_absent_ms": "900"})
        self.assertFalse(os.path.exists(self.path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
