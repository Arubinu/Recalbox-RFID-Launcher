"""Tests of the self-contained HTML installer builder."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import unittest

import support  # noqa: F401  (adds app/ to sys.path)

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT, "tools"))

import build_installer  # noqa: E402


class PayloadTest(unittest.TestCase):
    def setUp(self):
        self.payload = build_installer.build_payload()

    def test_version(self):
        self.assertEqual(self.payload["version"], build_installer.version())

    def test_fichiers_essentiels(self):
        files = self.payload["files"]
        for expected in (
            "app/main.py",
            "app/rfid/wsagent.py",
            "install.sh",
            "uninstall.sh",
            "VERSION",
            "bootstrap/recalbox-rfid-agent(permanent).py3",
            "userscript/recalbox-rfid(permanent).py3",
        ):
            self.assertIn(expected, files, expected)

    def test_contenu_identique_aux_sources(self):
        for relative in ("app/main.py", "install.sh", build_installer.USERSCRIPT):
            decoded = base64.b64decode(self.payload["files"][relative])
            with open(os.path.join(PROJECT, relative), "rb") as handle:
                self.assertEqual(decoded, handle.read(), relative)

    def test_pas_de_fichiers_techniques(self):
        for path in self.payload["files"]:
            self.assertNotIn("__pycache__", path)
            self.assertFalse(path.endswith((".pyc", ".pyo")))
            self.assertNotIn("\\", path)  # chemins posix uniquement

    def test_userscript_annonce_present(self):
        self.assertEqual(
            self.payload["userscript"], "bootstrap/recalbox-rfid-agent(permanent).py3"
        )
        self.assertIn(self.payload["userscript"], self.payload["files"])


class HtmlTest(unittest.TestCase):
    def test_ordinateur_autonome(self):
        html = build_installer.build_html()
        self.assertIn('id="rfid-payload"', html)
        self.assertIn("showDirectoryPicker", html)
        self.assertIn("Recalbox RFID Launcher", html)

    def test_payload_analysable(self):
        html = build_installer.build_html()
        extracted = html.split('id="rfid-payload" type="application/json">', 1)[1]
        extracted = extracted.split("</script>", 1)[0]
        payload = json.loads(extracted)
        self.assertIn("app/main.py", payload["files"])
        self.assertEqual(payload["version"], build_installer.version())

    def test_pas_de_balise_script_dans_le_payload(self):
        html = build_installer.build_html()
        start = html.index('<script id="rfid-payload"')
        end = html.index("</script>", start)
        payload = html[start:end]
        self.assertNotIn("</script", payload[payload.index(">") + 1:])
        self.assertNotIn("<script", payload[payload.index(">") + 1:])

    def test_generation_deterministe(self):
        self.assertEqual(
            build_installer.build_html(), build_installer.build_html()
        )


class FileTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-build-")

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_ecriture_du_fichier(self):
        output = os.path.join(self.directory, "installer.html")
        self.assertEqual(build_installer.main(["--output", output]), 0)
        self.assertTrue(os.path.isfile(output))
        with open(output, "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn('id="rfid-payload"', content)
        self.assertGreater(len(content), 100_000)

    def test_fins_de_ligne_lf(self):
        output = os.path.join(self.directory, "installer.html")
        build_installer.main(["--output", output])
        with open(output, "rb") as handle:
            data = handle.read()
        self.assertNotIn(b"\r\n", data)
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))


class CommittedInstallerTest(unittest.TestCase):
    """The file delivered in dist/ must match the current sources."""

    def setUp(self):
        self.dist = os.path.join(PROJECT, "dist")
        self.version = build_installer.version()
        self.path = os.path.join(self.dist, "recalbox-rfid-installer.html")

    def test_fichier_present(self):
        self.assertTrue(
            os.path.isfile(self.path),
            "installateur absent : lancez python tools/build_installer.py",
        )

    def test_fichier_a_jour(self):
        if not os.path.isfile(self.path):
            self.skipTest("fichier absent")
        with open(self.path, "r", encoding="utf-8") as handle:
            committed = handle.read()
        self.assertEqual(
            committed,
            build_installer.build_html(),
            "installateur périmé : relancez python tools/build_installer.py",
        )

    def test_langues_embarquees(self):
        """Each i18n/*.json file is compiled into the page (like the rest)."""
        import json
        import tools.build_installer as bati

        langues = bati.collect_languages()
        self.assertIn("fr", langues, "la langue de reference doit exister")
        self.assertIn("en", langues)
        self.assertGreater(len(langues["en"]), 100)
        texte = self.html if hasattr(self, "html") else bati.build_html()
        self.assertIn('id="rfid-i18n"', texte)
        debut = texte.index('id="rfid-i18n"')
        charge = texte[debut:].split(">", 1)[1].split("</script>", 1)[0]
        data = json.loads(charge)
        self.assertEqual(data["source"], "fr")
        self.assertIn("en", data["langues"])
        # a known key must be translated
        self.assertIn("Se connecter", data["langues"]["en"])

    def test_pas_d_ancienne_version(self):
        if not os.path.isdir(self.dist):
            self.skipTest("dossier dist absent")
        others = [
            name
            for name in os.listdir(self.dist)
            if name.startswith("recalbox-rfid-installer") and name != os.path.basename(self.path)
        ]
        self.assertEqual(others, [], "anciennes versions présentes dans dist/")


class InterrupteurTest(unittest.TestCase):
    """The switch knob must be centered in its track.

    Regression: `top: 2px` on a 22 px knob (border included) in a 24 px inner
    track stuck it to the bottom. The construction that guarantees the
    centering is checked, not a pixel value.
    """

    def test_rond_centre_verticalement(self):
        texte = build_installer.build_html()
        debut = texte.index(".switch::after {")
        bloc = texte[debut:debut + 500]
        self.assertIn("top: 50%", bloc)
        self.assertIn("translateY(-50%)", bloc)
        self.assertIn("box-sizing: border-box", bloc)
        self.assertNotIn("top: 2px", bloc)

    def test_rond_centre_une_fois_active(self):
        texte = build_installer.build_html()
        self.assertIn(
            '.switch[aria-checked="true"]::after { transform: translate(20px, -50%); }',
            texte,
        )


if __name__ == "__main__":
    unittest.main()
