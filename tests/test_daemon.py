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
