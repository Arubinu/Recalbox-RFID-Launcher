"""Tests de l'interface web (serveur HTTP réel, sur un port libre)."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import types
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest import mock

import support  # noqa: F401  (ajoute app/ au sys.path)

from rfid import webui as webui_module
from rfid.config import Config
from rfid.webui import WebUI


class WebUITestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-web-")
        self.home = os.path.join(self.directory, "home")
        os.makedirs(self.home, exist_ok=True)
        self.config_path = os.path.join(self.home, "config.ini")
        self.ui = None
        self.password = ""

    def tearDown(self):
        if self.ui is not None:
            self.ui.stop()
        shutil.rmtree(self.directory, ignore_errors=True)

    # ------------------------------------------------------------------ outils
    def start(self, password=""):
        if password:
            with open(self.config_path, "w", encoding="utf-8") as handle:
                handle.write("[web]\nport = 0\npassword = %s\n" % password)
        config = Config(self.config_path)
        self.ui = WebUI(config, log=None, home=self.home, port=0)
        self.assertTrue(self.ui.start())
        self.port = self.ui.server.server_address[1]
        return self.ui

    def request(self, path, method="GET", body=None, headers=None, raw=None):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def json_request(self, path, method="GET", body=None, headers=None):
        merged = {"Content-Type": "application/json"}
        merged.update(headers or {})
        status, text = self.request(
            path, method=method, body=body if body is not None else {}, headers=merged
        )
        try:
            return status, json.loads(text) if text else {}
        except ValueError:
            return status, {"raw": text}


class PageTest(WebUITestCase):
    def test_page_servie(self):
        self.start()
        status, text = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("Recalbox RFID Launcher", text)
        self.assertIn("/api/status", text)

    def test_route_inconnue(self):
        self.start()
        status, _ = self.request("/api/inexistant")
        self.assertEqual(status, 404)


class StatusTest(WebUITestCase):
    def test_non_installe(self):
        self.start()
        status, payload = self.json_request("/api/status")
        self.assertEqual(status, 200)
        self.assertFalse(payload["installed"])
        self.assertFalse(payload["spi"])
        self.assertEqual(payload["tags"], 0)
        self.assertFalse(payload["service"]["running"])
        self.assertEqual(payload["web"]["port"], self.port)

    def test_installe(self):
        os.makedirs(os.path.join(self.home, "app"), exist_ok=True)
        with open(os.path.join(self.home, "app", "main.py"), "w", encoding="utf-8") as handle:
            handle.write("# faux programme\n")
        with open(os.path.join(self.home, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write("1.1.0\n")
        self.start()
        _, payload = self.json_request("/api/status")
        self.assertTrue(payload["installed"])
        self.assertEqual(payload["installed_version"], "1.1.0")


class CurrentTargetTest(WebUITestCase):
    def test_jeu_selectionne(self):
        state = {
            "SystemId": "snes",
            "Game": "Super Mario World",
            "GamePath": "/recalbox/share/roms/snes/Super Mario World.smc",
            "IsFolder": "0",
            "State": "selected",
        }
        self.start()
        with mock.patch.object(webui_module, "read_state", lambda: state):
            status, payload = self.json_request("/api/current")
        self.assertEqual(status, 200)
        self.assertEqual(payload["current"]["system"], "snes")
        self.assertEqual(payload["current"]["game"], "Super Mario World.smc")

    def test_aucun_jeu(self):
        self.start()
        with mock.patch.object(webui_module, "read_state", lambda: None):
            _, payload = self.json_request("/api/current")
        self.assertIsNone(payload["current"])


class TagsTest(WebUITestCase):
    def test_ajout_liste_suppression(self):
        self.start()
        status, payload = self.json_request(
            "/api/tags",
            method="POST",
            body={"uid": "a1:b2:c3:d4", "system": "snes", "game": "jeu.smc", "name": "Jeu"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["uid"], "A1B2C3D4")

        _, listing = self.json_request("/api/tags")
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["tags"][0]["pretty"], "A1:B2:C3:D4")

        status, _ = self.json_request("/api/tags/A1B2C3D4", method="DELETE")
        self.assertEqual(status, 200)
        _, listing = self.json_request("/api/tags")
        self.assertEqual(listing["count"], 0)

    def test_suppression_par_post(self):
        self.start()
        self.json_request(
            "/api/tags", method="POST", body={"uid": "A1B2C3D4", "system": "nes", "game": "z.nes"}
        )
        status, payload = self.json_request("/api/tags/delete", method="POST", body={"uid": "A1B2C3D4"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_ajout_incomplet(self):
        self.start()
        status, payload = self.json_request(
            "/api/tags", method="POST", body={"uid": "A1B2C3D4", "system": "snes"}
        )
        self.assertEqual(status, 400)
        self.assertIn("jeu", payload["error"])

    def test_uid_invalide(self):
        self.start()
        status, _ = self.json_request(
            "/api/tags", method="POST", body={"uid": "ZZZZ", "system": "snes", "game": "jeu.smc"}
        )
        self.assertEqual(status, 400)

    def test_export_et_import(self):
        self.start()
        self.json_request(
            "/api/tags", method="POST", body={"uid": "A1B2C3D4", "system": "snes", "game": "jeu.smc"}
        )
        status, csv_text = self.request("/api/export")
        self.assertEqual(status, 200)
        self.assertIn("uid;system;game;name", csv_text)
        self.assertIn("A1:B2:C3:D4", csv_text)

        self.json_request("/api/tags/A1B2C3D4", method="DELETE")
        status, payload = self.request(
            "/api/import", method="POST", raw=csv_text.encode("utf-8"), headers={"Content-Type": "text/csv"}
        )
        self.assertEqual(status, 200)
        self.assertIn("stats", json.loads(payload))
        _, listing = self.json_request("/api/tags")
        self.assertEqual(listing["count"], 1)


class SecurityTest(WebUITestCase):
    def test_origine_refusee(self):
        self.start()
        status, _ = self.json_request(
            "/api/tags",
            method="POST",
            body={"uid": "A1B2C3D4", "system": "snes", "game": "jeu.smc"},
            headers={"Origin": "http://attaquant.example"},
        )
        self.assertEqual(status, 403)

    def test_origine_autorisee(self):
        self.start()
        status, _ = self.json_request(
            "/api/tags",
            method="POST",
            body={"uid": "A1B2C3D4", "system": "snes", "game": "jeu.smc"},
            headers={"Origin": "http://127.0.0.1:%d" % self.port},
        )
        self.assertEqual(status, 200)

    def test_content_type_formulaire_refuse(self):
        self.start()
        status, payload = self.request(
            "/api/tags",
            method="POST",
            raw=b"uid=A1B2C3D4",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(status, 400)
        self.assertIn("application/json", json.loads(payload)["error"])

    def test_mot_de_passe(self):
        self.start(password="secret")
        status, _ = self.request("/api/tags")
        self.assertEqual(status, 401)

        credentials = base64.b64encode(b"root:secret").decode("ascii")
        status, _ = self.request("/api/tags", headers={"Authorization": "Basic " + credentials})
        self.assertEqual(status, 200)

        wrong = base64.b64encode(b"root:autre").decode("ascii")
        status, _ = self.request("/api/tags", headers={"Authorization": "Basic " + wrong})
        self.assertEqual(status, 401)


class CommandTest(WebUITestCase):
    def test_association_sans_service(self):
        self.start()
        status, payload = self.json_request("/api/associate", method="POST", body={"mode": "associate"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertIn("service", payload["error"])

    def test_scan_sans_service(self):
        self.start()
        status, payload = self.json_request("/api/scan", method="POST", body={"uid": "a1b2c3d4"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])


class InstallTest(WebUITestCase):
    def _fake_subprocess(self, output="INSTALLATION FACTICE OK\n", code=0):
        recorded = {}

        def fake_run(command, **kwargs):
            recorded["command"] = command
            recorded["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, code, output)

        module = types.SimpleNamespace(
            run=fake_run,
            PIPE=subprocess.PIPE,
            STDOUT=subprocess.STDOUT,
            DEVNULL=subprocess.DEVNULL,
            TimeoutExpired=subprocess.TimeoutExpired,
            Popen=subprocess.Popen,
        )
        return module, recorded

    def test_installation_locale(self):
        installer = os.path.join(self.home, "install.sh")
        with open(installer, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        self.start()
        module, recorded = self._fake_subprocess()
        with mock.patch.object(webui_module, "subprocess", module):
            status, payload = self.json_request("/api/install", method="POST", body={})
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            for _ in range(100):
                _, state = self.json_request("/api/install/status")
                if state["state"] != "running":
                    break
                time.sleep(0.05)
        self.assertEqual(state["state"], "ok")
        self.assertIn("INSTALLATION FACTICE", state["output"])
        self.assertIn("--no-restart", recorded["command"])
        self.assertIn("--upgrade", recorded["command"])
        self.assertEqual(recorded["command"][1], installer)

    def test_installation_en_echec(self):
        installer = os.path.join(self.home, "install.sh")
        with open(installer, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        self.start()
        module, _ = self._fake_subprocess(output="boum", code=3)
        with mock.patch.object(webui_module, "subprocess", module):
            self.json_request("/api/install", method="POST", body={})
            for _ in range(100):
                _, state = self.json_request("/api/install/status")
                if state["state"] != "running":
                    break
                time.sleep(0.05)
        self.assertEqual(state["state"], "error")
        self.assertEqual(state["code"], 3)

    def test_installation_sans_installateur(self):
        self.start()
        status, _ = self.json_request("/api/install", method="POST", body={})
        self.assertEqual(status, 200)
        for _ in range(100):
            _, state = self.json_request("/api/install/status")
            if state["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(state["state"], "error")
        self.assertIn("install.sh", state["output"])

    def test_double_installation_refusee(self):
        self.start()
        self.ui._install["state"] = "running"  # noqa: SLF001
        status, payload = self.json_request("/api/install", method="POST", body={})
        self.assertEqual(status, 409)
        self.assertIn("deja", payload["error"])

    def test_upload_zip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("recalbox-rfid/install.sh", "#!/bin/sh\n")
            bundle.writestr("recalbox-rfid/VERSION", "1.1.0\n")
        self.start()
        module, recorded = self._fake_subprocess()
        with mock.patch.object(webui_module, "subprocess", module):
            status, _ = self.request(
                "/api/upload",
                method="POST",
                raw=buffer.getvalue(),
                headers={"Content-Type": "application/zip"},
            )
            self.assertEqual(status, 200)
            for _ in range(100):
                _, state = self.json_request("/api/install/status")
                if state["state"] != "running":
                    break
                time.sleep(0.05)
        self.assertEqual(state["state"], "ok")
        self.assertTrue(recorded["command"][1].endswith("install.sh"))
        self.assertIn("rfid-update-", recorded["command"][1])

    def test_upload_type_refuse(self):
        self.start()
        status, payload = self.request(
            "/api/upload", method="POST", raw=b"pas un zip", headers={"Content-Type": "text/plain"}
        )
        self.assertEqual(status, 400)
        self.assertIn("ZIP", json.loads(payload)["error"])


if __name__ == "__main__":
    unittest.main()
