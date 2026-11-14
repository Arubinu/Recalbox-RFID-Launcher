"""Reader mode (reader screen instead of Recalbox's interface) and launch command."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock

import support
from rfid import es_command, reader_mode
from rfid.esbridge import EsLauncher

PAD = {"index": 0, "guid": "0300d0424c050000cc09000011810000",
       "name": "Sony Interactive Entertainment Wireless Controller", "axes": 6, "hats": 1, "buttons": 13}
DEVICE = {"name": PAD["name"], "devicepath": "/dev/input/event0",
          "physicalpath": "platform-3f980000.usb-usb-0:1.4:1.3"}
CONF = {"emulationstation.pad0": "%s:%s" % (PAD["guid"], PAD["name"]),
        "emulationstation.pad0.path": DEVICE["physicalpath"], "global.ratio": "auto",
        "global.videomode": "1280x720"}
GB = {"type": "handheld", "fullname": "Game Boy", "cores": [
    {"emulator": "libretro", "core": "tgbdual", "priority": 2, "videobackend": "default"},
    {"emulator": "libretro", "core": "gambatte", "priority": 1, "videobackend": "default"}]}
#: Command of Recalbox's interface, read on Recalbox 10.1.
REAL = ["python", "/usr/bin/emulatorlauncher.pyc", "-p1index", "0", "-p1guid", PAD["guid"], "-p1name", PAD["name"],
        "-p1nbaxes", "6", "-p1nbhats", "1", "-p1nbbuttons", "13", "-p1devicepath", "/dev/input/event0",
        "-p1physicalpath", DEVICE["physicalpath"], "-system", "gb", "-rom", "/recalbox/share_init/roms/gb/Tuff.gb",
        "-emulator", "libretro", "-core", "gambatte", "-ratio", "auto", "-videobackend", "default", "-rotation", "0",
        "-resolution", "1280x720", "-disabledsoftpatching", "-systemtype", "handheld"]


class CommandTest(unittest.TestCase):
    def build(self, **extra):
        values = dict(conf=CONF, info=GB, meta={}, pads=[PAD], devices=[DEVICE])
        values.update(extra)
        return es_command.build("gb", "/recalbox/share_init/roms/gb/Tuff.gb", **values)

    def test_identique_a_recalbox(self):
        self.assertEqual(self.build(), REAL)
        self.assertEqual(es_command.compare(REAL, self.build()), [])

    def test_choix_du_coeur(self):
        options = es_command.options(self.build(conf=dict(CONF, **{"gb.core": "tgbdual"})))
        self.assertEqual(options["-core"], "tgbdual", "reglage de la console")
        options = es_command.options(self.build(meta={"core": "gambatte", "emulator": "libretro"},
                                                conf=dict(CONF, **{"gb.core": "tgbdual"})))
        self.assertEqual(options["-core"], "gambatte", "le reglage du jeu passe avant")

    def test_ordre_des_manettes(self):
        second = dict(PAD, index=1, guid="03000000aaaa", name="Pad B")
        conf = dict(CONF, **{"emulationstation.pad0": "03000000aaaa:Pad B", "emulationstation.pad1": CONF["emulationstation.pad0"]})
        options = es_command.options(self.build(conf=conf, pads=[PAD, second],
                                                devices=[DEVICE, {"name": "Pad B", "devicepath": "/dev/input/event5", "physicalpath": "usb-2"}]))
        self.assertEqual(options["-p1name"], "Pad B", "joueur 1 : la manette choisie dans Recalbox")
        self.assertEqual(options["-p1index"], "1")
        self.assertEqual(options["-p2devicepath"], "/dev/input/event0")

    def test_differences_signalees(self):
        mine = self.build(conf=dict(CONF, **{"global.ratio": "16/9"}))
        self.assertEqual(es_command.compare(REAL, mine), [("-ratio", "auto", "16/9")])

    def test_manette_detectee_en_32_bits(self):
        base = tempfile.mkdtemp(prefix="rfid-input-")
        self.addCleanup(shutil.rmtree, base, True)
        os.makedirs(os.path.join(base, "capabilities"))
        with open(os.path.join(base, "capabilities", "key"), "w") as handle:
            handle.write("7fdb0000 0 0 0 0 0 0 0 0 0\n")  # a DS4 seen by a Pi 3 (32-bit words)
        self.assertTrue(es_command._is_joystick(base, word_bits=32))
        with open(os.path.join(base, "capabilities", "key"), "w") as handle:
            handle.write("2420 0 10000 0 0 0 0 0 0 0 0\n")  # its touchpad
        self.assertFalse(es_command._is_joystick(base, word_bits=32))


class CommandCheckTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-check-")
        self.addCleanup(shutil.rmtree, self.home, True)

    def test_identique(self):
        result = es_command.check(REAL, built=list(REAL), now=lambda: 5)
        self.assertEqual((result["same"], result["system"], result["game"]), (True, "gb", "Tuff.gb"))
        es_command.record(self.home, result)
        self.assertEqual(es_command.summary(self.home)["different"], 0)

    def test_difference_gardee(self):
        ours = [part if part != "auto" else "16/9" for part in REAL]
        result = es_command.check(REAL, built=ours)
        self.assertFalse(result["same"])
        self.assertEqual(result["differences"], [{"option": "-ratio", "recalbox": "auto", "reader": "16/9"}])
        for _ in range(es_command.KEEP_CHECKS + 3):
            es_command.record(self.home, es_command.check(REAL, built=list(REAL)))
        es_command.record(self.home, result)
        summary = es_command.summary(self.home)
        self.assertEqual(summary["checked"], es_command.KEEP_CHECKS, "les plus anciens partent")
        self.assertEqual(summary["last_different"]["differences"][0]["option"], "-ratio")

    def test_commande_lue_dans_proc(self):
        proc = tempfile.mkdtemp(prefix="rfid-proc-")
        self.addCleanup(shutil.rmtree, proc, True)
        os.makedirs(os.path.join(proc, "4242"))
        with open(os.path.join(proc, "4242", "cmdline"), "wb") as handle:
            handle.write(b"\0".join(part.encode() for part in REAL) + b"\0")
        with mock.patch("rfid.esbridge.emulator_pids", return_value=[4242]):
            self.assertEqual(es_command.running_command(proc_dir=proc), REAL)
        self.assertIsNone(es_command.running_command(proc_dir=os.path.join(proc, "none")))


class FakeProcess:
    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.code = None
        self.signals = []

    def poll(self):
        return self.code

    def send_signal(self, sig):
        self.signals.append(sig)
        self.code = 0

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code = -9


class ReaderModeTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-reader-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.calls = []
        self.frontend = {"up": True, "quits_after": 0, "checks": 0}
        self.processes = []
        self.clock = support.FakeClock()
        self.hotkeys = os.path.join(self.home, "overrides.cfg")
        with open(self.hotkeys, "w", encoding="utf-8") as handle:
            handle.write('video_smooth = "true"\n')
        self.state = os.path.join(self.home, "es_state.inf")
        self.mode = reader_mode.ReaderMode(self.home, None, run=self.fake_run, running=self.running, popen=self.popen,
                                           clock=self.clock, sleep=self.clock.advance, python="python3",
                                           hotkey_path=self.hotkeys, state_path=self.state)
        patcher = mock.patch.object(es_command, "build", side_effect=lambda system, rom: ["python", "launcher", "-rom", rom])
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("launch_env",):
            p = mock.patch.object(es_command, name, return_value={})
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(es_command, "systems", return_value={"gb": GB})
        p.start()
        self.addCleanup(p.stop)

    def fake_run(self, args):
        self.calls.append(args[1])
        if args[1] == "start":
            self.frontend["up"] = True
            self.frontend["checks"] = 0

    def running(self):
        if self.frontend["up"] and self.calls and self.calls[-1] == "stop":
            self.frontend["checks"] += 1
            if self.frontend["checks"] > self.frontend["quits_after"]:
                self.frontend["up"] = False
        return self.frontend["up"]

    def popen(self, argv, **kwargs):
        process = FakeProcess(argv)
        self.processes.append(process)
        return process

    def enter(self):
        self.mode.wanted = True
        self.mode.enter()

    def test_entree_attend_l_arret_reel(self):
        self.frontend["quits_after"] = 50  # 25 s, longer than the init script waits
        self.enter()
        self.assertEqual(self.calls, ["stop"])
        self.assertFalse(self.frontend["up"])
        self.assertEqual(self.mode.state, "screen")
        self.assertIn("screen", self.processes[0].argv)

    def test_lancement_puis_retour_a_l_ecran(self):
        self.enter()
        screen = self.processes[0]
        self.assertTrue(self.mode.launch("gb", "/roms/gb/Tuff.gb"))
        self.assertEqual(screen.signals, [reader_mode.signal.SIGTERM], "l'ecran libere l'affichage")
        self.assertEqual(self.mode.state, "game")
        self.assertIn("State=playing", open(self.state, encoding="utf-8").read())
        game = self.processes[1]
        self.assertEqual(game.argv[-1], "/roms/gb/Tuff.gb")
        self.mode.step()
        self.assertEqual(self.mode.state, "game", "le jeu tourne")
        game.code = 0
        self.mode.step()
        self.assertEqual(self.mode.state, "screen")
        self.assertIn("State=selected", open(self.state, encoding="utf-8").read())
        self.assertEqual(len(self.processes), 3, "l'ecran revient")

    def test_raccourci_desactive_seulement_pendant_le_jeu(self):
        self.mode.no_quit_hotkey = True
        self.enter()
        self.mode.launch("gb", "/roms/gb/Tuff.gb")
        text = open(self.hotkeys, encoding="utf-8").read()
        self.assertIn('input_exit_emulator_btn = "nul"', text)
        self.assertIn('video_smooth = "true"', text, "les reglages de l'utilisateur restent")
        self.processes[1].code = 0
        self.mode.step()
        self.assertEqual(open(self.hotkeys, encoding="utf-8").read(), 'video_smooth = "true"\n')

    def test_pas_de_lancement_hors_du_mode(self):
        self.assertFalse(self.mode.launch("gb", "/roms/gb/Tuff.gb"))
        self.assertEqual(self.processes, [])

    def test_sortie_relance_recalbox(self):
        self.enter()
        self.mode.wanted = False
        self.mode.leave()
        self.assertEqual(self.calls, ["stop", "start"])
        self.assertTrue(self.frontend["up"])
        self.assertEqual(self.mode.state, "recalbox")
        self.assertEqual(self.processes[0].signals, [reader_mode.signal.SIGTERM])

    def test_ecran_qui_plante_sans_cesse(self):
        self.enter()
        with mock.patch.object(self.mode, "_switch") as switch:
            for _ in range(reader_mode.MAX_CRASHES):
                self.processes[-1].code = 1
                self.mode.step()
        switch.assert_called_once_with(False)
        self.assertFalse(self.mode.wanted)

    def test_lanceur_passe_par_le_mode(self):
        launcher = EsLauncher("127.0.0.1", 1)
        launcher.reader = self.mode
        self.enter()
        self.assertTrue(launcher.start_game("gb", "/roms/gb/Tuff.gb"))
        self.assertEqual(self.mode.state, "game")


class HotkeyBlockTest(unittest.TestCase):
    def test_ajout_et_retrait(self):
        home = tempfile.mkdtemp(prefix="rfid-hotkey-")
        self.addCleanup(shutil.rmtree, home, True)
        path = os.path.join(home, "missing.cfg")
        self.assertTrue(reader_mode.set_hotkey_block(True, path))
        self.assertFalse(reader_mode.set_hotkey_block(True, path), "deja en place")
        self.assertTrue(reader_mode.set_hotkey_block(False, path))
        self.assertEqual(open(path, encoding="utf-8").read(), "")


if __name__ == "__main__":
    unittest.main()
