"""Tests du script permanent qui lance l'agent WebSocket."""

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
BOOTSTRAP = os.path.join(PROJECT, "bootstrap", "recalbox-rfid-agent(permanent).py3")


def load_bootstrap():
    loader = SourceFileLoader("rfid_agent_bootstrap", BOOTSTRAP)
    spec = importlib.util.spec_from_loader("rfid_agent_bootstrap", loader)
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
        self.tmp = tempfile.mkdtemp(prefix="rfid-agent-bootstrap-")
        self.home = os.path.join(self.tmp, "home")
        self.share = os.path.join(self.tmp, "share")
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.share, exist_ok=True)
        self.module = load_bootstrap()
        self.module.RFID_HOME = self.home
        self.module.SHARE = self.share

    def tearDown(self):
        sys.modules.pop("rfid_agent_bootstrap", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_source(self):
        folder = os.path.join(self.share, "recalbox-rfid")
        os.makedirs(os.path.join(folder, "app"), exist_ok=True)
        with open(os.path.join(folder, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("# programme\n")
        with open(os.path.join(folder, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        return folder

    def make_installed(self):
        os.makedirs(os.path.join(self.home, "app"), exist_ok=True)
        with open(os.path.join(self.home, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("# programme\n")


class SourceTest(BootstrapTestCase):
    def test_aucun_projet(self):
        self.assertIsNone(self.module.find_source())

    def test_projet_trouve(self):
        folder = self.make_source()
        self.assertEqual(self.module.find_source(), folder)

    def test_installation_ignoree(self):
        self.make_installed()
        with open(os.path.join(self.home, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        self.assertIsNone(self.module.find_source())

    def test_projet_imbrique(self):
        nested = os.path.join(self.share, "outils", "recalbox-rfid")
        os.makedirs(os.path.join(nested, "app"), exist_ok=True)
        with open(os.path.join(nested, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("# programme\n")
        with open(os.path.join(nested, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        self.assertEqual(self.module.find_source(), nested)


class LaunchTest(BootstrapTestCase):
    def test_lance_depuis_installation(self):
        self.make_installed()
        with mock.patch("os.execv") as execv:
            self.assertEqual(self.module.main(), 1)
        execv.assert_called_once()
        arguments = execv.call_args[0][1]
        self.assertEqual(arguments[1], os.path.join(self.home, "app", "main.py"))
        self.assertEqual(arguments[2], "agent")
        self.assertIn("--home", arguments)
        self.assertNotIn("--source", arguments)

    def test_lance_depuis_le_partage(self):
        folder = self.make_source()
        with mock.patch("os.execv") as execv:
            self.assertEqual(self.module.main(), 1)
        arguments = execv.call_args[0][1]
        self.assertEqual(arguments[1], os.path.join(folder, "app", "main.py"))
        self.assertIn("--source", arguments)
        self.assertIn(folder, arguments)

    def test_aucun_lancement_sans_projet(self):
        with mock.patch("os.execv") as execv:
            self.assertEqual(self.module.main(), 1)
        execv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
