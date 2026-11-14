"""Status light, screen messages, game library and boot configuration."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import support
from rfid import bootcfg, led, osd
from rfid.config import Config
from rfid.library import Library, LibraryError, find_rom, players_text, relative_to_system


class FakeGpio:
    def __init__(self):
        self.levels = {}
        self.outputs = []

    def setup_output(self, pin, value=0):
        self.outputs.append(pin)
        self.levels[pin] = value

    def write(self, pin, value):
        self.levels[pin] = value


class FakeSpi:
    def __init__(self):
        self.frames = []
        self.closed = False

    def transfer(self, data):
        self.frames.append(bytes(data))
        return bytes(len(data))

    def close(self):
        self.closed = True


class LightTest(unittest.TestCase):
    def test_trame_ws2812(self):
        frame = led.ws2812_frame([(255, 0, 1)], 1.0)
        bits = frame[1:25]
        # GRB order: green 0, red 255, blue 1.
        self.assertEqual(list(bits[:8]), [led.WS_ZERO] * 8)
        self.assertEqual(list(bits[8:16]), [led.WS_ONE] * 8)
        self.assertEqual(list(bits[16:24]), [led.WS_ZERO] * 7 + [led.WS_ONE])
        self.assertTrue(frame.endswith(b"\x00" * 200), "pause de remise a zero")
        self.assertLess(len(led.ws2812_frame([(1, 1, 1)] * 150)), 4096)

    def test_luminosite(self):
        dim = led.ws2812_frame([(255, 255, 255)], 0.0)
        self.assertEqual(set(dim[1:25]), {led.WS_ZERO})

    def test_led_rgb_anode_commune(self):
        gpio = FakeGpio()
        light = led.RgbLight(gpio, (22, 23, 24), common_anode=True)
        light.write(led.GREEN)
        self.assertEqual(gpio.levels, {22: 1, 23: 0, 24: 1})
        light.write(led.OFF)
        self.assertEqual(gpio.levels, {22: 1, 23: 1, 24: 1})

    def test_led_rgb_cathode_commune(self):
        gpio = FakeGpio()
        light = led.RgbLight(gpio, (22, 23, 24))
        light.write(led.YELLOW)
        self.assertEqual(gpio.levels, {22: 1, 23: 1, 24: 0})

    def test_etats_et_evenements(self):
        clock = support.FakeClock(0.0)
        spi = FakeSpi()
        status = led.StatusLight(led.Ws2812Light(spi), clock=clock)
        status.set_state("idle")
        status.update()
        self.assertEqual(len(spi.frames), 1)
        status.update()
        self.assertEqual(len(spi.frames), 1, "rien n'est renvoye si la couleur ne change pas")
        status.flash("error")
        self.assertEqual(status.colour(), led.RED)
        clock.advance(2.0)
        self.assertEqual(status.colour(), led.GREEN)
        status.set_state("associate")
        colours = set()
        for _ in range(8):
            clock.advance(0.15)
            colours.add(status.colour())
        self.assertEqual(colours, {led.BLUE, led.OFF}, "clignote")

    def test_eteint_au_repos(self):
        status = led.StatusLight(led.Ws2812Light(FakeSpi()), idle_on=False, clock=support.FakeClock())
        status.set_state("idle")
        self.assertEqual(status.colour(), led.OFF)

    def test_construction_depuis_la_configuration(self):
        directory = tempfile.mkdtemp(prefix="rfid-led-")
        self.addCleanup(shutil.rmtree, directory, True)
        cfg = Config(os.path.join(directory, "config.ini"))
        self.assertFalse(led.build_light(cfg).enabled)
        cfg.write_values({"led.type": "ws2812", "led.count": "3", "led.brightness": "50"})
        spi = FakeSpi()
        status = led.build_light(cfg, open_spi=lambda path, speed: spi)
        self.assertTrue(status.enabled)
        self.assertEqual(status.output.count, 3)

    def test_spi_absent_ne_bloque_pas(self):
        directory = tempfile.mkdtemp(prefix="rfid-led-")
        self.addCleanup(shutil.rmtree, directory, True)
        cfg = Config(os.path.join(directory, "config.ini"))
        cfg.write_values({"led.type": "ws2812"})

        def missing(path, speed):
            raise OSError("no /dev/spidev1.0")

        self.assertFalse(led.build_light(cfg, open_spi=missing).enabled)


class ScreenTest(unittest.TestCase):
    def test_message_traduit(self):
        self.assertEqual(osd.message("bonus", "fr", n=10), "+10 min de jeu")
        self.assertEqual(osd.message("bonus", "xx", n=5), "+5 min of play")

    def test_langue_de_la_recalbox(self):
        directory = tempfile.mkdtemp(prefix="rfid-osd-")
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, "recalbox.conf")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("kodi.enabled=1\nsystem.language=de_DE\n")
        self.assertEqual(osd.recalbox_language(path), "de")
        self.assertEqual(osd.recalbox_language(os.path.join(directory, "absent")), "fr")

    def test_commande_retroarch(self):
        sent = []
        screen = osd.ScreenMessages(sender=sent.append)
        screen.language = "fr"
        self.assertTrue(screen.say("warn60"))
        self.assertEqual(sent, ["SHOW_MSG Plus qu'une minute de jeu".encode("utf-8")])

    def test_desactive(self):
        sent = []
        screen = osd.ScreenMessages(enabled=False, sender=sent.append)
        self.assertFalse(screen.show("x"))
        self.assertEqual(sent, [])

    def test_erreur_reseau_silencieuse(self):
        def fail(payload):
            raise OSError("unreachable")

        self.assertFalse(osd.ScreenMessages(sender=fail).show("x"))


class FakeApi:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def __call__(self, url, timeout=4.0):
        self.urls.append(url)
        for prefix, answer in self.routes.items():
            if url.endswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise LibraryError("404")


SYSTEMS = {"systems": [
    {"name": "snes", "fullName": "Super Nintendo", "manufacturer": "Nintendo"},
    {"name": "challenges", "fullName": "Challenges"},
    {"name": "megadrive", "fullName": "Mega Drive", "manufacturer": "Sega"},
]}
SNES = {"roms": [
    {"path": "/recalbox/share/roms/snes/Super Mario World.smc", "name": "Super Mario World", "favorite": True, "players": 2},
    {"path": "/recalbox/share/roms/snes/Pokémon.smc", "name": "Pokémon Édition", "favorite": False},
]}
MD = {"roms": [{"path": "/recalbox/share/roms/megadrive/Sonic.md", "name": "Sonic", "favorite": False}]}


def json_answer(payload):
    return ("application/json", json.dumps(payload).encode("utf-8"))


class LibraryTest(unittest.TestCase):
    def library(self, routes=None):
        api = FakeApi(routes or {
            "/api/systems/getactives": json_answer(SYSTEMS),
            "/api/systems/snes/roms": json_answer(SNES),
            "/api/systems/megadrive/roms": json_answer(MD),
        })
        return Library(http_get=api, roms_dirs=()), api

    def test_consoles_sans_les_listes_virtuelles(self):
        library, _api = self.library()
        self.assertEqual([item["id"] for item in library.systems()], ["snes", "megadrive"])

    def test_recherche_sans_accents(self):
        library, _api = self.library()
        self.assertEqual([g["name"] for g in library.search("pokemon edition")], ["Pokémon Édition"])
        self.assertEqual([g["name"] for g in library.search("", "megadrive")], ["Sonic"])

    def test_cache(self):
        library, api = self.library()
        library.search("mario")
        count = len(api.urls)
        library.search("sonic")
        self.assertEqual(len(api.urls), count)

    def test_hasard_parmi_les_favoris(self):
        library, _api = self.library()
        self.assertEqual(library.pick_random(favorites_only=True)["name"], "Super Mario World")

    def test_image_du_jeu(self):
        library, api = self.library({
            "/api/systems/getactives": json_answer(SYSTEMS),
            "Super%20Mario%20World.smc": ("image/png", b"\x89PNG"),
        })
        self.assertEqual(library.game_image("snes", "/recalbox/share/roms/snes/Super Mario World.smc"),
                         ("image/png", b"\x89PNG"))
        self.assertIn("%2Frecalbox%2Fshare%2Froms%2Fsnes%2FSuper%20Mario%20World.smc", api.urls[-1])

    def test_logo_svg(self):
        library, _api = self.library({"/resource/eu/svg/logo": ("image/svg+xml", b"<svg/>")})
        self.assertEqual(library.system_logo("snes"), ("image/svg+xml", b"<svg/>"))
        with self.assertRaises(LibraryError):
            library.system_logo("snes", "passwd")

    def test_repli_sur_gamelist(self):
        directory = tempfile.mkdtemp(prefix="rfid-roms-")
        self.addCleanup(shutil.rmtree, directory, True)
        os.makedirs(os.path.join(directory, "nes", "media"))
        with open(os.path.join(directory, "nes", "gamelist.xml"), "w", encoding="utf-8") as handle:
            handle.write("<gameList><game><path>./Zelda.nes</path><name>Zelda</name>"
                         "<image>./media/zelda.png</image><favorite>true</favorite><players>1-2</players></game>"
                         "<game><path>./Hidden.nes</path><hidden>true</hidden></game></gameList>")
        with open(os.path.join(directory, "nes", "media", "zelda.png"), "wb") as handle:
            handle.write(b"PNGDATA")
        library = Library(http_get=FakeApi({"/api/systems/getactives": LibraryError("down")}),
                          roms_dirs=(directory,))
        self.assertEqual([item["id"] for item in library.systems()], ["nes"])
        games = library.games("nes")
        self.assertEqual([g["name"] for g in games], ["Zelda"])
        self.assertTrue(games[0]["favorite"])
        self.assertEqual(games[0]["players"], "1-2")
        self.assertEqual(library.game_image("nes", games[0]["path"]), ("image/png", b"PNGDATA"))

    def test_nombre_de_joueurs(self):
        self.assertEqual([players_text(v) for v in (1, 2, 4, 0, True, None)], ["1", "1-2", "1-4", "", "", ""])
        self.assertEqual([players_text(v) for v in ("1-4", "2", " 1 - 2 ", "1–2", "4-1", "2-2", "abc")],
                         ["1-4", "2", "1-2", "1-2", "", "2", ""])
        library, _api = self.library()
        mario = library.game_info("snes", "/recalbox/share/roms/snes/Super Mario World.smc")
        self.assertEqual(mario["players"], "1-2")
        self.assertEqual(library.game_info("snes", "Super Mario World.smc")["name"], "Super Mario World",
                         "un badge peut ne garder que le nom du fichier")
        self.assertEqual(library.game_info("megadrive", "/recalbox/share/roms/megadrive/Sonic.md")["players"], "")
        self.assertIsNone(library.game_info("snes", "/absent.smc"))

    def test_console_invalide(self):
        library, _api = self.library()
        with self.assertRaises(LibraryError):
            library.games("../etc")

    def test_chemins_portables(self):
        self.assertEqual(relative_to_system("snes", "/recalbox/share_init/roms/snes/a/b.smc"), "a/b.smc")
        self.assertEqual(find_rom("snes", "../../etc/passwd"), "")


class BootConfigTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-boot-")
        self.user = os.path.join(self.directory, "recalbox-user-config.txt")
        self.main = os.path.join(self.directory, "config.txt")
        with open(self.user, "w", encoding="utf-8") as handle:
            handle.write("dtparam=spi=on\n")
        with open(self.main, "w", encoding="utf-8") as handle:
            handle.write("disable_overscan=1\ndtparam=audio=on\n\n[pi4]\narm_boost=1\n")

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_ajout_dans_les_deux_fichiers(self):
        result = bootcfg.ensure_line(files=(self.user, self.main), remount=lambda mode: True)
        self.assertEqual(len(result["changed"]), 2)
        with open(self.main, encoding="utf-8") as handle:
            lines = handle.read().split("\n")
        self.assertLess(lines.index(bootcfg.SPI1_OVERLAY), lines.index("[pi4]"), "section globale")
        with open(self.user, encoding="utf-8") as handle:
            self.assertIn(bootcfg.SPI1_OVERLAY, handle.read())
        self.assertTrue(bootcfg.has_line(bootcfg.SPI1_OVERLAY, (self.user,)))

    def test_deja_present(self):
        bootcfg.ensure_line(files=(self.user, self.main), remount=lambda mode: True)
        again = bootcfg.ensure_line(files=(self.user, self.main), remount=lambda mode: True)
        self.assertEqual(again["changed"], [])

    def test_sauvegarde_d_installation_conservee(self):
        backup = self.main + ".bak-rfid-launcher"
        with open(backup, "w", encoding="utf-8") as handle:
            handle.write("original\n")
        bootcfg.ensure_line(files=(self.main,), remount=lambda mode: True)
        with open(backup, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "original\n")


if __name__ == "__main__":
    unittest.main()
