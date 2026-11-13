"""Permanent script tests: automatic installation + agent."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from unittest import mock

import support  # noqa: F401  (adds app/ to sys.path)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOTSTRAP = os.path.join(PROJECT, "bootstrap", "recalbox-rfid-agent(permanent).py3")


def load_bootstrap():
    loader = SourceFileLoader("rfid_agent_bootstrap", BOOTSTRAP)
    spec = importlib.util.spec_from_loader("rfid_agent_bootstrap", loader)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # do not create a __pycache__ in bootstrap/
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class BootstrapTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfid-agent-bootstrap-")
        self.home = os.path.join(self.tmp, "home")
        self.share = os.path.join(self.tmp, "share")
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.share, exist_ok=True)
        self.module = load_bootstrap()
        self.module.RFID_HOME = self.home
        self.module.SHARE = self.share
        self.module.BOOT_CONFIG = os.path.join(self.tmp, "recalbox-user-config.txt")
        self.module.STATE_FILE = os.path.join(self.tmp, "es_state.inf")

    def tearDown(self):
        sys.modules.pop("rfid_agent_bootstrap", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ outils
    def make_source(self, version="1.6.0"):
        folder = os.path.join(self.share, "recalbox-rfid")
        os.makedirs(os.path.join(folder, "app"), exist_ok=True)
        for name in ("app/main.py", "install.sh"):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write("# programme\n")
        with open(os.path.join(folder, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write(version + "\n")
        return folder

    def make_installed(self, version="1.5.0"):
        os.makedirs(os.path.join(self.home, "app"), exist_ok=True)
        with open(os.path.join(self.home, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("# programme\n")
        with open(os.path.join(self.home, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write(version + "\n")

    def write_state(self, state):
        with open(self.module.STATE_FILE, "w", encoding="utf-8") as handle:
            handle.write("Action=rungame\nState=%s\n" % state)

    def patch_agent(self):
        return mock.patch.object(self.module, "launch_agent")


class HelperTest(BootstrapTestCase):
    def test_versions(self):
        self.assertEqual(self.module.version_tuple("1.6.0"), (1, 6, 0))
        self.assertEqual(self.module.version_tuple("2"), (2, 0, 0))
        self.assertGreater(
            self.module.version_tuple("1.10.0"), self.module.version_tuple("1.9.9")
        )

    def test_version_plus_recente(self):
        source = self.make_source("1.6.0")
        self.make_installed("1.5.0")
        self.assertTrue(self.module.newer_source_available(source))
        self.make_installed("1.6.0")
        self.assertFalse(self.module.newer_source_available(source))
        self.assertFalse(self.module.newer_source_available(None))

    def test_recherche_du_projet(self):
        self.assertIsNone(self.module.find_source())
        folder = self.make_source()
        self.assertEqual(self.module.find_source(), folder)

    def test_installation_ignoree(self):
        self.make_installed()
        with open(os.path.join(self.home, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        self.assertIsNone(self.module.find_source())

    def test_spi(self):
        self.assertFalse(self.module.spi_configured())
        with open(self.module.BOOT_CONFIG, "w", encoding="utf-8") as handle:
            handle.write("dtparam = spi=on\n")
        self.assertTrue(self.module.spi_configured())
        with mock.patch.object(self.module, "spi_active", return_value=False):
            self.assertTrue(self.module.needs_reboot())
        with mock.patch.object(self.module, "spi_active", return_value=True):
            self.assertFalse(self.module.needs_reboot())

    def test_jeu_en_cours(self):
        self.assertFalse(self.module.game_running())
        self.write_state("selected")
        self.assertFalse(self.module.game_running())
        self.write_state("playing")
        self.assertTrue(self.module.game_running())


class MainTest(BootstrapTestCase):
    def test_premiere_installation_sans_redemarrage(self):
        self.make_source("1.6.0")
        with mock.patch.object(self.module, "run_install", return_value=0) as install, \
             mock.patch.object(self.module, "needs_reboot", return_value=False), \
             mock.patch.object(self.module, "start_service") as start, \
             mock.patch.object(self.module, "reboot_system") as reboot, \
             self.patch_agent():
            self.module.main()
        install.assert_called_once()
        start.assert_called_once()
        reboot.assert_not_called()

    def test_premiere_installation_avec_redemarrage(self):
        self.make_source("1.6.0")
        with mock.patch.object(self.module, "run_install", return_value=0), \
             mock.patch.object(self.module, "needs_reboot", return_value=True), \
             mock.patch.object(self.module, "game_running", return_value=False), \
             mock.patch.object(self.module, "reboot_system") as reboot, \
             self.patch_agent():
            self.module.main()
        reboot.assert_called_once()

    def test_pas_de_redemarrage_pendant_un_jeu(self):
        self.make_source("1.6.0")
        with mock.patch.object(self.module, "run_install", return_value=0), \
             mock.patch.object(self.module, "needs_reboot", return_value=True), \
             mock.patch.object(self.module, "game_running", return_value=True), \
             mock.patch.object(self.module, "reboot_system") as reboot, \
             mock.patch.object(self.module, "start_service") as start, \
             self.patch_agent():
            self.module.main()
        reboot.assert_not_called()
        start.assert_called_once()

    def test_mise_a_jour_si_version_plus_recente(self):
        self.make_installed("1.5.0")
        self.make_source("1.6.0")
        with mock.patch.object(self.module, "run_install", return_value=0) as install, \
             mock.patch.object(self.module, "start_service") as start, \
             self.patch_agent():
            self.module.main()
        install.assert_called_once()
        start.assert_called_once()

    def test_pas_de_mise_a_jour_si_version_identique(self):
        self.make_installed("1.6.0")
        self.make_source("1.6.0")
        with mock.patch.object(self.module, "run_install") as install, \
             self.patch_agent():
            self.module.main()
        install.assert_not_called()

    def test_aucun_projet(self):
        with mock.patch.object(self.module, "launch_agent") as agent:
            self.assertEqual(self.module.main(), 1)
        agent.assert_not_called()

    def test_journal(self):
        self.module.log("message de test")
        path = os.path.join(self.home, "logs", "auto-install.log")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as handle:
            self.assertIn("message de test", handle.read())


if __name__ == "__main__":
    unittest.main()
