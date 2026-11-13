"""Consistency of version numbers across the project.

This test prevents the classic slip: releasing a 1.1.0 while leaving
``__version__`` or ``install.sh`` at 1.0.0.
"""

from __future__ import annotations

import os
import re
import unittest

import support  # noqa: F401  (adds app/ to sys.path)

import rfid

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(relative: str) -> str:
    with open(os.path.join(PROJECT, relative), "r", encoding="utf-8") as handle:
        return handle.read()


class VersionConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.version = read("VERSION").strip()
        self.assertRegex(self.version, r"^\d+\.\d+\.\d+$")

    def test_module_version(self):
        self.assertEqual(rfid.__version__, self.version)

    def test_installateur(self):
        self.assertIn('VERSION="%s"' % self.version, read("install.sh"))

    def test_changelog(self):
        self.assertIn("## [%s]" % self.version, read("CHANGELOG.md"))

    def test_readme_ne_annonce_pas_une_autre_version(self):
        readme = read("README.md")
        # IP addresses (127.0.0.1) must not be taken for versions.
        for version in re.findall(r"(?<![\d.])(\d+\.\d+\.\d+)(?![\d.])", readme):
            self.assertEqual(version, self.version, "version %s dans README.md" % version)


if __name__ == "__main__":
    unittest.main()
