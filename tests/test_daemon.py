"""Tests des utilitaires du service (fichiers d'etat, verrou)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support  # noqa: F401
from rfid.daemon import (
    acquire_lock,
    pid_path,
    read_pid,
    read_status,
    release_lock,
    write_json_atomic,
)


class DaemonHelpersTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-daemon-")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_pid_absent(self):
        self.assertEqual(read_pid(self.home), 0)

    def test_pid_present(self):
        with open(pid_path(self.home), "w", encoding="ascii") as handle:
            handle.write("12345\n")
        self.assertEqual(read_pid(self.home), 12345)

    def test_pid_invalide(self):
        with open(pid_path(self.home), "w", encoding="ascii") as handle:
            handle.write("pas un nombre")
        self.assertEqual(read_pid(self.home), 0)

    def test_ecriture_atomique_et_lecture(self):
        write_json_atomic(os.path.join(self.home, "status.json"), {"pid": 42, "tags": 3})
        status = read_status(self.home)
        self.assertEqual(status["pid"], 42)
        self.assertEqual(status["tags"], 3)

    def test_status_absent(self):
        self.assertIsNone(read_status(self.home))

    def test_status_corrompu(self):
        with open(os.path.join(self.home, "status.json"), "w", encoding="utf-8") as handle:
            handle.write("{ coupe")
        self.assertIsNone(read_status(self.home))

    def test_verrou(self):
        lock = acquire_lock(os.path.join(self.home, "test.lock"))
        if lock == -1:
            self.skipTest("verrou non disponible sur cette plateforme")
        try:
            self.assertNotEqual(lock, 0)
        finally:
            release_lock(lock)


if __name__ == "__main__":
    unittest.main()

class ReleaseGestureTest(unittest.TestCase):
    """Les gestes sont traites au relachement, jamais au contact."""

    def setUp(self):
        from unittest import mock as _mock

        from rfid import daemon as _daemon

        self._daemon = _daemon
        self.service = _daemon.Service.__new__(_daemon.Service)
        self.service.home = tempfile.mkdtemp(prefix="rfid-gesture-")
        self.service.log = None
        self.service._press_started_at = None
        self.service._active_uid = "A1B2C3D4"
        self.service._absent_since = None
        self.armements = []
        self.service.controller = _mock.Mock()
        self.service.controller.on_button = lambda geste: self.armements.append(geste)

    def tearDown(self):
        shutil.rmtree(self.service.home, ignore_errors=True)

    def test_appui_court_arme_a_l_association(self):
        self.service._handle_gesture("short")
        self.assertEqual(self.armements, ["short"])

    def test_geste_long_ignore(self):
        """Le geste "long" n'existe plus : il ne doit rien armer du tout."""
        self.service._handle_gesture("long")
        self.assertEqual(self.armements, [])

    def test_armer_oublie_le_badge_deja_pose(self):
        self.service._handle_gesture("short")
        self.assertIsNone(self.service._active_uid)


class ReaderTestTest(unittest.TestCase):
    """Test du lecteur : distingue "aucune carte", "carte vue" et "carte illisible"."""

    def setUp(self):
        from unittest import mock as _mock

        from rfid import daemon as _daemon

        self.daemon = _daemon
        self.service = _daemon.Service.__new__(_daemon.Service)
        self.service.home = tempfile.mkdtemp(prefix="rfid-rtest-")
        self.service.log = None
        self.service._reader_test = None
        self.service.reader = _mock.Mock()
        self.service.reader.version = 0x92
        self.now = 100.0
        self._patch = _mock.patch.object(_daemon.time, "monotonic", side_effect=lambda: self.now)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.service.home, ignore_errors=True)

    def _run(self, read_uid, request, passes=4):
        chip = self.service.reader.rc522
        chip.read_uid.return_value = read_uid
        chip.request.return_value = request
        self.service._start_reader_test(5)
        for _ in range(passes):
            self.service._reader_test_step()
        self.service._finish_reader_test()
        import json

        path = os.path.join(self.service.home, self.daemon.READER_TEST_FILENAME)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_uid_lu(self):
        result = self._run(b"\xa1\xb2\xc3\xd4", None)
        self.assertTrue(result["finished"])
        self.assertEqual(result["uids"], ["A1B2C3D4"])
        self.assertEqual(result["answers"], 4)
        self.assertTrue(result["reader_ready"])
        self.assertEqual(result["version"], 0x92)

    def test_aucune_carte(self):
        result = self._run(None, None)
        self.assertEqual(result["uids"], [])
        self.assertEqual(result["atqas"], {})
        self.assertEqual(result["answers"], 0)
        self.assertEqual(result["attempts"], 4)
        self.assertTrue(result["reader_ready"])

    def test_carte_vue_mais_illisible(self):
        result = self._run(None, b"\x00\x04")
        self.assertEqual(result["uids"], [])
        self.assertEqual(result["atqas"], {"0004": 4})
        self.assertEqual(result["answers"], 4)
        self.assertEqual(result["reqa"], 4)

    def test_lecteur_indisponible(self):
        self.service.reader = None
        self.service._start_reader_test(5)
        self.service._reader_test_step()
        import json

        path = os.path.join(self.service.home, self.daemon.READER_TEST_FILENAME)
        with open(path, encoding="utf-8") as handle:
            result = json.load(handle)
        self.assertFalse(result["reader_ready"])
        self.assertTrue(result["errors"])

    def test_delai_borne(self):
        self.service._start_reader_test(500)
        self.assertLessEqual(self.service._reader_test["seconds"], 15.0)
        self.service._start_reader_test(0)
        self.assertGreaterEqual(self.service._reader_test["seconds"], 2.0)


class BadgeLatchTest(unittest.TestCase):
    """Mode "cartouche" : un badge laisse sur le lecteur n'agit qu'une fois."""

    def setUp(self):
        from unittest import mock as _mock

        from rfid import daemon as _daemon

        self.daemon = _daemon
        self.service = _daemon.Service.__new__(_daemon.Service)
        self.service.home = tempfile.mkdtemp(prefix="rfid-latch-")
        self.service.log = None
        self.service.rearm_absent_ms = 1200.0
        self.service._active_uid = None
        self.service._absent_since = None
        self.service.last_uid = None
        self.service.last_uid_at = 0
        self.actions = []
        self.service.controller = _mock.Mock()
        self.service.controller.on_badge = lambda uid: self.actions.append(uid)
        self.service.reader = _mock.Mock()
        self.service.reader.tag_present.return_value = True
        self.now = 100.0
        self._patch = _mock.patch.object(_daemon.time, "monotonic", side_effect=lambda: self.now)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.service.home, ignore_errors=True)

    def test_badge_laisse_n_agit_qu_une_fois(self):
        for _ in range(5):
            self.service._badge_seen("A1B2C3D4")
            self.now += 0.15
            self.service._release_latch()      # badge toujours present
        self.assertEqual(self.actions, ["A1B2C3D4"])

    def test_retirer_puis_representer_refait_l_action(self):
        self.service._badge_seen("A1B2C3D4")
        self.service.reader.tag_present.return_value = False
        self.now += 0.2
        self.service._release_latch()          # debut de l'absence
        self.now += 1.3
        self.service._release_latch()          # absence assez longue
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4", "A1B2C3D4"])

    def test_absence_trop_courte_ne_rearme_pas(self):
        self.service._badge_seen("A1B2C3D4")
        self.service.reader.tag_present.return_value = False
        self.now += 0.2
        self.service._release_latch()
        self.now += 0.4
        self.service._release_latch()
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4"])

    def test_autre_badge_agit_immediatement(self):
        self.service._badge_seen("A1B2C3D4")
        self.service._badge_seen("11223344")
        self.assertEqual(self.actions, ["A1B2C3D4", "11223344"])

