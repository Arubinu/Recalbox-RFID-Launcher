"""Tests de l'interface avec le frontend Recalbox (etat + commande UDP)."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import unittest

import support  # noqa: F401
from rfid.esbridge import (
    EsLauncher,
    current_target,
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
        # Systeme "arcade" range dans le dossier "mame"
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

    def test_jeu_en_cours(self):
        self.assertTrue(game_is_running(self.state(State="playing")))
        self.assertFalse(game_is_running(self.state()))
        self.assertFalse(game_is_running(None))


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
