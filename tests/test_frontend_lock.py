"""Menu lock: favourite games only and no START menu (recalbox.conf)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import support  # noqa: F401 - sets sys.path
from rfid import frontend_lock as lock

CONF = """## Recalbox
emulationstation.menu=default
;emulationstation.favoritesonly=1
emulationstation.selectedsystem=favorites
kodi.enabled=1
"""


class FrontendLockTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-lock-")
        self.conf = os.path.join(self.home, "recalbox.conf")
        with open(self.conf, "w", encoding="utf-8") as handle:
            handle.write(CONF)
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def apply(self, enabled, **extra):
        return lock.apply(self.home, enabled, conf=self.conf, run=self.calls.append, **extra)

    def text(self):
        with open(self.conf, encoding="utf-8") as handle:
            return handle.read()

    def test_verrouillage_puis_retour(self):
        self.assertEqual(self.apply(True), {"changed": True})
        self.assertTrue(lock.is_locked(self.conf))
        self.assertIn("emulationstation.favoritesonly=1", self.text())
        self.assertIn("emulationstation.menu=none", self.text())
        self.assertIn("kodi.enabled=1", self.text(), "le reste du fichier est garde")
        self.assertEqual([call[1] for call in self.calls], ["stop", "start"])
        self.assertEqual(self.apply(True), {"changed": False}, "deja verrouille")
        self.apply(False)
        self.assertEqual(self.text(), CONF, "le fichier revient exactement comme avant")
        self.assertFalse(os.path.exists(os.path.join(self.home, lock.LOCK_FILENAME)))

    def test_fichier_sans_retour_a_la_ligne_final(self):
        original = CONF.rstrip("\n")
        with open(self.conf, "w", encoding="utf-8") as handle:
            handle.write(original)
        self.apply(True)
        self.assertTrue(lock.is_locked(self.conf))
        self.apply(False)
        self.assertEqual(self.text(), original)

    def test_valeurs_d_avant_remises(self):
        with open(self.conf, "w", encoding="utf-8") as handle:
            handle.write(CONF.replace(";emulationstation.favoritesonly=1", "emulationstation.favoritesonly=1")
                         .replace("menu=default", "menu=bartop"))
        self.apply(True)
        self.apply(False)
        values = lock.read_values(self.text(), lock.LOCKED)
        self.assertEqual(values, {"emulationstation.menu": "bartop", "emulationstation.favoritesonly": "1",
                                  "emulationstation.collection.ports": None,
                                  "emulationstation.collection.challenges": None})

    def test_refuse_pendant_un_jeu(self):
        with self.assertRaises(lock.LockError):
            self.apply(True, game_running=lambda: True)
        self.assertEqual(self.calls, [], "le menu n'est pas arrete pendant un jeu")
        self.assertFalse(lock.is_locked(self.conf))

    def test_desinstallation_sans_redemarrer(self):
        self.apply(True)
        self.calls.clear()
        self.assertEqual(self.apply(False, restart=False, game_running=lambda: True), {"changed": True})
        self.assertEqual(self.calls, [])
        self.assertFalse(lock.is_locked(self.conf))

    def toggle(self, **extra):
        return lock.toggle_unlock(self.home, conf=self.conf, run=self.calls.append, **extra)

    def test_carte_deverrouiller_aller_retour(self):
        self.apply(True)
        locked = self.text()
        self.assertEqual(self.toggle(), "unlocked")
        self.assertEqual(self.text(), CONF, "tous les jeux et le menu START comme avant")
        self.assertTrue(lock.is_unlocked(self.home))
        self.assertEqual(self.toggle(), "locked")
        self.assertEqual(self.text(), locked, "verrouille a nouveau")
        self.assertFalse(lock.is_unlocked(self.home))
        self.apply(False)
        self.assertEqual(self.text(), CONF, "l'option desactivee remet toujours le fichier d'origine")

    def test_carte_sans_verrouillage(self):
        with self.assertRaises(lock.LockError):
            self.toggle()
        self.assertEqual(self.calls, [])
        self.assertFalse(lock.is_unlocked(self.home))

    def test_carte_refusee_pendant_un_jeu(self):
        self.apply(True)
        self.calls.clear()
        with self.assertRaises(lock.LockError):
            self.toggle(game_running=lambda: True)
        self.assertEqual(self.calls, [])
        self.assertTrue(lock.is_locked(self.conf))
        self.assertFalse(lock.is_unlocked(self.home))

    def test_portages_et_challenges_masques(self):
        self.apply(True)
        values = lock.read_values(self.text(), lock.LOCKED)
        self.assertEqual(values["emulationstation.collection.ports"], "0")
        self.assertEqual(values["emulationstation.collection.challenges"], "0")
        self.apply(False)
        self.assertEqual(self.text(), CONF)

    def recalbox_turns_favourites_off(self):
        """What Recalbox does when no game is a favourite."""
        text = self.text().replace("\nemulationstation.favoritesonly=1", "\nemulationstation.favoritesonly=0")
        with open(self.conf, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_favoris_annules_par_recalbox(self):
        self.apply(True)
        self.recalbox_turns_favourites_off()
        self.assertFalse(lock.is_locked(self.conf))
        self.assertTrue(lock.lock_active(self.home), "le lecteur a verrouille : il faut pouvoir defaire")
        self.assertEqual(self.toggle(), "unlocked")
        self.assertEqual(self.toggle(), "locked")
        self.recalbox_turns_favourites_off()
        self.assertEqual(self.apply(False), {"changed": True})
        self.assertEqual(self.text(), CONF, "tout revient, meme la ligne ajoutee par Recalbox")

    def test_ancienne_copie_a_deux_cles(self):
        self.apply(True)
        with open(os.path.join(self.home, lock.LOCK_FILENAME), "w", encoding="utf-8") as handle:
            handle.write('{"emulationstation.menu": "default", "emulationstation.favoritesonly": null}')
        self.apply(False)
        values = lock.read_values(self.text(), lock.LOCKED)
        self.assertEqual(values["emulationstation.menu"], "default")
        self.assertIsNone(values["emulationstation.favoritesonly"])
        self.assertEqual(values["emulationstation.collection.ports"], "1", "valeur par defaut de Recalbox")

    def make_frontend(self, quits_after, starts=True):
        """Fake frontend: runs until ``quits_after`` checks after the stop."""
        state = {"up": True, "checks": 0, "starts": 0}

        def run(args):
            self.calls.append(args)
            if args[1] == "start":
                state["starts"] += 1
                state["up"] = starts or state["starts"] > 1

        def running():
            if state["up"] and self.calls and self.calls[-1][1] == "stop":
                state["checks"] += 1
                if state["checks"] > quits_after:
                    # Recalbox saves its settings while quitting.
                    with open(self.conf, "a", encoding="utf-8") as handle:
                        handle.write("system.saved.on.quit=1\n")
                    state["up"] = False
            return state["up"]

        clock = support.FakeClock()
        return state, dict(run=run, running=running, sleep=clock.advance, clock=clock)

    def test_attend_l_arret_reel_du_menu(self):
        state, fake = self.make_frontend(quits_after=40)  # 20 s: longer than the init script waits
        self.assertEqual(lock.apply(self.home, True, conf=self.conf, **fake), {"changed": True})
        self.assertIn("system.saved.on.quit=1", self.text(), "ecrit apres l'enregistrement du menu")
        self.assertTrue(lock.is_locked(self.conf))
        self.assertEqual([call[1] for call in self.calls], ["stop", "start"])
        self.assertTrue(state["up"])

    def test_relance_si_le_menu_ne_repart_pas(self):
        state, fake = self.make_frontend(quits_after=2, starts=False)
        lock.apply(self.home, True, conf=self.conf, **fake)
        self.assertEqual([call[1] for call in self.calls], ["stop", "start", "start"])
        self.assertTrue(state["up"])

    def test_menu_qui_ne_s_arrete_pas(self):
        _state, fake = self.make_frontend(quits_after=10 ** 6)
        with self.assertRaises(lock.LockError):
            lock.apply(self.home, True, conf=self.conf, **fake)
        self.assertEqual(self.text(), CONF, "rien n'est ecrit")
        self.assertEqual([call[1] for call in self.calls], ["stop", "start"])

    def test_rien_a_defaire(self):
        self.assertEqual(self.apply(False), {"changed": False})
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
