"""Badge database tests (JSON storage)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401
from rfid.storage import StorageError, TagStore, normalize_uid, pretty_uid


class NormalizeUidTest(unittest.TestCase):
    def test_formats_acceptes(self):
        self.assertEqual(normalize_uid("a1:b2:c3:d4"), "A1B2C3D4")
        self.assertEqual(normalize_uid("A1 B2 C3 D4"), "A1B2C3D4")
        self.assertEqual(normalize_uid("a1-b2-c3-d4"), "A1B2C3D4")
        self.assertEqual(normalize_uid("a1b2c3d4"), "A1B2C3D4")

    def test_formats_refuses(self):
        for bad in ("", "ZZ", "ABC", "GGGGGGGG", None):
            with self.assertRaises(StorageError):
                normalize_uid(bad)

    def test_affichage(self):
        self.assertEqual(pretty_uid("A1B2C3D4"), "A1:B2:C3:D4")
        self.assertEqual(pretty_uid("01020304050607"), "01:02:03:04:05:06:07")


class TagStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-store-")
        self.path = os.path.join(self.directory, "tags.json")
        self.store = TagStore(self.path)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_base_vide(self):
        self.store.load()
        self.assertEqual(self.store.count(), 0)
        self.assertIsNone(self.store.get("A1B2C3D4"))

    def test_ajout_et_lecture(self):
        self.store.load()
        entry = self.store.put("a1b2c3d4", "snes", "Super Mario World.smc", "Super Mario World", "/recalbox/share/roms/snes/Super Mario World.smc")
        self.assertEqual(entry["system"], "snes")
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.get("A1:B2:C3:D4")["game"], "Super Mario World.smc")

    def test_persistance(self):
        self.store.load()
        self.store.put("A1B2C3D4", "snes", "jeu.smc")
        reloaded = TagStore(self.path)
        reloaded.load()
        self.assertEqual(reloaded.get("A1B2C3D4")["system"], "snes")
        with open(self.path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        self.assertEqual(raw["schema"], 1)
        self.assertIn("A1B2C3D4", raw["tags"])

    def test_ecriture_atomique_et_sauvegarde(self):
        self.store.load()
        self.store.put("A1B2C3D4", "snes", "jeu.smc")
        self.store.put("A1B2C3D4", "snes", "autre.smc")
        self.assertTrue(os.path.isfile(self.path + ".bak"))
        # No temporary file must be left
        leftovers = [name for name in os.listdir(self.directory) if name.startswith(".tags-")]
        self.assertEqual(leftovers, [])

    def test_suppression(self):
        self.store.load()
        self.store.put("A1B2C3D4", "snes", "jeu.smc")
        self.assertTrue(self.store.delete("A1B2C3D4"))
        self.assertFalse(self.store.delete("A1B2C3D4"))
        self.assertEqual(self.store.count(), 0)

    def test_compteur_utilisation(self):
        self.store.load()
        self.store.put("A1B2C3D4", "snes", "jeu.smc")
        self.store.touch("A1B2C3D4")
        self.store.touch("A1B2C3D4")
        entry = self.store.get("A1B2C3D4")
        self.assertEqual(entry["hits"], 2)
        self.assertTrue(entry["last_used"])

    def test_rechargement_si_modifie(self):
        self.store.load()
        self.store.put("A1B2C3D4", "snes", "jeu.smc")
        with open(self.path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        raw["tags"]["A1B2C3D4"]["system"] = "megadrive"
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(raw, handle)
        os.utime(self.path, (1, 1))
        self.assertTrue(self.store.reload_if_changed())
        self.assertEqual(self.store.get("A1B2C3D4")["system"], "megadrive")

    def test_fichier_corrompu_conserve(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{ pas du json")
        store = TagStore(self.path)
        store.load()
        self.assertEqual(store.count(), 0)
        backups = [name for name in os.listdir(self.directory) if ".corrupt-" in name]
        self.assertEqual(len(backups), 1)

    def test_entree_incomplete_ignoree(self):
        payload = {"schema": 1, "tags": {"A1B2C3D4": {"system": "snes"}}}
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        store = TagStore(self.path)
        store.load()
        self.assertEqual(store.count(), 0)

    def test_csv_aller_retour(self):
        self.store.load()
        self.store.put("A1B2C3D4", "snes", "Super Mario World.smc", "Super Mario World")
        self.store.put("01020304050607", "nes", "Zelda.nes", "Zelda")
        csv_path = os.path.join(self.directory, "export.csv")
        self.assertEqual(self.store.export_csv(csv_path), 2)

        other = TagStore(os.path.join(self.directory, "autre.json"))
        other.load()
        stats = other.import_csv(csv_path)
        self.assertEqual(stats["ajoutes"], 2)
        self.assertEqual(stats["ignores"], 0)
        self.assertEqual(other.get("01020304050607")["name"], "Zelda")

    def test_csv_sans_ecrasement(self):
        self.store.load()
        self.store.put("A1B2C3D4", "snes", "jeu.smc", "Un")
        csv_path = os.path.join(self.directory, "export.csv")
        self.store.export_csv(csv_path)
        self.store.put("A1B2C3D4", "snes", "autre.smc", "Deux")
        stats = self.store.import_csv(csv_path, overwrite=False)
        self.assertEqual(stats["ignores"], 1)
        self.assertEqual(self.store.get("A1B2C3D4")["game"], "autre.smc")


if __name__ == "__main__":
    unittest.main()
