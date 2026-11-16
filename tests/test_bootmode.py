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
        custom = self.read(self.custom).splitlines()
        boot = os.path.join(self.home, "boot.sh")
        self.assertEqual(custom[0], "#!/bin/bash")
        self.assertEqual(custom[-2], bootmode.COMMENT, "un commentaire en anglais")
        self.assertIn('sh "%s" "$1"' % boot, custom[-1], "une seule ligne qui appelle notre fichier")
        self.assertIn("S31emulationstation start", custom[-1], "sans boot.sh, l'interface revient")
        script = self.read(boot)
        self.assertIn('"/u/recalbox-rfid(permanent).py3"', script)
        self.assertIn("pgrep -f 'main.py daemon'", script, "securite : l'interface revient")
        self.assertFalse(self.skip(), "deja fait")
        self.assertTrue(self.restore())
        self.assertEqual(self.read(self.conf), before, "le fichier redevient identique")
        self.assertFalse(os.path.exists(self.custom), "custom.sh n'existait pas")
        self.assertFalse(os.path.exists(boot))
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

    def test_ancien_bloc_remplace(self):
        old = [bootmode.OLD_BEGIN, 'if [ "$1" = "start" ]; then', "  true", "fi", bootmode.OLD_END]
        self.write(self.custom, "\n".join(["#!/bin/bash", "echo bonjour"] + old) + "\n")
        self.skip()
        text = self.read(self.custom)
        self.assertNotIn(bootmode.OLD_BEGIN, text)
        self.assertEqual(text.count(bootmode.COMMENT), 1)
        self.assertIn("echo bonjour", text)
        self.skip()
        self.assertEqual(self.read(self.custom).count(bootmode.COMMENT), 1, "une seule fois")

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
        mode.enter()
        boot["stopping"] = lambda: True
        mode.shutdown()
        self.assertEqual(calls[-1], "skip", "la Recalbox s'arrete : rien n'est rendu")
        self.assertEqual(mode.state, "screen")

    def test_bloc_arret(self):
        lines = "\n".join(bootmode.boot_lines("/u", "/c"))
        self.assertIn('if [ "$1" = "stop" ]; then', lines)
        self.assertIn("touch %s" % bootmode.STOPPING_FLAG, lines)
        self.assertIn("pgrep -f 'main.py daemon'", lines, "ps tronque les lignes : pgrep")


class IntruderTest(unittest.TestCase):
    def test_interface_lancee_derriere_l_ecran(self):
        from rfid.reader_mode import ES_SERVICE, ReaderMode

        home = tempfile.mkdtemp(prefix="rfid-intruder-")
        self.addCleanup(shutil.rmtree, home, True)
        commands, skips = [], []
        es = {"on": False}

        class Process:
            def poll(self):
                return None

            def send_signal(self, sig):
                pass

            def wait(self, timeout=None):
                return 0

        def run(args):
            commands.append(list(args))
            if args[-1] == "stop":
                es["on"] = False

        clock = support.FakeClock()
        mode = ReaderMode(home, None, run=run, running=lambda: es["on"], popen=lambda *a, **k: Process(),
                          clock=clock, sleep=clock.advance, uptime=lambda: 1000.0,
                          hotkey_path=os.path.join(home, "o.cfg"), state_path=os.path.join(home, "es_state.inf"),
                          boot={"skip": lambda: skips.append(1) or True})
        mode.enter()
        commands.clear()
        mode.step()
        self.assertEqual(commands, [], "rien a arreter")
        es["on"] = True
        clock.advance(11)
        mode.step()
        mode._thread.join(5)
        self.assertIn([ES_SERVICE, "stop"], commands)
        self.assertFalse(es["on"])
        self.assertEqual(mode.state, "screen")
        self.assertGreaterEqual(len(skips), 2, "le demarrage direct est remis")


if __name__ == "__main__":
    unittest.main()
