"""The reader screen straight at boot (system.es.atstartup and custom.sh)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support
from rfid import bootmode


class BootModeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rfid-boot-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.home = os.path.join(self.dir, "rfid")
        os.makedirs(self.home)
        self.conf = os.path.join(self.dir, "recalbox.conf")
        self.custom = os.path.join(self.dir, "custom.sh")
        self.write(self.conf, "kodi.atstartup=0\nsystem.language=fr_FR\n")

    @staticmethod
    def write(path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def skip(self):
        return bootmode.skip_interface(self.home, conf=self.conf, custom=self.custom, userscripts="/u")

    def restore(self):
        return bootmode.restore_interface(self.home, conf=self.conf, custom=self.custom)

    def test_aller_retour_sans_reglage(self):
        before = self.read(self.conf)
        self.assertTrue(self.skip())
        self.assertIn("system.es.atstartup=0", self.read(self.conf))
        self.assertTrue(bootmode.skipping(self.conf))
        script = self.read(self.custom)
        self.assertTrue(script.startswith("#!/bin/bash"))
        self.assertIn('"/u/recalbox-rfid(permanent).py3"', script)
        self.assertIn("S31emulationstation start", script, "securite : l'interface revient")
        self.assertFalse(self.skip(), "deja fait")
        self.assertTrue(self.restore())
        self.assertEqual(self.read(self.conf), before, "le fichier redevient identique")
        self.assertFalse(os.path.exists(self.custom), "custom.sh n'existait pas")
        self.assertFalse(bootmode.skipping(self.conf))

    def test_valeur_d_avant_rendue(self):
        self.write(self.conf, "system.es.atstartup=1\n")
        self.skip()
        self.restore()
        self.assertEqual(self.read(self.conf), "system.es.atstartup=1\n")

    def test_custom_sh_de_l_utilisateur_garde(self):
        self.write(self.custom, "#!/bin/bash\necho bonjour\n")
        self.skip()
        self.assertIn("echo bonjour", self.read(self.custom))
        self.restore()
        self.assertEqual(self.read(self.custom), "#!/bin/bash\necho bonjour\n")

    def test_reglage_de_l_utilisateur_non_touche(self):
        """atstartup=0 set by the user (not by the reader): left as it is."""
        self.write(self.conf, "system.es.atstartup=0\n")
        self.restore()
        self.assertEqual(self.read(self.conf), "system.es.atstartup=0\n")
        self.write(self.custom, "#!/bin/bash\n")
        self.restore()
        self.assertTrue(os.path.exists(self.custom), "un custom.sh sans notre bloc reste")


class ReaderModeBootTest(unittest.TestCase):
    def test_entree_et_sortie(self):
        from rfid.reader_mode import ReaderMode

        calls = []
        boot = {"skip": lambda: calls.append("skip") or True, "restore": lambda: calls.append("restore") or True,
                "skipping": lambda: True}
        home = tempfile.mkdtemp(prefix="rfid-boot-mode-")
        self.addCleanup(shutil.rmtree, home, True)

        class Process:
            def poll(self):
                return None

            def send_signal(self, sig):
                pass

            def wait(self, timeout=None):
                return 0

        clock = support.FakeClock()
        mode = ReaderMode(home, None, run=lambda args: None, running=lambda: False, popen=lambda *a, **k: Process(),
                          clock=clock, sleep=clock.advance, uptime=lambda: 10.0, hotkey_path=os.path.join(home, "o.cfg"),
                          state_path=os.path.join(home, "es_state.inf"), boot=boot)
        mode.enter()
        self.assertEqual(mode.state, "screen", "pas d'attente de l'interface au demarrage")
        self.assertEqual(calls, ["skip"])
        mode.leave()
        self.assertEqual(calls, ["skip", "restore"], "rendu avant de relancer l'interface")


if __name__ == "__main__":
    unittest.main()
