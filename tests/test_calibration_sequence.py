"""Automatic tuning sequence tests (service, simulated reader)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401
from rfid import calibration
from rfid import daemon as daemon_module
from rfid.config import Config


class FakeChip:
    """Puce RC522 simulee : UID, reponses REQA/WUPA, version."""

    def __init__(self, uid=b"\x36\x00\x00\x00"):
        self.uid = uid
        self.version = 0x92
        self.present = True
        self.readable = True
        self.speed = None
        self.closed = False

    def begin(self):
        return self.version

    def read_version(self):
        return self.version

    def read_uid(self, trace=None):
        return self.uid if self.readable else None

    def request(self, mode=0x26):
        return b"\x04\x00" if self.present else None

    def reset_field(self):
        pass

    def close(self):
        self.closed = True


class FakeReader:
    def __init__(self, chip):
        self.rc522 = chip
        self.cooldown_s = 2.5
        self.version = 0x92
        self.closed = False

    def start(self):
        return 0x92

    def tag_present(self):
        return self.rc522.present

    def close(self):
        self.closed = True


class CalibrationSequenceTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-calib-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.config = Config(os.path.join(self.home, "config.ini"))
        self.config.create_default()

        self.service = daemon_module.Service.__new__(daemon_module.Service)
        self.service.home = self.home
        self.service.log = None
        self.service.cfg = self.config
        self.service.gpio = None
        self.service.rearm_absent_ms = 1200.0
        self.service._reader_test = None
        self.service._calibration = None
        self.service._calibration_signature = None
        self.service._active_uid = None
        self.every_speed_fails = False
        self.chip = FakeChip()
        self.service.reader = FakeReader(self.chip)
        self.service.controller = mock.Mock()

        self.now = 100.0
        self.patch_time = mock.patch.object(
            daemon_module.time, "monotonic", side_effect=lambda: self.now
        )
        self.patch_time.start()
        self.addCleanup(self.patch_time.stop)

        self.patch_spi = mock.patch.object(
            daemon_module, "open_spi", side_effect=self.fake_open_spi
        )
        self.patch_spi.start()
        self.addCleanup(self.patch_spi.stop)
        self.patch_chip = mock.patch.object(
            daemon_module, "Rc522", side_effect=self.fake_rc522
        )
        self.patch_chip.start()
        self.addCleanup(self.patch_chip.stop)
        self.patch_reader = mock.patch.object(
            daemon_module, "build_reader", side_effect=lambda *a, **k: FakeReader(self.chip)
        )
        self.patch_reader.start()
        self.addCleanup(self.patch_reader.stop)

    # ------------------------------------------------------------ outillage
    def fake_open_spi(self, device, speed):
        return SimpleNamespace(speed=speed, backend="fake", close=lambda: None)

    def fake_rc522(self, spi, log=None):
        chip = FakeChip()
        chip.speed = spi.speed
        if self.every_speed_fails or spi.speed >= 8000000:
            # Bus too fast: the register cannot be read (0x00/0xFF).
            chip.version = 0x00
        return chip

    def step(self, fois=1, pas=0.02):
        for _ in range(fois):
            self.now += pas
            self.service._calibration_step()

    def etat(self):
        with open(os.path.join(self.home, "calibration.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def config_texte(self):
        with open(self.config.path, encoding="utf-8") as handle:
            return handle.read()

    def lance(self):
        self.service._start_calibration()
        self.assertIsNotNone(self.service._calibration)

    def deroule_complet(self):
        """Plays the whole sequence with a cooperative badge."""
        self.lance()
        self.step()                      # speed -> waiting for the badge
        self.chip.present = True
        self.step()                      # lectures
        self.step()                      # presence
        self.chip.present = False
        self.step(fois=5)                # retrait confirme
        self.chip.present = True
        self.step(fois=2)                # repose + lecture -> fin

    # ------------------------------------------------------------- mesures
    def test_sequence_complete_applique_les_reglages(self):
        self.deroule_complet()
        etat = self.etat()
        self.assertEqual(etat["phase"], "done")
        self.assertTrue(etat["finished"])
        self.assertEqual(etat["error"], "")
        mesures = etat["measures"]
        self.assertEqual(mesures["best_speed"], 4000000)
        self.assertEqual(mesures["uids"], ["36000000"])
        self.assertEqual(mesures["reads"], 20)
        self.assertEqual(mesures["reqa_ok"], 20)
        self.assertEqual(mesures["wupa_ok"], 20)
        self.assertIsNotNone(mesures["absence_ms"])
        self.assertIsNotNone(mesures["reinsert_ms"])
        texte = self.config_texte()
        self.assertIn("spi_speed_hz = 4000000", texte)
        self.assertIn("poll_interval_ms = 60", texte)
        self.assertIn("rearm_absent_ms = 1000", texte)
        self.assertEqual(Config(self.config.path).get_int("rfid", "spi_speed_hz", 0), 4000000)
        self.assertEqual(self.service.rearm_absent_ms, 1000.0)

    def test_les_commentaires_du_fichier_sont_gardes(self):
        self.deroule_complet()
        self.assertIn("Recalbox RFID Launcher", self.config_texte())
        self.assertGreater(self.config_texte().count("#"), 20)

    def test_les_anciennes_valeurs_sont_sauvegardees(self):
        self.deroule_complet()
        chemin = os.path.join(self.home, "calibration-backup.json")
        with open(chemin, encoding="utf-8") as handle:
            sauvegarde = json.load(handle)
        self.assertEqual(sauvegarde["values"]["rfid.spi_speed_hz"], "1000000")
        self.assertEqual(sauvegarde["values"]["rfid.poll_interval_ms"], "150")
        self.assertTrue(sauvegarde["at"])
        applied = self.etat()["applied"]
        self.assertEqual(applied["rfid.spi_speed_hz"], ["1000000", "4000000"])

    def test_les_etapes_sont_publiees(self):
        self.lance()
        etat = self.etat()
        self.assertEqual(etat["phase"], "speed")
        self.assertEqual(etat["total"], 5)
        self.assertEqual(etat["defaults"], calibration.DEFAULTS)
        self.step()
        etat = self.etat()
        self.assertEqual(etat["phase"], "read")
        self.assertEqual(etat["instruct"], "pose_badge")
        self.step()
        self.assertEqual(self.etat()["instruct"], "hold_badge")
        self.step()
        self.assertEqual(self.etat()["instruct"], "remove_badge")

    def test_vitesse_la_plus_rapide_qui_marche(self):
        self.lance()
        self.step()
        speeds = self.etat()["measures"]["speeds"]
        self.assertEqual(speeds, [[8000000, 0], [4000000, 1]])

    def test_aucune_vitesse_ne_marche(self):
        self.every_speed_fails = True   # even the slowest speed fails
        self.lance()
        self.step()
        etat = self.etat()
        self.assertEqual(etat["phase"], "error")
        self.assertEqual(etat["error"], "spi_failed")
        self.assertIn("spi_speed_hz = 1000000", self.config_texte())

    def test_le_badge_pose_a_la_fin_n_agit_pas(self):
        self.deroule_complet()
        self.assertTrue(self.service._adopt_next_read)
        self.assertGreater(self.service._adopt_until, self.now)
        # The loop sees the badge placed again: it must not start anything.
        self.service._active_uid = None
        self.service._badge_seen("36000000")
        self.service.controller.on_badge.assert_not_called()
        self.assertEqual(self.service._active_uid, "36000000")

    def test_l_adoption_est_arnee_meme_apres_une_annulation(self):
        self.lance()
        self.step()
        self.service._finish_calibration("cancelled")
        self.assertTrue(self.service._adopt_next_read)
        self.assertGreater(self.service._adopt_until, self.now)

    def test_l_adoption_est_arnee_apres_un_echec(self):
        self.lance()
        self.step()
        self.service._finish_calibration("badge_unreadable")
        self.assertTrue(self.service._adopt_next_read)
        self.assertGreater(self.service._adopt_until, self.now)

    # ------------------------------------------------------------- echecs
    def test_aucun_badge_pose_ne_change_rien(self):
        self.lance()
        self.step()
        self.chip.present = False
        self.step(pas=61.0)           # past the 60 s delay
        etat = self.etat()
        self.assertEqual(etat["phase"], "error")
        self.assertEqual(etat["error"], "timeout_pose")
        self.assertEqual(self.config_texte().count("poll_interval_ms = 150"), 1)

    def test_badge_illisible_ne_change_rien(self):
        self.lance()
        self.step()
        self.chip.readable = False
        self.step()
        etat = self.etat()
        self.assertEqual(etat["error"], "badge_unreadable")
        self.assertIn("spi_speed_hz = 1000000", self.config_texte())

    def test_lecteur_absent(self):
        self.service.reader = None
        self.lance()
        self.step()
        etat = self.etat()
        self.assertEqual(etat["error"], "no_reader")

    def test_annulation(self):
        self.lance()
        self.step()
        self.service._finish_calibration("cancelled")
        etat = self.etat()
        self.assertEqual(etat["phase"], "error")
        self.assertEqual(etat["error"], "cancelled")
        self.assertIn("rearm_absent_ms = 1200", self.config_texte())

    def test_retrait_jamais_effectue(self):
        self.lance()
        self.step()
        self.chip.present = True
        self.step()
        self.step()                   # presence
        self.chip.present = True      # the badge stays on the reader
        self.step(pas=61.0)
        self.assertEqual(self.etat()["error"], "timeout_remove")

    def test_repose_jamais_effectue(self):
        self.lance()
        self.step()
        self.chip.present = True
        self.step()
        self.step()
        self.chip.present = False
        self.step(fois=5)
        self.step(pas=61.0)           # never placed again
        self.assertEqual(self.etat()["error"], "timeout_replace")

    # --------------------------------------------------------- repli / reset
    def test_repli_si_la_vitesse_mesuree_ne_tient_pas(self):
        self.lance()
        self.step()
        # The reader reopens badly at the chosen speed: back to 1 MHz.
        self.chip.version = 0x00
        self.service._calibration = None
        applique = self.service._apply_calibration_settings(
            {"rfid.spi_speed_hz": "4000000", "rfid.poll_interval_ms": "80",
             "rfid.rearm_absent_ms": "1500"}
        )
        self.assertEqual(applique["rfid.spi_speed_hz"], ["1000000", "1000000"])
        self.assertIn("spi_speed_hz = 1000000", self.config_texte())

    def test_reinitialisation(self):
        self.config.write_values(
            {"rfid.spi_speed_hz": "4000000", "rfid.poll_interval_ms": "80",
             "rfid.rearm_absent_ms": "2500"}
        )
        self.service.rearm_absent_ms = 2500.0
        self.service._reset_calibration_settings()
        texte = self.config_texte()
        self.assertIn("spi_speed_hz = 1000000", texte)
        self.assertIn("poll_interval_ms = 150", texte)
        self.assertIn("rearm_absent_ms = 1200", texte)
        etat = self.etat()
        self.assertEqual(etat["phase"], "reset")
        self.assertEqual(etat["applied"]["rfid.poll_interval_ms"], ["80", "150"])
        self.assertEqual(self.service.rearm_absent_ms, 1200.0)


if __name__ == "__main__":
    unittest.main()
