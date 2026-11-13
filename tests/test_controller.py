"""Business logic tests (association, launch, deletion)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support
from rfid.config import Config
from rfid.controller import Controller
from rfid.storage import TagStore

SELECTED_STATE = {
    "Action": "gamelistbrowsing",
    "SystemId": "snes",
    "Game": "Super Mario World",
    "GamePath": "/recalbox/share/roms/snes/Super Mario World.smc",
    "IsFolder": "0",
    "State": "selected",
}


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-ctrl-")
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.launcher = support.FakeLauncher()
        self.feedback = support.FakeFeedback()
        self.clock = support.FakeClock()
        self.state = dict(SELECTED_STATE)
        self.config = Config(os.path.join(self.directory, "config.ini"))
        self.controller = self.make_controller()

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def make_controller(self, config=None, launcher=None):
        return Controller(
            self.store,
            launcher or self.launcher,
            self.feedback,
            config or self.config,
            None,
            state_provider=lambda: self.state,
            clock=self.clock,
        )

    # ------------------------------------------------------------------ button
    def test_appui_sans_jeu_selectionne(self):
        self.state = {}
        self.assertEqual(self.controller.on_button("short"), "no_target")
        self.assertEqual(self.feedback.events, ["error"])
        self.assertFalse(self.controller.armed)

    def test_appui_arme_lassociation(self):
        self.assertEqual(self.controller.on_button("short"), "armed_associate")
        self.assertEqual(self.controller.target.game, "Super Mario World.smc")
        self.assertEqual(self.feedback.events, ["armed"])

    def test_appui_long_arme_la_suppression(self):
        self.assertEqual(self.controller.on_button("long"), "armed_delete")
        self.assertEqual(self.controller.mode, "delete")

    # ------------------------------------------------------------- association
    def test_association_ne_lance_pas_le_jeu(self):
        """Pairing only saves the mapping: no launch."""
        self.controller.on_button("short")
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "bound")
        entry = self.store.get("A1B2C3D4")
        self.assertEqual(entry["system"], "snes")
        self.assertEqual(entry["game"], "Super Mario World.smc")
        self.assertEqual(entry["name"], "Super Mario World")
        self.assertEqual(self.launcher.calls, [], "l'association ne doit rien lancer")
        self.assertFalse(self.controller.armed)
        self.assertIn("ok", self.feedback.events)      # confirmation beeps

    def test_le_scan_suivant_lance_le_jeu(self):
        self.controller.on_button("short")
        self.controller.on_badge("A1B2C3D4")
        self.launcher.calls.clear()
        avant = list(self.feedback.events)
        # Second scan, outside association mode: direct launch
        self.assertEqual(self.controller.on_badge("A1:B2:C3:D4"), "launched")
        self.assertEqual(
            self.launcher.calls, [("snes", "/recalbox/share/roms/snes/Super Mario World.smc")]
        )
        self.assertEqual(self.store.get("A1B2C3D4")["hits"], 1)
        # the launch is visible on screen: no extra beep
        self.assertEqual(self.feedback.events, avant)

    def test_ancien_reglage_ignore(self):
        """A `launch_after_bind = 1` left by an older version is ignored."""
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write("[launch]\nlaunch_after_bind = 1\n")
        self.config.reload()
        controller = self.make_controller()
        controller.on_button("short")
        self.assertEqual(controller.on_badge("A1B2C3D4"), "bound")
        self.assertEqual(self.launcher.calls, [])

    def test_association_refusee_si_nom_avec_pipe(self):
        self.state = dict(SELECTED_STATE, GamePath="/recalbox/share/roms/snes/jeu|bizarre.smc")
        self.controller.on_button("short")
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "failed")
        self.assertEqual(self.store.count(), 0)

    def test_association_sur_la_fiche_d_un_jeu(self):
        """The frontend leaves State=playing on a game page: pairing works."""
        self.state = dict(SELECTED_STATE, State="playing")
        self.assertEqual(self.controller.on_button("short"), "armed_associate")
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "bound")

    def test_journal_explique_l_absence_de_jeu(self):
        """The log says why no game was found (frontend state)."""
        journal = support.RecordingLog()
        controleur = Controller(
            self.store,
            self.launcher,
            self.feedback,
            self.config,
            journal,
            state_provider=lambda: {},
            clock=self.clock,
        )
        self.assertEqual(controleur.on_button("short"), "no_target")
        self.assertTrue(
            any("es_state.inf" in message for _niveau, message in journal.messages),
            journal.messages,
        )

    # --------------------------------------------------------------- lancement
    def test_entree_sans_chemin_utilise_le_nom(self):
        """A pairing made before 2.6.5 has no path: fall back to the name."""
        self.store.put("A1B2C3D4", "snes", "Super Mario World.smc", "Super Mario World")
        self.controller.on_badge("A1B2C3D4")
        self.assertEqual(self.launcher.calls, [("snes", "Super Mario World.smc")])

    def test_badge_inconnu(self):
        self.assertEqual(self.controller.on_badge("FFFFFFFF"), "unknown")
        self.assertEqual(self.feedback.events, ["error"])
        self.assertEqual(self.launcher.calls, [])

    def test_jeu_deja_en_cours(self):
        self.controller.on_button("short")
        self.controller.on_badge("A1B2C3D4")
        self.launcher.calls.clear()
        self.state = dict(SELECTED_STATE, State="playing")
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "ignored")
        self.assertEqual(self.launcher.calls, [])

    def test_echec_du_lancement(self):
        self.controller = self.make_controller(launcher=support.FakeLauncher(ok=False))
        self.controller.on_button("short")
        self.controller.on_badge("A1B2C3D4")
        self.launcher.calls.clear()
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "failed")
        self.assertEqual(self.feedback.events[-1], "error")

    # -------------------------------------------------------------- suppression
    def test_suppression(self):
        self.controller.on_button("short")
        self.controller.on_badge("A1B2C3D4")
        self.assertEqual(self.store.count(), 1)
        self.controller.on_button("long")
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "deleted")
        self.assertEqual(self.store.count(), 0)

    def test_suppression_badge_inconnu(self):
        self.controller.on_button("long")
        self.assertEqual(self.controller.on_badge("FFFFFFFF"), "unknown")

    # ------------------------------------------------------------------ timeout
    def test_expiration(self):
        self.controller.on_button("short")
        self.clock.advance(31)
        self.assertEqual(self.controller.tick(), "expired")
        self.assertFalse(self.controller.armed)
        self.assertIn("timeout", self.feedback.events)

    def test_pas_d_expiration_sans_armement(self):
        self.clock.advance(100)
        self.assertEqual(self.controller.tick(), "")

    def test_status(self):
        self.controller.on_button("short")
        status = self.controller.status()
        self.assertEqual(status["mode"], "associate")
        self.assertIn("snes", status["target"])
        self.assertGreater(status["seconds_left"], 0)


class ActionTest(ControllerTest):
    """Action on scan: start the game, or only confirm."""

    def set_action(self, value):
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write("[launch]\naction = %s\n" % value)
        self.config.reload()
        self.controller = self.make_controller()
        self.controller.store.put("A1B2C3D4", "snes", "Super Mario World.smc", "Mario")
        return self.controller

    def test_action_launch_par_defaut(self):
        self.controller.store.put("A1B2C3D4", "snes", "Super Mario World.smc")
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "launched")
        self.assertEqual(self.launcher.calls[-1][1], "Super Mario World.smc")

    def test_action_none_ne_lance_rien(self):
        controller = self.set_action("none")
        self.assertEqual(controller.on_badge("A1B2C3D4"), "recognized")
        self.assertEqual(self.launcher.calls, [])
        self.assertIn("recognized", self.feedback.events)
        self.assertNotIn("error", self.feedback.events)

    def test_arret_du_jeu_lance_par_le_badge(self):
        self.controller.store.put("A1B2C3D4", "snes", "Super Mario World.smc")
        self.assertEqual(self.controller.on_badge("A1B2C3D4"), "launched")
        self.assertTrue(self.controller.game_running())
        self.assertTrue(self.controller.stop_game())
        self.assertFalse(self.controller.game_running())
        self.assertEqual(self.launcher.stops, 1)

    def test_arret_sans_jeu_en_cours(self):
        journal = support.RecordingLog()
        controleur = Controller(
            self.store,
            self.launcher,
            self.feedback,
            self.config,
            journal,
            state_provider=lambda: self.state,
            clock=self.clock,
        )
        self.assertFalse(controleur.game_running())
        self.assertFalse(controleur.stop_game())
        self.assertTrue(
            any("Aucun jeu en cours" in message for _niveau, message in journal.messages),
            journal.messages,
        )

    def test_arret_apres_le_lancement_remet_l_action_a_zero(self):
        self.controller.store.put("A1B2C3D4", "snes", "Super Mario World.smc")
        self.controller.on_badge("A1B2C3D4")
        self.assertEqual(self.controller.last_action, "launched")
        self.controller.stop_game()
        self.assertEqual(self.controller.last_action, "")

    def test_delai_arme_dix_secondes(self):
        controller = self.make_controller()
        controller.on_button("short")
        self.assertAlmostEqual(controller.arm_timeout_s, 10.0, places=3)


if __name__ == "__main__":
    unittest.main()
