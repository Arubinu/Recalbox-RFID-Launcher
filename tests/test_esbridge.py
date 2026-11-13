"""Tests of the interface with the Recalbox frontend (state + UDP command)."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import unittest
from unittest import mock

import support  # noqa: F401
from rfid import esbridge
from rfid.esbridge import (
    emulator_pids,
    EsLauncher,
    current_target,
    describe_state,
    state_snapshot,
    game_is_running,
    read_state,
    relative_game_key,
)


class ReadStateTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-state-")
        self.path = os.path.join(self.directory, "es_state.inf")

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_fichier_absent(self):
        self.assertIsNone(read_state(self.path))

    def test_lecture_crlf_et_derniere_valeur(self):
        with open(self.path, "w", encoding="utf-8", newline="") as handle:
            handle.write("Version=2.0\r\nAction=gamelistbrowsing\r\nSystemId=snes\r\n")
            handle.write("Game=Super Mario World\r\nEmulator=libretro\r\nEmulator=other\r\n")
        state = read_state(self.path)
        self.assertEqual(state["Action"], "gamelistbrowsing")
        self.assertEqual(state["SystemId"], "snes")
        self.assertEqual(state["Emulator"], "other")


class RelativeKeyTest(unittest.TestCase):
    def test_chemin_standard(self):
        self.assertEqual(
            relative_game_key("snes", "/recalbox/share/roms/snes/Super Mario World.smc"),
            "Super Mario World.smc",
        )

    def test_sous_dossier(self):
        self.assertEqual(
            relative_game_key("snes", "/recalbox/share/roms/snes/Classiques/jeu.smc"),
            "Classiques/jeu.smc",
        )

    def test_dossier_systeme_different(self):
        # "arcade" system stored in the "mame" folder
        self.assertEqual(
            relative_game_key("arcade", "/recalbox/share/roms/mame/pacman.zip"),
            "pacman.zip",
        )

    def test_support_externe(self):
        self.assertEqual(
            relative_game_key("snes", "/recalbox/share/externals/usb0/roms/snes/jeu.smc"),
            "jeu.smc",
        )

    def test_chemin_inconnu(self):
        self.assertEqual(relative_game_key("snes", "/media/jeu.smc"), "jeu.smc")


class CurrentTargetTest(unittest.TestCase):
    def state(self, **overrides):
        base = {
            "Action": "gamelistbrowsing",
            "SystemId": "snes",
            "Game": "Super Mario World",
            "GamePath": "/recalbox/share/roms/snes/Super Mario World.smc",
            "IsFolder": "0",
            "State": "selected",
        }
        base.update(overrides)
        return base

    def test_jeu_selectionne(self):
        target = current_target(self.state())
        self.assertIsNotNone(target)
        self.assertEqual(target.system, "snes")
        self.assertEqual(target.game, "Super Mario World.smc")
        self.assertEqual(target.name, "Super Mario World")

    def test_dossier_ignore(self):
        self.assertIsNone(current_target(self.state(IsFolder="1")))

    def test_jeu_en_cours_ignore(self):
        self.assertIsNone(current_target(self.state(State="playing")))

    def test_demo_ignoree(self):
        self.assertIsNone(current_target(self.state(State="demo")))

    def test_champs_vides(self):
        self.assertIsNone(current_target(self.state(SystemId="", GamePath="")))
        self.assertIsNone(current_target(None))

    def test_association_accepte_le_jeu_affiche(self):
        """On a game page, the frontend leaves State=playing: it is accepted."""
        cible = current_target(self.state(State="playing"), allow_running=True)
        self.assertIsNotNone(cible)
        self.assertEqual(cible.game, "Super Mario World.smc")
        # for badge launches, the filter stays active
        self.assertIsNone(current_target(self.state(State="playing")))

    def test_cles_de_remplacement(self):
        """Frontend versions do not all use the same keys."""
        state = {
            "System": "snes",
            "Path": "/recalbox/share/roms/snes/Super Mario World.smc",
            "Game": "Super Mario World",
        }
        cible = current_target(state)
        self.assertIsNotNone(cible)
        self.assertEqual(cible.system, "snes")
        self.assertEqual(cible.game, "Super Mario World.smc")

    def test_type_folder_ignore(self):
        self.assertIsNone(current_target(self.state(Type="folder")))
        self.assertIsNone(current_target(self.state(Type="empty")))

    def test_diagnostic_de_l_etat(self):
        self.assertIn("absent", describe_state(None))
        texte = describe_state(self.state(State="playing"))
        self.assertIn("State='playing'", texte)
        self.assertIn("GamePath=", texte)

    def test_instantane_tronque(self):
        resume = state_snapshot({"GamePath": "x" * 400}, limite=20)
        self.assertEqual(len(resume["GamePath"]), 20)
        self.assertTrue(resume["GamePath"].endswith("…"))
        self.assertEqual(state_snapshot(None), {})

    def test_chemin_reconstruit(self):
        """Manual addition: the full path is rebuilt for the frontend."""
        from rfid.esbridge import resolve_rom_path

        self.assertEqual(
            resolve_rom_path("snes", "Super Mario World.smc"),
            "/recalbox/share/roms/snes/Super Mario World.smc",
        )
        self.assertEqual(
            resolve_rom_path("snes", "/recalbox/share_init/roms/snes/x.smc"),
            "/recalbox/share_init/roms/snes/x.smc",
        )
        self.assertEqual(resolve_rom_path("", "x.smc"), "")

    def test_jeu_en_cours(self):
        self.assertTrue(game_is_running(self.state(State="playing")))
        self.assertFalse(game_is_running(self.state()))
        self.assertFalse(game_is_running(None))


class EmulatorProcessTest(unittest.TestCase):
    """Detection of the emulators to stop (fake /proc)."""

    def setUp(self):
        self.proc = tempfile.mkdtemp(prefix="rfid-proc-")
        self.addCleanup(shutil.rmtree, self.proc, True)

    def ajouter(self, pid, ligne):
        dossier = os.path.join(self.proc, str(pid))
        os.makedirs(dossier)
        with open(os.path.join(dossier, "cmdline"), "wb") as handle:
            handle.write(ligne.encode("utf-8").replace(b" ", b"\x00"))

    def test_detecte_retroarch(self):
        self.ajouter(4242, "/usr/bin/retroarch -L /usr/lib/libretro/snes9x.so")
        self.assertEqual(emulator_pids(proc_dir=self.proc), [4242])

    def test_ignore_le_frontend(self):
        self.ajouter(1100, "/usr/bin/emulationstation --log-file /tmp/es.log")
        self.assertEqual(emulator_pids(proc_dir=self.proc), [])

    def test_ignore_un_processus_sans_rapport(self):
        # "service" contains "vice": filtering must use the program name,
        # never the whole line.
        self.ajouter(900, "/usr/bin/python3 /usr/bin/service-helper --all")
        self.ajouter(901, "/usr/sbin/rpc.statd")
        self.assertEqual(emulator_pids(proc_dir=self.proc), [])

    def test_ignore_son_propre_pid(self):
        self.ajouter(os.getpid(), "/usr/bin/retroarch")
        self.assertEqual(emulator_pids(proc_dir=self.proc), [])

    def test_detecte_par_le_chemin_du_jeu(self):
        rom = "/recalbox/share/roms/snes/Super Mario World.smc"
        self.ajouter(5000, "/usr/bin/monemu %s" % rom)
        self.assertEqual(emulator_pids(rom, proc_dir=self.proc), [5000])
        self.assertEqual(emulator_pids("", proc_dir=self.proc), [])

    def test_detecte_emulatorlauncher(self):
        self.ajouter(5100, "/usr/bin/python3 /usr/bin/emulatorlauncher -system snes -rom jeu.smc")
        self.assertEqual(emulator_pids(proc_dir=self.proc), [5100])

    def test_dossier_absent(self):
        self.assertEqual(emulator_pids(proc_dir=os.path.join(self.proc, "absent")), [])

    def test_entrees_non_numeriques(self):
        self.ajouter(600, "/usr/bin/retroarch")
        os.makedirs(os.path.join(self.proc, "sys"))
        self.assertEqual(emulator_pids(proc_dir=self.proc), [600])

    def test_game_running(self):
        launcher = EsLauncher("127.0.0.1", 1337)
        with mock.patch.object(esbridge, "emulator_pids", return_value=[7]):
            self.assertTrue(launcher.game_running())
        with mock.patch.object(esbridge, "emulator_pids", return_value=[]):
            self.assertFalse(launcher.game_running())


class StopGameTest(unittest.TestCase):
    """Stopping the game: SIGTERM, then SIGKILL if the emulator resists."""

    def setUp(self):
        self.launcher = EsLauncher("127.0.0.1", 1337)
        self.signaux = []
        self.patch_kill = mock.patch.object(esbridge, "_kill", side_effect=self.noter)
        self.patch_kill.start()
        self.addCleanup(self.patch_kill.stop)
        self.patch_sleep = mock.patch.object(esbridge.time, "sleep")
        self.patch_sleep.start()
        self.addCleanup(self.patch_sleep.stop)

    def noter(self, pid, sig):
        self.signaux.append((pid, sig))

    def test_arret_propre(self):
        with mock.patch.object(esbridge, "emulator_pids", side_effect=[[11, 22], [], []]):
            self.assertTrue(self.launcher.stop_game())
        self.assertEqual(self.signaux, [(11, esbridge.SIG_TERM), (22, esbridge.SIG_TERM)])

    def test_aucun_emulateur(self):
        with mock.patch.object(esbridge, "emulator_pids", return_value=[]):
            self.assertFalse(self.launcher.stop_game())
        self.assertEqual(self.signaux, [])

    def test_emulateur_qui_resiste(self):
        with mock.patch.object(esbridge, "emulator_pids", return_value=[33]):
            self.assertTrue(self.launcher.stop_game(timeout_s=0.0))
        self.assertEqual(self.signaux, [(33, esbridge.SIG_TERM), (33, esbridge.SIG_KILL)])


class PayloadTest(unittest.TestCase):
    def test_trame(self):
        self.assertEqual(
            EsLauncher.build_payload("snes", "Super Mario World.smc"),
            b"START|snes|Super Mario World.smc",
        )

    def test_accents(self):
        payload = EsLauncher.build_payload("snes", "Pokemon.smc")
        self.assertEqual(payload, b"START|snes|" + os.fsencode("Pokemon.smc"))
        accented = EsLauncher.build_payload("snes", "Pokémon.smc")
        self.assertEqual(accented, b"START|snes|" + os.fsencode("Pokémon.smc"))

    def test_caractere_interdit(self):
        with self.assertRaises(ValueError):
            EsLauncher.build_payload("snes", "jeu|interdit.smc")
        with self.assertRaises(ValueError):
            EsLauncher.build_payload("", "jeu.smc")


class UdpSendTest(unittest.TestCase):
    def test_envoi_reel(self):
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2.0)
        port = receiver.getsockname()[1]
        try:
            launcher = EsLauncher("127.0.0.1", port)
            self.assertTrue(launcher.start_game("snes", "Super Mario World.smc"))
            payload, _ = receiver.recvfrom(2048)
            self.assertEqual(payload, b"START|snes|Super Mario World.smc")
        finally:
            receiver.close()


if __name__ == "__main__":
    unittest.main()
