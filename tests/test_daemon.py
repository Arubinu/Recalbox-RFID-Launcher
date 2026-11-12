"""Tests des utilitaires du service (fichiers d'etat, verrou)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support  # noqa: F401
from rfid.daemon import (
    acquire_lock,
    pid_path,
    read_pid,
    read_status,
    release_lock,
    write_json_atomic,
)


class DaemonHelpersTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-daemon-")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_pid_absent(self):
        self.assertEqual(read_pid(self.home), 0)

    def test_pid_present(self):
        with open(pid_path(self.home), "w", encoding="ascii") as handle:
            handle.write("12345\n")
        self.assertEqual(read_pid(self.home), 12345)

    def test_pid_invalide(self):
        with open(pid_path(self.home), "w", encoding="ascii") as handle:
            handle.write("pas un nombre")
        self.assertEqual(read_pid(self.home), 0)

    def test_ecriture_atomique_et_lecture(self):
        write_json_atomic(os.path.join(self.home, "status.json"), {"pid": 42, "tags": 3})
        status = read_status(self.home)
        self.assertEqual(status["pid"], 42)
        self.assertEqual(status["tags"], 3)

    def test_status_absent(self):
        self.assertIsNone(read_status(self.home))

    def test_status_corrompu(self):
        with open(os.path.join(self.home, "status.json"), "w", encoding="utf-8") as handle:
            handle.write("{ coupe")
        self.assertIsNone(read_status(self.home))

    def test_verrou(self):
        lock = acquire_lock(os.path.join(self.home, "test.lock"))
        if lock == -1:
            self.skipTest("verrou non disponible sur cette plateforme")
        try:
            self.assertNotEqual(lock, 0)
        finally:
            release_lock(lock)



class ReleaseGestureTest(unittest.TestCase):
    """Les gestes sont traites au relachement, jamais au contact."""

    def setUp(self):
        from unittest import mock as _mock

        from rfid import daemon as _daemon

        self._daemon = _daemon
        self.service = _daemon.Service.__new__(_daemon.Service)
        self.service.home = tempfile.mkdtemp(prefix="rfid-gesture-")
        self.service.log = None
        self.service._press_started_at = None
        self.service._active_uid = "A1B2C3D4"
        self.service._absent_since = None
        self.armements = []
        self.service.controller = _mock.Mock()
        self.service.controller.on_button = lambda geste: self.armements.append(geste)

    def tearDown(self):
        shutil.rmtree(self.service.home, ignore_errors=True)

    def test_appui_court_arme_a_l_association(self):
        self.service._handle_gesture("short")
        self.assertEqual(self.armements, ["short"])

    def test_geste_long_ignore(self):
        """Le geste "long" n'existe plus : il ne doit rien armer du tout."""
        self.service._handle_gesture("long")
        self.assertEqual(self.armements, [])

    def test_armer_oublie_le_badge_deja_pose(self):
        self.service._handle_gesture("short")
        self.assertIsNone(self.service._active_uid)


class ReaderTestTest(unittest.TestCase):
    """Test du lecteur : distingue "aucune carte", "carte vue" et "carte illisible"."""

    def setUp(self):
        from unittest import mock as _mock

        from rfid import daemon as _daemon

        self.daemon = _daemon
        self.service = _daemon.Service.__new__(_daemon.Service)
        self.service.home = tempfile.mkdtemp(prefix="rfid-rtest-")
        self.service.log = None
        self.service._reader_test = None
        self.service.reader = _mock.Mock()
        self.service.reader.version = 0x92
        self.now = 100.0
        self._patch = _mock.patch.object(_daemon.time, "monotonic", side_effect=lambda: self.now)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.service.home, ignore_errors=True)

    def _run(self, read_uid, request, passes=4):
        chip = self.service.reader.rc522
        chip.read_uid.return_value = read_uid
        chip.request.return_value = request
        self.service._start_reader_test(5)
        for _ in range(passes):
            self.service._reader_test_step()
        self.service._finish_reader_test()
        import json

        path = os.path.join(self.service.home, self.daemon.READER_TEST_FILENAME)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_uid_lu(self):
        result = self._run(b"\xa1\xb2\xc3\xd4", None)
        self.assertTrue(result["finished"])
        self.assertEqual(result["uids"], ["A1B2C3D4"])
        self.assertEqual(result["answers"], 4)
        self.assertTrue(result["reader_ready"])
        self.assertEqual(result["version"], 0x92)

    def test_aucune_carte(self):
        result = self._run(None, None)
        self.assertEqual(result["uids"], [])
        self.assertEqual(result["atqas"], {})
        self.assertEqual(result["answers"], 0)
        self.assertEqual(result["attempts"], 4)
        self.assertTrue(result["reader_ready"])

    def test_carte_vue_mais_illisible(self):
        result = self._run(None, b"\x00\x04")
        self.assertEqual(result["uids"], [])
        self.assertEqual(result["atqas"], {"0004": 4})
        self.assertEqual(result["answers"], 4)
        self.assertEqual(result["reqa"], 4)

    def test_lecteur_indisponible(self):
        self.service.reader = None
        self.service._start_reader_test(5)
        self.service._reader_test_step()
        import json

        path = os.path.join(self.service.home, self.daemon.READER_TEST_FILENAME)
        with open(path, encoding="utf-8") as handle:
            result = json.load(handle)
        self.assertFalse(result["reader_ready"])
        self.assertTrue(result["errors"])

    def test_delai_borne(self):
        self.service._start_reader_test(500)
        self.assertLessEqual(self.service._reader_test["seconds"], 15.0)
        self.service._start_reader_test(0)
        self.assertGreaterEqual(self.service._reader_test["seconds"], 2.0)


class BadgeLatchTest(unittest.TestCase):
    """Mode "cartouche" : un badge laisse sur le lecteur n'agit qu'une fois."""

    #: Service construit sans materiel : on ne teste que la logique de presence.
    def setUp(self):
        from unittest import mock as _mock

        from rfid import daemon as _daemon

        self.daemon = _daemon
        self.service = _daemon.Service.__new__(_daemon.Service)
        self.service.home = tempfile.mkdtemp(prefix="rfid-latch-")
        self.service.log = None
        self.service.rearm_absent_ms = 1200.0
        self.service._active_uid = None
        self.service._absent_since = None
        self.service._absent_hits = 0
        self.service._active_seen_at = 0.0
        self.service._last_read_at = 0.0
        self.service._action_at = 0.0
        self.service._launched_uid = None
        self.service._stop_pending = None
        self.service._stop_on_remove = False
        self.service.last_uid = None
        self.service.last_uid_at = 0
        self.actions = []
        self.service.controller = _mock.Mock()
        self.service.controller.last_action = ""
        self.service.controller.on_badge = lambda uid: self.actions.append(uid)
        self.service.reader = _mock.Mock()
        self.service.reader.tag_present.return_value = True
        self.now = 100.0
        self._patch = _mock.patch.object(_daemon.time, "monotonic", side_effect=lambda: self.now)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(shutil.rmtree, self.service.home, True)

    def avancer(self, secondes):
        self.now += secondes

    def presence(self, verdict):
        self.service.reader.tag_present.return_value = verdict

    def laisse_tourner(self, secondes, pas=0.15):
        """Fait tourner la boucle du service (presence + arret differe)."""
        reste = secondes
        while reste > 0:
            self.now += pas
            self.service._check_presence()
            self.service._service_stop()
            reste -= pas

    # ------------------------------------------------------------- verrou
    def test_badge_laisse_n_agit_qu_une_fois(self):
        for _ in range(6):
            self.service._badge_seen("A1B2C3D4")
            self.avancer(0.15)
            self.service._check_presence()
        self.assertEqual(self.actions, ["A1B2C3D4"])

    def test_lecture_ratee_n_est_pas_un_retrait(self):
        # L'anti-rebond du lecteur renvoie None pendant 2,5 s : ce silence ne
        # doit jamais passer pour un badge retire (sinon le jeu se relancait).
        self.service._badge_seen("A1B2C3D4")
        self.presence(True)
        self.laisse_tourner(6.0)
        self.assertEqual(self.actions, ["A1B2C3D4"])

    def test_lecteur_muet_ne_conclut_pas(self):
        self.service._badge_seen("A1B2C3D4")
        self.presence(None)
        self.laisse_tourner(10.0)
        self.assertEqual(self.service._active_uid, "A1B2C3D4")

    def test_badge_retire_puis_repose_refait_l_action(self):
        self.service._badge_seen("A1B2C3D4")
        self.presence(False)
        self.laisse_tourner(6.0)   # 3 s de grace + 2 s d'absence confirmee
        self.assertIsNone(self.service._active_uid)
        self.presence(True)
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4", "A1B2C3D4"])

    def test_absence_trop_courte_ne_rearme_pas(self):
        self.service._badge_seen("A1B2C3D4")
        self.presence(False)
        self.laisse_tourner(1.0)
        self.presence(True)
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4"])

    def test_absence_exigee_au_moins_deux_secondes(self):
        self.service._badge_seen("A1B2C3D4")
        self.presence(False)
        self.laisse_tourner(1.5)   # > rearm_absent_ms (1,2 s) mais < 2 s
        self.assertEqual(self.service._active_uid, "A1B2C3D4")

    def test_grace_apres_lancement(self):
        # Un badge qui disparait juste apres le lancement ne doit pas defaire
        # l'action (demarrage de l'emulateur, badge mal pose une seconde...).
        self.service._badge_seen("A1B2C3D4")
        self.presence(False)
        self.laisse_tourner(2.5)
        self.assertEqual(self.service._active_uid, "A1B2C3D4")
        self.laisse_tourner(3.0)
        self.assertIsNone(self.service._active_uid)

    def test_autre_badge_agit_immediatement(self):
        self.service._badge_seen("A1B2C3D4")
        self.service._badge_seen("11223344")
        self.assertEqual(self.actions, ["A1B2C3D4", "11223344"])

    def test_etat_du_badge_oublie_pour_un_mode_arme(self):
        self.service._badge_seen("A1B2C3D4")
        self.service._forget_latch()
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4", "A1B2C3D4"])


class AdoptAfterTestTest(BadgeLatchTest):
    """Apres un test ou une mesure, le badge pose ne doit pas agir."""

    def test_badge_pose_apres_une_mesure_n_agit_pas(self):
        self.service._calibration = None
        self.service._arm_adoption()
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, [])
        self.assertEqual(self.service._active_uid, "A1B2C3D4")
        self.assertFalse(self.service._adopt_next_read)

    def test_le_badge_reste_verrouille_ensuite(self):
        self.service._arm_adoption()
        self.service._badge_seen("A1B2C3D4")
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, [])

    def test_retirer_puis_reposer_agit(self):
        self.service._arm_adoption()
        self.service._badge_seen("A1B2C3D4")
        self.presence(False)
        self.laisse_tourner(6.0)
        self.presence(True)
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4"])

    def test_un_autre_badge_agit_immediatement(self):
        self.service._arm_adoption()
        self.service._badge_seen("A1B2C3D4")
        self.service._badge_seen("11223344")
        self.assertEqual(self.actions, ["11223344"])

    def test_un_mode_arme_peut_representer_le_badge(self):
        self.service._arm_adoption()
        self.service._forget_latch()
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4"])

    def test_l_adoption_expire(self):
        # Un badge pose bien apres la mesure doit agir normalement.
        self.service._arm_adoption(secondes=1.0)
        self.avancer(5.0)
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4"])
        self.assertFalse(self.service._adopt_next_read)

    def test_sans_drapeau_le_badge_agit(self):
        self.service._adopt_next_read = False
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4"])


class StopOnRemoveTest(BadgeLatchTest):
    """Option « quitter le jeu quand le badge est retire »."""

    def setUp(self):
        super().setUp()
        self.service._stop_on_remove = True
        self.service.controller.last_action = "launched"
        self.service.controller.game_running.return_value = True

    def retirer_le_badge(self):
        self.presence(False)
        # 3 s de grace apres le lancement + 2 s d'absence confirmee.
        self.laisse_tourner(6.0)

    def test_le_jeu_est_arrete_quand_le_badge_est_retire(self):
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.service.controller.stop_game.assert_called_once_with()

    def test_badge_laisse_n_arrete_rien(self):
        self.service._badge_seen("A1B2C3D4")
        self.laisse_tourner(8.0)
        self.service.controller.stop_game.assert_not_called()

    def test_option_desactivee_n_arrete_rien(self):
        self.service._stop_on_remove = False
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.service.controller.stop_game.assert_not_called()

    def test_sans_lancement_rien_a_arreter(self):
        self.service.controller.last_action = "recognized"
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.service.controller.stop_game.assert_not_called()

    def test_arret_attend_le_demarrage_de_l_emulateur(self):
        self.service.controller.game_running.return_value = False
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.service.controller.stop_game.assert_not_called()
        # L'emulateur finit par demarrer : le service l'arrete alors.
        self.service.controller.game_running.return_value = True
        self.laisse_tourner(0.5)
        self.service.controller.stop_game.assert_called_once_with()

    def test_arret_abandonne_si_aucun_jeu_ne_demarre(self):
        self.service.controller.game_running.return_value = False
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.laisse_tourner(self.daemon.Service.STOP_WAIT_S + 1.0)
        self.service.controller.stop_game.assert_not_called()
        self.assertIsNone(self.service._stop_pending)

    def test_un_seul_arret_par_retrait(self):
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.laisse_tourner(3.0)
        self.service.controller.stop_game.assert_called_once_with()

    def test_erreur_d_arret_non_bloquante(self):
        self.service.controller.stop_game.side_effect = RuntimeError("boom")
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()  # ne doit pas lever
        self.assertIsNone(self.service._active_uid)

    def test_retrait_puis_repose_relance_le_jeu(self):
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.presence(True)
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4", "A1B2C3D4"])


if __name__ == "__main__":
    unittest.main()
