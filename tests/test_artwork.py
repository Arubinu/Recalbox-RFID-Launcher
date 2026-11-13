"""Online game pictures (libretro thumbnail server), without network."""

from __future__ import annotations

import base64
import os
import shutil
import tempfile
import unittest

import support  # noqa: F401 - sets sys.path
from rfid import artwork
from rfid.artwork import Artwork, ArtworkError, match, title_key

PNG = b"\x89PNG\r\n\x1a\nfake"


def listing(*names):
    links = "".join('<a href="%s.png">x</a>' % artwork.urllib.parse.quote(name) for name in names)
    return ("<html><body><a href=\"../\">../</a>%s</body></html>" % links).encode("utf-8")


class FakeServer:
    def __init__(self, folders):
        self.folders = folders
        self.calls = []
        self.down = False

    def __call__(self, url, timeout=15.0):
        self.calls.append(url)
        if self.down:
            raise ArtworkError("serveur d'images injoignable (test)")
        path = artwork.urllib.parse.unquote(url[len(artwork.BASE_URL) + 1:])
        system, folder, rest = path.split("/", 2)
        names = self.folders.get((system, folder), [])
        if not rest:
            return listing(*names)
        return PNG if rest[:-4] in names else b""


class MatchTest(unittest.TestCase):
    NAMES = [
        "Sonic The Hedgehog (USA, Europe)",
        "Sonic The Hedgehog (World) (Sonic Mega Collection)",
        "Sonic The Hedgehog (Japan, Korea)",
        "Legend of Zelda, The (USA)",
        "Legend of Zelda, The (USA) (Beta)",
        "Tetris (World) (Rev 1)",
        "Tetris (Japan)",
        "Mario _ Luigi (USA)",
    ]

    def test_nom_de_fichier_exact(self):
        self.assertEqual(match(self.NAMES, "/roms/gb/Tetris (Japan).gb"), "Tetris (Japan)")

    def test_nom_du_jeu_et_article(self):
        self.assertEqual(match(self.NAMES, "/roms/nes/zelda.nes", "The Legend of Zelda"),
                         "Legend of Zelda, The (USA)")

    def test_version_ordinaire_preferee(self):
        """Neither a compilation nor a beta when the plain cartridge exists."""
        self.assertEqual(match(self.NAMES, "/roms/megadrive/sonic.md", "Sonic The Hedgehog"),
                         "Sonic The Hedgehog (USA, Europe)")

    def test_tags_de_la_rom_respectes(self):
        self.assertEqual(match(self.NAMES, "/roms/megadrive/Sonic The Hedgehog (Japan, Korea).md"),
                         "Sonic The Hedgehog (Japan, Korea)")

    def test_caracteres_remplaces(self):
        self.assertEqual(match(self.NAMES, "/roms/gba/Mario & Luigi (USA).gba"), "Mario _ Luigi (USA)")

    def test_rien(self):
        self.assertEqual(match(self.NAMES, "/roms/gb/PongBoy.gb", "Pong Boy"), "")
        self.assertEqual(match([], "/roms/gb/Tetris.gb", "Tetris"), "")

    def test_cle(self):
        self.assertEqual(title_key("Legend of Zelda, The - Link's Awakening (USA)"),
                         title_key("The Legend of Zelda: Link's Awakening"))
        self.assertEqual(title_key("Pokémon Pinball (Europe)"), "pokemon pinball")


class ArtworkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfid-art-")
        self.now = 1000000.0
        gb = artwork.SYSTEMS["gb"]
        self.server = FakeServer({
            (gb, "Named_Boxarts"): ["Tetris (World) (Rev 1)"],
            (gb, "Named_Snaps"): ["Tetris (World) (Rev 1)"],
            (gb, "Named_Titles"): ["Tetris (World) (Rev 1)", "Tuff (World) (Aftermarket) (Unl)"],
            (gb, "Named_Logos"): ["Tetris (World) (Rev 1)"],
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make(self):
        return Artwork(self.tmp, http_get=self.server, now=lambda: self.now)

    def test_images_disponibles(self):
        found = self.make().available("gb", "/roms/gb/Tetris.gb", "Tetris")
        self.assertEqual(set(found), {"boxart", "snap", "title", "logo"})
        found = self.make().available("gb", "/roms/gb/Tuff.gb", "Tuff")
        self.assertEqual(found, {"title": "Tuff (World) (Aftermarket) (Unl)"})

    def test_console_inconnue(self):
        self.assertEqual(self.make().available("inconnue", "/roms/x/a.bin"), {})
        self.assertEqual(self.server.calls, [])

    def test_liste_en_cache_sur_disque(self):
        self.make().available("gb", "/roms/gb/Tetris.gb")
        first = len(self.server.calls)
        self.assertEqual(first, 4)
        # A new agent (restart) reads the disk cache.
        self.make().available("gb", "/roms/gb/Tetris.gb")
        self.assertEqual(len(self.server.calls), first)
        # Two weeks later, the listing is downloaded again.
        self.now += artwork.INDEX_TTL_S + 1
        self.make().available("gb", "/roms/gb/Tetris.gb")
        self.assertEqual(len(self.server.calls), first * 2)

    def test_image(self):
        art = self.make()
        self.assertEqual(art.picture("gb", "boxart", "Tetris (World) (Rev 1)"), ("image/png", PNG))
        self.assertIn("Named_Boxarts/Tetris%20%28World%29%20%28Rev%201%29.png", self.server.calls[-1])

    def test_nom_absent_de_la_liste_refuse(self):
        """Only names of the listing are fetched (no free URL)."""
        art = self.make()
        self.assertIsNone(art.picture("gb", "boxart", "../../etc/passwd"))
        self.assertIsNone(art.picture("gb", "nimporte", "Tetris (World) (Rev 1)"))
        self.assertFalse(any("passwd" in url for url in self.server.calls))

    def test_serveur_injoignable(self):
        self.server.down = True
        art = self.make()
        with self.assertRaises(ArtworkError):
            art.available("gb", "/roms/gb/Tetris.gb")
        calls = len(self.server.calls)
        # No new attempt for ten minutes.
        with self.assertRaises(ArtworkError):
            art.index("gb", "boxart")
        self.assertEqual(len(self.server.calls), calls)
        self.server.down = False
        self.now += artwork.FAILURE_TTL_S + 1
        self.assertEqual(art.index("gb", "boxart"), ["Tetris (World) (Rev 1)"])


class AgentCommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rfid-art-agent-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_commandes(self):
        from rfid import wsagent
        from rfid.config import Config
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        config_path = os.path.join(home, "config.ini")
        agent = wsagent.Agent(Config(config_path), None, home=home, port=0)
        gb = artwork.SYSTEMS["gb"]
        server = FakeServer({(gb, "Named_Boxarts"): ["Tetris (World) (Rev 1)"]})
        agent.artwork = Artwork(os.path.join(home, "cache"), http_get=server)

        found = agent._cmd_media_online(None, {"system": "gb", "path": "/roms/gb/Tetris.gb", "name": "Tetris"})
        self.assertEqual(found, {"enabled": True, "found": {"boxart": "Tetris (World) (Rev 1)"}})
        picture = agent._cmd_media_online_get(None, {"system": "gb", "kind": "boxart", "name": "Tetris (World) (Rev 1)"})
        self.assertTrue(picture["found"])
        self.assertEqual(base64.b64decode(picture["data"]), PNG)

        server.down = True
        agent.artwork = Artwork(os.path.join(self.tmp, "other"), http_get=server)
        failed = agent._cmd_media_online(None, {"system": "gb", "path": "/roms/gb/Tetris.gb"})
        self.assertEqual(failed["found"], {})
        self.assertIn("injoignable", failed["error"])

        with open(config_path, "a", encoding="utf-8") as handle:
            handle.write("\n[cards]\nonline_art = 0\n")
        self.assertEqual(agent._cmd_media_online(None, {"system": "gb", "path": "/a.gb"}),
                         {"enabled": False, "found": {}})
        with self.assertRaises(ValueError):
            agent._cmd_media_online_get(None, {"system": "gb", "kind": "boxart", "name": "x"})


if __name__ == "__main__":
    unittest.main()
