"""Tests du script d'auto-installation (sans Recalbox, sans effet de bord)."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from unittest import mock

import support  # noqa: F401  (ajoute app/ au sys.path)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOTSTRAP = os.path.join(PROJECT, "bootstrap", "recalbox-rfid-autoinstall(permanent).py3")


def load_bootstrap():
    # Extension .py3 : il faut fournir explicitement le chargeur de code source.
    loader = SourceFileLoader("rfid_bootstrap", BOOTSTRAP)
    spec = importlib.util.spec_from_loader("rfid_bootstrap", loader)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # ne pas créer de __pycache__ dans bootstrap/
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class BootstrapTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfid-bootstrap-")
        self.home = os.path.join(self.tmp, "home")
        self.share = os.path.join(self.tmp, "share")
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.share, exist_ok=True)
        self.module = load_bootstrap()
        self.module.RFID_HOME = self.home
        self.module.SHARE = self.share
        self.module.BOOT_CONFIG = os.path.join(self.tmp, "recalbox-user-config.txt")
        self.module.STATE_FILE = os.path.join(self.tmp, "es_state.inf")
        self.module.WAIT_TICKS = 0

    def tearDown(self):
        sys.modules.pop("rfid_bootstrap", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ outils
    def make_source(self, version="1.2.0"):
        folder = os.path.join(self.share, "recalbox-rfid")
        os.makedirs(os.path.join(folder, "app"), exist_ok=True)
        with open(os.path.join(folder, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("# programme\n")
        with open(os.path.join(folder, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        with open(os.path.join(folder, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write(version + "\n")
        return folder

    def make_installed(self, version="1.1.0"):
        os.makedirs(os.path.join(self.home, "app"), exist_ok=True)
        with open(os.path.join(self.home, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("# programme\n")
        with open(os.path.join(self.home, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write(version + "\n")

    def write_state(self, state):
        with open(self.module.STATE_FILE, "w", encoding="utf-8") as handle:
            handle.write("Action=rungame\nState=%s\n" % state)


class VersionTest(BootstrapTestCase):
    def test_analyse_version(self):
        self.assertEqual(self.module.version_tuple("1.2.0"), (1, 2, 0))
        self.assertEqual(self.module.version_tuple("2"), (2, 0, 0))
        self.assertEqual(self.module.version_tuple(""), (0, 0, 0))
        self.assertEqual(self.module.version_tuple("1.10.0"), (1, 10, 0))
        self.assertGreater(
            self.module.version_tuple("1.10.0"), self.module.version_tuple("1.9.9")
        )

    def test_lecture_version(self):
        self.make_source("1.2.3")
        self.assertEqual(self.module.read_version(os.path.join(self.share, "recalbox-rfid")), "1.2.3")
        self.assertEqual(self.module.read_version(os.path.join(self.tmp, "absent")), "")

    def test_version_plus_recente(self):
        source = self.make_source("1.2.0")
        self.make_installed("1.1.0")
        self.assertTrue(self.module.newer_source_available(source))

        self.make_installed("1.2.0")
        self.assertFalse(self.module.newer_source_available(source))

        self.make_installed("1.3.0")
        self.assertFalse(self.module.newer_source_available(source))

        self.assertFalse(self.module.newer_source_available(None))


class EtatTest(BootstrapTestCase):
    def test_installe(self):
        self.assertFalse(self.module.installed())
        self.make_installed()
        self.assertTrue(self.module.installed())

    def test_recherche_du_projet(self):
        self.assertIsNone(self.module.find_source())
        folder = self.make_source("1.2.0")
        self.assertEqual(self.module.find_source(), folder)

    def test_projet_installe_ignore(self):
        # Le dossier installé ne doit pas être confondu avec la source.
        self.make_installed()
        with open(os.path.join(self.home, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        self.assertIsNone(self.module.find_source())

    def test_spi_configure(self):
        self.assertFalse(self.module.spi_configured())
        with open(self.module.BOOT_CONFIG, "w", encoding="utf-8") as handle:
            handle.write("disable_overscan=1\n")
        self.assertFalse(self.module.spi_configured())
        with open(self.module.BOOT_CONFIG, "a", encoding="utf-8") as handle:
            handle.write("dtparam=spi=on\r\n")
        self.assertTrue(self.module.spi_configured())
        with open(self.module.BOOT_CONFIG, "w", encoding="utf-8") as handle:
            handle.write("dtparam = spi=on\n")
        self.assertTrue(self.module.spi_configured())

    def test_jeu_en_cours(self):
        self.assertFalse(self.module.game_running())
        self.write_state("selected")
        self.assertFalse(self.module.game_running())
        self.write_state("playing")
        self.assertTrue(self.module.game_running())

    def test_daemon_absent(self):
        self.assertFalse(self.module.daemon_running())
        with open(os.path.join(self.home, "rfid.pid"), "w", encoding="ascii") as handle:
            handle.write("999999\n")
        self.assertFalse(self.module.daemon_running())

    @unittest.skipUnless(os.path.isdir("/proc"), "necessite /proc (Linux)")
    def test_daemon_present(self):
        with open(os.path.join(self.home, "rfid.pid"), "w", encoding="ascii") as handle:
            handle.write("%d\n" % os.getpid())
        self.assertTrue(self.module.daemon_running())


class MainTest(BootstrapTestCase):
    def test_service_deja_actif(self):
        self.make_installed()
        with mock.patch.object(self.module, "daemon_running", return_value=True), \
             mock.patch.object(self.module, "run_install") as install:
            self.assertEqual(self.module.main(), 0)
        install.assert_not_called()

    def test_installation_automatique_puis_redemarrage(self):
        self.make_source("1.2.0")
        with mock.patch.object(self.module, "run_install", return_value=0) as install, \
             mock.patch.object(self.module, "spi_active", return_value=False), \
             mock.patch.object(self.module, "spi_configured", return_value=True), \
             mock.patch.object(self.module, "game_running", return_value=False), \
             mock.patch.object(self.module, "reboot_system") as reboot:
            self.assertEqual(self.module.main(), 0)
        install.assert_called_once()
        reboot.assert_called_once()

    def test_installation_puis_service_si_spi_deja_actif(self):
        self.make_source("1.2.0")
        with mock.patch.object(self.module, "run_install", return_value=0), \
             mock.patch.object(self.module, "spi_active", return_value=True), \
             mock.patch.object(self.module, "start_service") as start, \
             mock.patch.object(self.module, "reboot_system") as reboot:
            self.assertEqual(self.module.main(), 0)
        start.assert_called_once()
        reboot.assert_not_called()

    def test_pas_de_redemarrage_pendant_un_jeu(self):
        self.make_source("1.2.0")
        with mock.patch.object(self.module, "run_install", return_value=0), \
             mock.patch.object(self.module, "spi_active", return_value=False), \
             mock.patch.object(self.module, "spi_configured", return_value=True), \
             mock.patch.object(self.module, "game_running", return_value=True), \
             mock.patch.object(self.module, "start_service") as start, \
             mock.patch.object(self.module, "reboot_system") as reboot:
            self.assertEqual(self.module.main(), 0)
        start.assert_called_once()
        reboot.assert_not_called()

    def test_echec_installation_ouvre_la_page(self):
        self.make_source("1.2.0")
        with mock.patch.object(self.module, "run_install", return_value=1), \
             mock.patch.object(self.module, "serve_web", return_value=1) as serve:
            self.assertEqual(self.module.main(), 1)
        serve.assert_called_once()

    def test_aucun_projet(self):
        with mock.patch.object(self.module, "serve_web") as serve:
            self.assertEqual(self.module.main(), 1)
        serve.assert_not_called()

    def test_mise_a_jour_automatique(self):
        self.make_installed("1.0.0")
        self.make_source("1.2.0")
        with mock.patch.object(self.module, "daemon_running", return_value=False), \
             mock.patch.object(self.module, "run_install", return_value=0) as install, \
             mock.patch.object(self.module, "start_service") as start:
            self.assertEqual(self.module.main(), 0)
        install.assert_called_once()
        start.assert_called_once()

    def test_pas_de_mise_a_jour_si_version_identique(self):
        self.make_installed("1.2.0")
        self.make_source("1.2.0")
        with mock.patch.object(self.module, "daemon_running", return_value=False), \
             mock.patch.object(self.module, "run_install") as install, \
             mock.patch.object(self.module, "serve_web", return_value=1) as serve:
            self.assertEqual(self.module.main(), 1)
        install.assert_not_called()
        serve.assert_called_once()

    def test_page_de_secours_si_service_absent(self):
        self.make_installed("1.2.0")
        with mock.patch.object(self.module, "daemon_running", return_value=False), \
             mock.patch.object(self.module, "serve_web", return_value=1) as serve:
            self.assertEqual(self.module.main(), 1)
        serve.assert_called_once()

    def test_journal(self):
        self.module.log("message de test")
        path = os.path.join(self.home, "logs", "auto-install.log")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as handle:
            self.assertIn("message de test", handle.read())


if __name__ == "__main__":
    unittest.main()
