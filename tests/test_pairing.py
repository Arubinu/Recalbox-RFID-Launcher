"""Tests de l'appairage confirme physiquement."""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
sys.dont_write_bytecode = True

from rfid import pairing  # noqa: E402


class PairingTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-pair-")
        self.now = 1000000.0
        self._patch = mock.patch.object(pairing.time, "time", side_effect=lambda: self.now)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        for name in os.listdir(self.home):
            try:
                os.remove(os.path.join(self.home, name))
            except OSError:
                pass
        os.rmdir(self.home)

    def test_demande_puis_attente(self):
        request = pairing.create_request(self.home, "127.0.0.1")
        self.assertEqual(len(request["id"]), 8)
        self.assertAlmostEqual(request["until"], self.now + pairing.PAIRING_WINDOW_S, places=3)
        self.assertEqual(pairing.pending(self.home)["id"], request["id"])

    def test_une_seule_demande_a_la_fois(self):
        pairing.create_request(self.home)
        with self.assertRaises(pairing.PairingError):
            pairing.create_request(self.home)

    def test_demande_expiree_oubliee(self):
        pairing.create_request(self.home)
        self.now += pairing.PAIRING_WINDOW_S + 1
        self.assertIsNone(pairing.pending(self.home))
        # A new request is then possible.
        self.assertTrue(pairing.create_request(self.home)["id"])

    def test_accord_valable_une_seule_fois(self):
        request = pairing.create_request(self.home)
        self.assertTrue(pairing.grant(self.home, request, press_started=self.now + 1))
        self.assertTrue(pairing.take_grant(self.home, request["id"]))
        self.assertFalse(pairing.take_grant(self.home, request["id"]), "accord rejoue")

    def test_demande_servie_libere_la_place(self):
        """Another device may ask right after a successful pairing."""
        request = pairing.create_request(self.home)
        pairing.grant(self.home, request, press_started=self.now + 1)
        self.assertTrue(pairing.take_grant(self.home, request["id"]))
        self.assertIsNone(pairing.pending(self.home))
        self.assertTrue(pairing.create_request(self.home)["id"])

    def test_accord_refuse_pour_une_autre_demande(self):
        """The dreaded race: the press meant for A must not validate B."""
        premiere = pairing.create_request(self.home)
        self.assertTrue(pairing.grant(self.home, premiere, press_started=self.now + 1))
        # Request A expires, someone creates another one right after.
        self.now += pairing.PAIRING_WINDOW_S + 0.5
        seconde = pairing.create_request(self.home)
        self.assertNotEqual(premiere["id"], seconde["id"])
        self.assertFalse(
            pairing.take_grant(self.home, seconde["id"]),
            "un accord de la demande precedente a valide la suivante",
        )

    def test_accord_expire_avec_sa_demande(self):
        request = pairing.create_request(self.home)
        self.assertTrue(pairing.grant(self.home, request, press_started=self.now + 1))
        self.now += pairing.PAIRING_WINDOW_S + 1
        self.assertFalse(pairing.take_grant(self.home, request["id"]))

    def test_appui_commence_avant_la_demande_refuse(self):
        """A finger already down must not validate a request that arrived later."""
        pressed_at = self.now - 2.0
        request = pairing.create_request(self.home)
        self.assertFalse(pairing.grant(self.home, request, press_started=pressed_at))

    def test_nouvelle_demande_efface_un_ancien_accord(self):
        premiere = pairing.create_request(self.home)
        self.assertTrue(pairing.grant(self.home, premiere, press_started=self.now + 1))
        self.now += pairing.PAIRING_WINDOW_S + 0.5
        seconde = pairing.create_request(self.home)
        self.assertFalse(pairing.take_grant(self.home, seconde["id"]))
        self.assertFalse(pairing.take_grant(self.home, premiere["id"]))

    def test_annulation(self):
        pairing.create_request(self.home)
        pairing.cancel(self.home)
        self.assertIsNone(pairing.pending(self.home))
        self.assertFalse(pairing.take_grant(self.home, "QUELCONQUE"))


class PrivateStateDirTest(unittest.TestCase):
    """Pairing states must never live on the Samba share."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-state-")
        self.previous = os.environ.pop(pairing.STATE_DIR_ENV, None)

    def tearDown(self):
        if self.previous is None:
            os.environ.pop(pairing.STATE_DIR_ENV, None)
        else:
            os.environ[pairing.STATE_DIR_ENV] = self.previous
        shutil.rmtree(self.home, ignore_errors=True)

    def test_dossier_impose(self):
        prive = os.path.join(self.home, "prive")
        os.environ[pairing.STATE_DIR_ENV] = prive
        self.assertEqual(os.path.dirname(pairing.request_path(self.home)), prive)
        self.assertEqual(os.path.dirname(pairing.grant_path(self.home)), prive)

    def test_accord_forge_ignore(self):
        # A computer on the network can write to the share: a fake grant
        # dropped in home must give no access.
        prive = os.path.join(self.home, "prive")
        os.environ[pairing.STATE_DIR_ENV] = prive
        request = pairing.create_request(self.home)
        with open(os.path.join(self.home, pairing.GRANT_FILENAME), "w", encoding="utf-8") as handle:
            json.dump({"id": request["id"], "request_until": request["until"] + 60}, handle)
        with open(os.path.join(self.home, pairing.REQUEST_FILENAME), "w", encoding="utf-8") as handle:
            json.dump({"id": "FORGED01", "until": request["until"] + 60}, handle)
        self.assertFalse(pairing.take_grant(self.home, request["id"]), "faux accord accepte")

    def test_accord_du_service_accepte(self):
        prive = os.path.join(self.home, "prive")
        os.environ[pairing.STATE_DIR_ENV] = prive
        request = pairing.create_request(self.home)
        pairing.grant(self.home, request, request["created"] + 1.0)
        self.assertTrue(pairing.take_grant(self.home, request["id"]))

    def test_dossier_par_defaut_hors_partage(self):
        # The redirection to /tmp is checked on the machine itself; here we at
        # least make sure the default value is not the share.
        self.assertFalse(pairing.DEFAULT_STATE_DIR.startswith("/recalbox/share"))
        self.assertNotIn("/recalbox/share", pairing.DEFAULT_STATE_DIR)


class ServiceButtonTest(unittest.TestCase):
    """The service turns a long press into a pairing grant."""

    def setUp(self):
        from rfid import daemon

        self.home = tempfile.mkdtemp(prefix="rfid-svc-pair-")
        self.service = daemon.Service.__new__(daemon.Service)
        self.service.home = self.home
        self.service.log = None
        self.calls = []
        self.service.controller = mock.Mock()
        self.service.controller.on_button = lambda gesture: self.calls.append(gesture)
        self.service.feedback = mock.Mock()
        self.service._press_started_at = None

    def tearDown(self):
        pairing.cancel(self.home)
        for name in os.listdir(self.home):
            try:
                os.remove(os.path.join(self.home, name))
            except OSError:
                pass
        os.rmdir(self.home)

    def test_sans_demande_l_appui_court_associe(self):
        self.service.controller.armed = False
        self.service._active_uid = None
        self.service._absent_since = None
        self.service._handle_gesture("short")
        self.assertEqual(self.calls, ["short"])
        self.assertEqual(pairing.pending(self.home), None)

    def test_appui_tres_long_avec_demande_accorde(self):
        request = pairing.create_request(self.home)
        self.service._press_started_at = request["created"] + 1.0
        self.service._handle_gesture("hold")
        self.assertEqual(self.calls, [], "l'appui d'appairage ne doit rien associer")
        self.assertTrue(pairing.take_grant(self.home, request["id"]))
        self.service.feedback.ok.assert_called_once()

    def test_appui_court_pendant_une_demande_associe_quand_meme(self):
        """A short press during a request arms the association (known behaviour)."""
        pairing.create_request(self.home)
        self.service.controller.armed = False
        self.service._handle_gesture("short")
        self.assertEqual(self.calls, ["short"])

    def test_appui_tres_long_sans_demande_ignore(self):
        self.service._handle_gesture("hold")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
