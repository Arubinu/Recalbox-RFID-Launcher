"""Service utility tests (state files, lock)."""

from __future__ import annotations

import json
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
    """Gestures are handled on release, never on contact."""

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
        """The "long" gesture no longer exists: it must arm nothing at all."""
        self.service._handle_gesture("long")
        self.assertEqual(self.armements, [])

    def prepare_double(self, card=True, running=True):
        from unittest import mock as _mock

        controller = self.service.controller
        controller.game_card = lambda uid: {"system": "gb", "game": "Tuff.gb"} if card else None
        controller.game_running = _mock.Mock(return_value=running)
        controller.new_game = _mock.Mock(return_value="launched")
        self.service.players = None
        self.service.feedback = _mock.Mock()
        self.service.light = None
        self.service.log = _mock.Mock()
        self.service._new_game = None
        self.service._skip_resume = False
        self.service._launched_uid = None
        self.service.screen = None
        self.service.launcher = _mock.Mock()
        self.service.launcher.reset_command = lambda: False  # not a RetroArch game

    def test_double_appui_nouvelle_partie(self):
        self.prepare_double()
        self.service._handle_gesture("double")
        self.service.controller.stop_game.assert_called_once_with("new")
        self.assertEqual(self.armements, [], "pas d'association")
        self.assertTrue(self.service._skip_resume)
        job = self.service._new_game
        self.assertEqual(job["uid"], "A1B2C3D4")
        # The frontend is back to its menu: the game starts again.
        job["at"] = 0
        self.service.controller.game_running.return_value = False
        self.service._new_game_step()
        self.service.controller.new_game.assert_called_once_with("A1B2C3D4", None)
        self.assertEqual(self.service._launched_uid, "A1B2C3D4")
        job["at"] = 0
        self.service.controller.game_running.return_value = True
        self.service._new_game_step()
        self.assertIsNone(self.service._new_game, "partie relancee")

    def test_double_appui_retroarch_recommence_sur_place(self):
        from unittest import mock as _mock

        self.prepare_double()
        resets = []
        self.service.launcher.reset_command = lambda: resets.append(1) or True
        self.service.screen = _mock.Mock()
        self.service._handle_gesture("double")
        self.assertEqual(resets, [1])
        self.service.controller.stop_game.assert_not_called()
        self.assertIsNone(self.service._new_game, "ni quitte ni relance")
        self.assertFalse(self.service._skip_resume)
        self.service.screen.say.assert_called_once_with("new_game")

    def test_double_appui_sans_carte_de_jeu(self):
        self.prepare_double(card=False)
        self.service._handle_gesture("double")
        self.assertEqual(self.armements, ["short"], "comme un appui court")
        self.assertIsNone(self.service._new_game)

    def test_armer_oublie_le_badge_deja_pose(self):
        self.service._handle_gesture("short")
        self.assertIsNone(self.service._active_uid)


class ReaderTestTest(unittest.TestCase):
    """Reader test: tells "no card", "card seen" and "unreadable card" apart."""

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
    """"Cartridge" mode: a badge left on the reader acts only once."""

    #: Service built without hardware: only the presence logic is tested.
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
        """Runs the service loop (presence + delayed stop)."""
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
        # The reader debounce returns None for 2.5 s: this silence must never
        # look like a removed badge (otherwise the game started again).
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
        self.laisse_tourner(6.0)   # 3 s grace + 2 s of confirmed absence
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
        self.laisse_tourner(1.5)   # > rearm_absent_ms (1.2 s) but < 2 s
        self.assertEqual(self.service._active_uid, "A1B2C3D4")

    def test_grace_apres_lancement(self):
        # A badge that disappears right after the launch must not undo the
        # action (emulator starting, badge badly placed for a second...).
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
    """After a test or a measurement, the badge on the reader must not act."""

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
        # A badge placed well after the measurement must act normally.
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
    """"Quit the game when the badge is removed" option."""

    def setUp(self):
        super().setUp()
        self.service._stop_on_remove = True
        self.service.controller.last_action = "launched"
        self.service.controller.game_running.return_value = True

    def retirer_le_badge(self):
        self.presence(False)
        # 3 s grace after the launch + 2 s of confirmed absence.
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
        # The emulator finally starts: the service then stops it.
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
        self.retirer_le_badge()  # must not raise
        self.assertIsNone(self.service._active_uid)

    def test_retrait_puis_repose_relance_le_jeu(self):
        self.service._badge_seen("A1B2C3D4")
        self.retirer_le_badge()
        self.presence(True)
        self.service._badge_seen("A1B2C3D4")
        self.assertEqual(self.actions, ["A1B2C3D4", "A1B2C3D4"])


class BonusSwapTest(StopOnRemoveTest):
    """Cartridge mode: a bonus card put in place of the game card."""

    def test_carte_bonus_a_la_place_du_jeu(self):
        self.service._badge_seen("A1B2C3D4")
        self.presence(False)
        self.laisse_tourner(5.2)        # removal noticed, stop not run yet
        self.service._stop_pending = ("A1B2C3D4", self.now + 5)
        self.service.controller.last_action = ""
        self.service.controller.on_badge = lambda uid: "extended"
        self.presence(True)
        self.service._badge_seen("B0B0B0B0")
        self.assertIsNone(self.service._stop_pending, "la partie continue")
        self.assertEqual(self.service._launched_uid, "B0B0B0B0", "la carte bonus tient le jeu")


class ServiceExtrasTest(unittest.TestCase):
    """Commands from the page, end of play time, status light."""

    def setUp(self):
        from unittest import mock as _mock

        from rfid import daemon as _daemon
        from rfid.playtime import PlayTimer

        self.mock = _mock
        self.daemon = _daemon
        self.home = tempfile.mkdtemp(prefix="rfid-extras-")
        self.addCleanup(shutil.rmtree, self.home, True)
        service = _daemon.Service.__new__(_daemon.Service)
        service.home = self.home
        service.log = support.RecordingLog()
        service._web_command_signature = None
        service._active_uid = None
        service._absent_since = None
        service._absent_hits = 0
        service._last_read_at = 0.0
        service._adopt_next_read = False
        service._adopt_until = 0.0
        service._expire_at = None
        service._next_game_check = 0.0
        service._game_gone = 0
        service._launched_uid = "A1"
        service._pairing_shown = None
        service._next_light_check = 0.0
        service._light_pairing = False
        service.reader = object()
        service.screen = _mock.Mock()
        service.light = _mock.Mock()
        service.light.enabled = True
        service.feedback = _mock.Mock()
        service.controller = _mock.Mock()
        service.controller.mode = ""
        service.controller.launched_uid = "A1"
        self.clock = support.FakeClock(500.0)
        service.playtime = PlayTimer(None, clock=self.clock)
        self.service = service
        patch = _mock.patch.object(_daemon.time, "monotonic", side_effect=lambda: self.clock.now)
        patch.start()
        self.addCleanup(patch.stop)

    def command(self, payload):
        with open(os.path.join(self.home, "agent-command.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        self.service._consume_agent_command()

    def test_commande_jeu_choisi(self):
        self.command({"cmd": "arm_target", "target": {"system": "snes", "name": "Mario",
                                                       "path": "/recalbox/share/roms/snes/Mario.smc"}})
        target = self.service.controller.arm_target.call_args[0][0]
        self.assertEqual((target.system, target.game, target.path),
                         ("snes", "Mario.smc", "/recalbox/share/roms/snes/Mario.smc"))

    def test_commande_carte_speciale(self):
        self.command({"cmd": "arm_entry", "entry": {"kind": "action", "action": "quit"}})
        self.service.controller.arm_entry.assert_called_once_with({"kind": "action", "action": "quit"})

    def test_fin_du_temps_de_jeu(self):
        self.service.playtime.start("A1", {"name": "Mario"}, 1)
        self.clock.advance(61)
        self.service._playtime_step()
        self.service.screen.say.assert_called_with("expired")
        self.service.light.flash.assert_called_with("timeup")
        self.service.controller.stop_game.assert_not_called()
        self.clock.advance(self.daemon.Service.EXPIRE_NOTICE_S + 0.1)
        self.service._playtime_step()
        self.service.controller.stop_game.assert_called_once_with("time")

    def test_jeu_quitte_depuis_son_menu(self):
        self.service.playtime.start("A1", {"name": "Mario"}, 30)
        self.service.controller.game_running.return_value = False
        for _ in range(3):
            self.clock.advance(21)
            self.service._playtime_step()
        self.assertIsNone(self.service.playtime.session)
        self.assertEqual(self.service.playtime.last["reason"], "quit")

    def test_voyant(self):
        self.service._light_step()
        self.service.light.set_state.assert_called_with("playing")
        self.service.controller.mode = "associate"
        self.service._light_step()
        self.service.light.set_state.assert_called_with("associate")
        self.service.reader = None
        self.service._light_step()
        self.service.light.set_state.assert_called_with("noreader")

    def test_ecriture_dans_le_badge(self):
        from fake_rc522 import FakeRc522Spi
        from rfid.drivers.rc522 import Rc522Reader

        spi = FakeRc522Spi(bytes.fromhex("A1B2C3D4"))
        self.service.reader = Rc522Reader(spi)
        self.service.reader.start()
        self.service._arm_adoption = lambda *a: None
        self.command({"cmd": "write_tag", "uid": "A1B2C3D4", "data": b"RL1|nes|a.nes\x00".hex()})
        self.service._tag_write_step()
        self.assertIsNone(self.service._tag_write)
        self.assertTrue(spi.read_text().startswith(b"RL1|nes|a.nes"))
        with open(os.path.join(self.home, "tag-write.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["state"], "done")

    def test_ecriture_abandonnee_sans_badge(self):
        from fake_rc522 import FakeRc522Spi
        from rfid.drivers.rc522 import Rc522Reader

        self.service.reader = Rc522Reader(FakeRc522Spi(None))
        self.service.reader.start()
        self.command({"cmd": "write_tag", "uid": "A1B2C3D4", "data": "00"})
        self.service._tag_write_step()
        self.assertIsNotNone(self.service._tag_write, "attend le badge")
        self.clock.advance(self.daemon.Service.TAG_WRITE_S + 1)
        self.service._tag_write_step()
        self.assertIsNone(self.service._tag_write)
        with open(os.path.join(self.home, "tag-write.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["state"], "error")

    def test_demande_d_acces_affichee_une_fois(self):
        with self.mock.patch.object(self.daemon.pairing, "pending", return_value={"id": "R1"}):
            self.service._light_step()
            self.clock.advance(1)
            self.service._light_step()
        self.service.screen.say.assert_called_once_with("pairing")
        self.service.light.set_state.assert_called_with("pairing")


class LockWatchdogTest(unittest.TestCase):
    """A locked menu whose Recalbox interface does not come back is unlocked."""

    def setUp(self):
        from unittest import mock

        from rfid import daemon as _daemon

        self.mock = mock
        self.daemon = _daemon
        self.service = _daemon.Service.__new__(_daemon.Service)
        self.service.home = tempfile.mkdtemp(prefix="rfid-watchdog-")
        self.service.log = mock.Mock()
        self.service.controller = mock.Mock()
        self.service.controller.game_running.return_value = False
        self.service._frontend_missing_since = None
        self.service._next_frontend_check = 0.0
        self.service._unlock_busy = False
        self.now = [1000.0]
        self.patches = [
            mock.patch.object(_daemon.time, "monotonic", side_effect=lambda: self.now[0]),
            mock.patch.object(_daemon.frontend_lock, "lock_active", return_value=True),
            mock.patch.object(_daemon.frontend_lock, "frontend_running", return_value=False),
            mock.patch.object(_daemon.threading, "Thread"),
        ]
        for patch in self.patches:
            patch.start()
        self.thread = _daemon.threading.Thread

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        shutil.rmtree(self.service.home, ignore_errors=True)

    def tick(self, seconds):
        self.now[0] += seconds
        self.service._lock_watchdog()

    def test_deverrouillage_de_secours(self):
        self.tick(0)
        self.tick(60)
        self.thread.assert_not_called()
        self.tick(61)
        self.thread.assert_called_once()
        self.assertTrue(self.service._unlock_busy)

    def test_rien_pendant_une_partie_ou_une_bascule(self):
        self.service.controller.game_running.return_value = True
        for _ in range(20):
            self.tick(20)
        self.service.controller.game_running.return_value = False
        self.service._unlock_busy = True
        for _ in range(20):
            self.tick(20)
        self.thread.assert_not_called()

    def test_rien_sans_verrouillage(self):
        with self.mock.patch.object(self.daemon.frontend_lock, "lock_active", return_value=False):
            for _ in range(20):
                self.tick(20)
        self.thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
