"""Remote control (page and Home Assistant), the status light signals, the
weekly summary, the cartridge sound and the reader screen look."""

from __future__ import annotations

import json
import os
import shutil
import struct
import tempfile
import time
import unittest

import support
from rfid import led, mqtt, screen
from rfid.config import Config
from rfid.controller import Controller
from rfid.feedback import Feedback
from rfid.players import Players
from rfid.playtime import PlayTimer
from rfid.storage import TagStore

IDLE = {"State": "selected"}
WEDNESDAY = time.mktime((2026, 11, 11, 12, 0, 0, 0, 0, -1))
MONDAY = time.mktime((2026, 11, 16, 12, 0, 0, 0, 0, -1))


class FakeScreen:
    def __init__(self):
        self.said = []

    def say(self, key, **values):
        self.said.append((key, values))
        return True


class RemoteTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="rfid-remote-")
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.store = TagStore(os.path.join(self.directory, "tags.json"))
        self.store.load()
        self.store.put("6A0E0001", "snes", "Mario.smc", "Mario")
        self.store.put_entry("1EA00001", {"kind": "action", "action": "player", "name": "Lea",
                                          "params": {"quota_min": 30, "period": "day"}})
        self.launcher = support.FakeLauncher()
        self.clock = support.FakeClock()
        self.wall = support.FakeClock(WEDNESDAY)
        self.screen = FakeScreen()
        self.config = Config(os.path.join(self.directory, "config.ini"))
        with open(self.config.path, "w", encoding="utf-8") as handle:
            handle.write("[players]\nenabled = 1\n")
        self.config.reload()
        self.players = Players(self.directory, wall=self.wall, clock=self.clock)
        self.playtime = PlayTimer(self.directory, clock=self.clock, wall=self.wall)
        self.controller = Controller(self.store, self.launcher, support.FakeFeedback(), self.config, None,
                                     state_provider=lambda: dict(IDLE), clock=self.clock, playtime=self.playtime,
                                     screen=self.screen, players=self.players)

    def test_plus_dix_minutes(self):
        self.assertEqual(self.controller.remote("add", 10), "nothing", "pas de partie")
        self.controller.on_badge("1EA00001")
        self.controller.on_badge("6A0E0001")
        before = self.controller.player_left("1EA00001", self.store.get("1EA00001"))
        self.assertEqual(self.controller.remote("add", 10), "added")
        after = self.controller.player_left("1EA00001", self.store.get("1EA00001"))
        self.assertAlmostEqual(after - before, 600, delta=1)
        self.assertEqual(self.screen.said[-1][0], "reward")

    def test_quitter(self):
        self.controller.on_badge("6A0E0001")
        self.assertEqual(self.controller.remote("quit"), "quit")
        self.assertFalse(self.launcher.running)
        self.assertEqual(self.controller.remote("quit"), "nothing")
        self.assertEqual(self.controller.remote("autre"), "unknown")


class FakeClient:
    """A broker in memory: what was published, and messages to deliver."""

    def __init__(self):
        self.published, self.subscribed, self.incoming, self.closed = [], [], [], False
        self.connected_with = None

    def connect(self, client_id, username="", password="", will=None):
        self.connected_with = (client_id, username, password, will)

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    def subscribe(self, topic):
        self.subscribed.append(topic)

    def read_packet(self, timeout):
        if self.incoming:
            topic, payload = self.incoming.pop(0)
            body = struct.pack("!H", len(topic)) + topic.encode() + payload.encode()
            return mqtt.PUBLISH, 0, body
        time.sleep(0.01)
        return None

    def ping_if_due(self):
        pass

    def close(self, polite=True):
        self.closed = True


class MqttTest(unittest.TestCase):
    def test_paquets(self):
        packet = mqtt.connect_packet("id", "user", "secret", will=("t/availability", "offline"))
        self.assertEqual(packet[0], 0x10)
        flags = packet[2 + 6 + 1]  # fixed header (2), "MQTT" (6), level (1)
        self.assertEqual(flags, 0x80 | 0x40 | 0x20 | 0x04 | 0x02)
        self.assertEqual(mqtt._length(321), bytes([0xC1, 0x02]))
        topic, payload = mqtt.parse_publish(0, mqtt.publish_packet("a/b", "PRESS")[2:])
        self.assertEqual((topic, payload), ("a/b", "PRESS"))

    def test_decouverte(self):
        configs = mqtt.discovery("recalbox_rfid", "homeassistant", "recalbox_rfid", "1.3.0")
        topics = [topic for topic, _payload in configs]
        self.assertIn("homeassistant/button/recalbox_rfid/poweroff/config", topics)
        self.assertIn("homeassistant/sensor/recalbox_rfid/remaining/config", topics)
        ids = [json.loads(payload)["unique_id"] for _topic, payload in configs]
        self.assertEqual(len(ids), len(set(ids)))
        button = json.loads(dict(configs)["homeassistant/button/recalbox_rfid/quit/config"])
        self.assertEqual(button["command_topic"], "recalbox_rfid/cmd/quit")
        self.assertEqual(button["name"], "Quitter le jeu")

    def test_pont(self):
        client = FakeClient()
        client.incoming = [("recalbox_rfid/cmd/add", "PRESS"), ("recalbox_rfid/cmd/rm -rf", "PRESS")]
        bridge = mqtt.Bridge({"host": "ha.local", "user": "u", "password": "p"}, client_factory=lambda h, p: client)
        bridge.update({"game": "Mario", "playing": True})
        bridge.start()
        deadline = time.time() + 3
        while time.time() < deadline and not any(t == "recalbox_rfid/state" for t, _p, _r in client.published):
            time.sleep(0.02)
        bridge.stop()
        self.assertEqual(client.connected_with[1:3], ("u", "p"))
        self.assertEqual(client.connected_with[3], ("recalbox_rfid/availability", "offline"))
        self.assertIn(("recalbox_rfid/availability", "online", True), client.published)
        self.assertEqual(client.subscribed, ["recalbox_rfid/cmd/#"])
        state = [json.loads(p) for t, p, _r in client.published if t == "recalbox_rfid/state"]
        self.assertEqual(state[0]["game"], "Mario")
        self.assertEqual(bridge.take_commands(), ["add"], "seulement les commandes connues")
        self.assertEqual(client.published[-1], ("recalbox_rfid/availability", "offline", True))

    def test_refus_lisible(self):
        row = {"player": "Lea", "reason": "player_exhausted", "game": "Mario"}
        self.assertEqual(mqtt.refusal_text(row), "Lea · plus de temps de jeu · Mario")
        self.assertEqual(mqtt.refusal_text(None), "")


class LightTest(unittest.TestCase):
    def test_couleurs(self):
        light = led.StatusLight(idle_on=False)
        light.set_state("bedtime")
        self.assertEqual(light.colour(), led.PURPLE, "visible meme sans voyant au repos")
        light.set_state("exhausted")
        self.assertEqual(light.colour(), led.ORANGE)


class WeekSummaryTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="rfid-week-")
        self.addCleanup(shutil.rmtree, self.home, True)
        usage = {"P1": {"2026-11-10": 3600, "2026-11-15": 1200, "2026-11-16": 600},
                 "P2": {"2026-11-12": 900}, "G1": {"2026-11-12": 3000}}
        with open(os.path.join(self.home, "players.json"), "w", encoding="utf-8") as handle:
            json.dump({"usage": usage}, handle)
        with open(os.path.join(self.home, "trophies.json"), "w", encoding="utf-8") as handle:
            json.dump({"P1": {"games:10": "2026-11-12", "consoles:3": "2026-10-01"}}, handle)
        self.players = {"players": [{"uid": "P1", "name": "Lea"}, {"uid": "P2", "name": "Tom"},
                                    {"uid": "G1", "name": "Invite", "guest": True}]}

    def write_config(self, text):
        with open(os.path.join(self.home, "config.ini"), "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_le_lundi(self):
        lines = screen.week_summary(self.home, self.players, "fr", now=MONDAY)
        self.assertEqual(lines[0], ("La semaine dernière : Lea 1 h 20, Tom 15 min", "week"))
        self.assertEqual(lines[1], ("Trophées de la semaine : Lea 1", "trophy"))
        self.assertEqual(screen.week_summary(self.home, self.players, "fr", now=WEDNESDAY), [], "pas le mercredi")

    def test_premier_jour_choisi(self):
        self.write_config("[players]\nweek_start = wednesday\n")
        self.assertTrue(screen.week_summary(self.home, self.players, "fr", now=WEDNESDAY))
        self.assertEqual(screen.week_summary(self.home, self.players, "fr", now=MONDAY), [])


class CartridgeSoundTest(unittest.TestCase):
    def test_son(self):
        feedback = Feedback(enabled=False, player="none")
        self.assertGreater(len(Feedback._clack_wave()), 1000)
        spawned = []
        feedback._spawn = lambda make: spawned.append(make)
        feedback.cartridge()
        self.assertEqual(spawned, [], "option desactivee")
        feedback.card_sound, feedback._player = True, "/usr/bin/paplay"
        feedback.cartridge()
        self.assertEqual(len(spawned), 1)
        feedback.play([(440.0, 0.1)])
        self.assertEqual(len(spawned), 1, "les bips restent coupes")


class AudioEnvTest(unittest.TestCase):
    def test_serveur_de_son_trouve(self):
        from rfid.feedback import audio_env

        root = tempfile.mkdtemp(prefix="rfid-run-")
        self.addCleanup(shutil.rmtree, root, True)
        uid = str(os.getuid()) if hasattr(os, "getuid") else "0"
        os.makedirs(os.path.join(root, uid, "pulse"))
        open(os.path.join(root, uid, "pulse", "native"), "w").close()
        self.assertEqual(audio_env({}, root)["XDG_RUNTIME_DIR"], os.path.join(root, uid))
        self.assertEqual(audio_env({"XDG_RUNTIME_DIR": "/x"}, root)["XDG_RUNTIME_DIR"], "/x", "garde le sien")
        self.assertNotIn("XDG_RUNTIME_DIR", audio_env({}, os.path.join(root, "absent")))


class LookTest(unittest.TestCase):
    def tearDown(self):
        screen.set_theme("dark")

    def test_theme(self):
        self.assertEqual(screen.set_theme("light"), "light")
        self.assertEqual(screen.TEXT, screen.THEMES["light"]["TEXT"])
        self.assertEqual(screen.set_theme("rose"), "dark")
        self.assertEqual(screen.TEXT, (240, 243, 248))


if __name__ == "__main__":
    unittest.main()
