"""Home Assistant over MQTT (option ``[mqtt] enabled``).

The service publishes what the reader does (game running, player, time left,
bedtime, last refused game) on ``<topic>/state`` (JSON, retained) and takes
commands on ``<topic>/cmd/<quit|pause|add|poweroff>``. Home Assistant finds
the device by itself (MQTT discovery, ``homeassistant/...``): sensors, binary
sensors and buttons grouped in one "Recalbox RFID" device.

A small MQTT 3.1.1 client is written here (QoS 0, user name and password):
Recalbox ships no MQTT library for Python. Everything runs in one thread; the
service hands it the state (``update``) and reads the commands
(``take_commands``) in its own loop: nothing of the service is touched from
the thread.
"""

from __future__ import annotations

import json
import select
import socket
import struct
import threading
import time

#: Commands accepted on <topic>/cmd/<name>.
COMMANDS = ("quit", "pause", "add", "poweroff")
KEEPALIVE_S = 60
#: Waits between two connection attempts (seconds), growing up to the last one.
RETRY_S = (5, 10, 30, 60)

CONNECT, CONNACK, PUBLISH, SUBSCRIBE, SUBACK, PINGREQ, PINGRESP, DISCONNECT = 1, 2, 3, 8, 9, 12, 13, 14
CONNACK_ERRORS = {1: "protocole refuse", 2: "identifiant refuse", 3: "serveur indisponible",
                  4: "utilisateur ou mot de passe incorrect", 5: "acces refuse"}


class MqttError(Exception):
    pass


def _length(value: int) -> bytes:
    """MQTT "remaining length": 7 bits per byte."""
    out = bytearray()
    while True:
        byte, value = value % 128, value // 128
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _text(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack("!H", len(data)) + data


def _packet(kind: int, flags: int, body: bytes) -> bytes:
    return bytes([(kind << 4) | flags]) + _length(len(body)) + body


def connect_packet(client_id: str, username: str = "", password: str = "", will=None,
                   keepalive: int = KEEPALIVE_S) -> bytes:
    """CONNECT, clean session; will: (topic, payload) retained."""
    flags = 0x02
    payload = _text(client_id)
    if will:
        flags |= 0x04 | 0x20  # will, retained, QoS 0
        payload += _text(will[0]) + _text(will[1])
    if username:
        flags |= 0x80
        if password:
            flags |= 0x40
    if username:
        payload += _text(username)
        if password:
            payload += _text(password)
    body = _text("MQTT") + bytes([4, flags]) + struct.pack("!H", keepalive) + payload
    return _packet(CONNECT, 0, body)


def publish_packet(topic: str, payload: str, retain: bool = False) -> bytes:
    return _packet(PUBLISH, 0x01 if retain else 0, _text(topic) + payload.encode("utf-8"))


def subscribe_packet(packet_id: int, topic: str) -> bytes:
    return _packet(SUBSCRIBE, 0x02, struct.pack("!H", packet_id) + _text(topic) + b"\x00")


def parse_publish(flags: int, body: bytes):
    """(topic, payload) of a PUBLISH body."""
    size = struct.unpack("!H", body[:2])[0]
    topic = body[2:2 + size].decode("utf-8", "replace")
    rest = body[2 + size:]
    if (flags >> 1) & 0x03:
        rest = rest[2:]  # packet identifier (QoS 1 or 2)
    return topic, rest.decode("utf-8", "replace")


class Client:
    """One connection to the broker."""

    def __init__(self, host: str, port: int = 1883, timeout: float = 10.0, sock_factory=None):
        self.host, self.port, self.timeout = host, int(port), timeout
        self.sock_factory = sock_factory or socket.create_connection
        self.sock = None
        self._buffer = b""
        self._last_sent = 0.0
        self._packet_id = 0

    def connect(self, client_id: str, username: str = "", password: str = "", will=None) -> None:
        self.sock = self.sock_factory((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        self._send(connect_packet(client_id, username, password, will))
        kind, _flags, body = self.read_packet(self.timeout)
        if kind != CONNACK or len(body) < 2:
            raise MqttError("reponse inattendue du serveur MQTT")
        if body[1]:
            raise MqttError(CONNACK_ERRORS.get(body[1], "connexion refusee (%d)" % body[1]))

    def _send(self, data: bytes) -> None:
        if self.sock is None:
            raise MqttError("pas connecte")
        self.sock.sendall(data)
        self._last_sent = time.monotonic()

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self._send(publish_packet(topic, payload, retain))

    def subscribe(self, topic: str) -> None:
        self._packet_id = self._packet_id % 65535 + 1
        self._send(subscribe_packet(self._packet_id, topic))

    def ping_if_due(self) -> None:
        if time.monotonic() - self._last_sent >= KEEPALIVE_S / 2:
            self._send(_packet(PINGREQ, 0, b""))

    def _fill(self, wanted: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while len(self._buffer) < wanted:
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            ready, _w, _x = select.select([self.sock], [], [], left)
            if not ready:
                return False
            data = self.sock.recv(4096)
            if not data:
                raise MqttError("connexion fermee par le serveur MQTT")
            self._buffer += data
        return True

    def read_packet(self, timeout: float):
        """(kind, flags, body), or None when nothing came within ``timeout``."""
        if not self._fill(2, timeout):
            return None
        multiplier, size, index = 1, 0, 1
        while True:
            if not self._fill(index + 1, self.timeout):
                raise MqttError("paquet MQTT incomplet")
            byte = self._buffer[index]
            size += (byte & 0x7F) * multiplier
            multiplier *= 128
            index += 1
            if not byte & 0x80:
                break
            if index > 4:
                raise MqttError("paquet MQTT invalide")
        if not self._fill(index + size, self.timeout):
            raise MqttError("paquet MQTT incomplet")
        header = self._buffer[0]
        body = self._buffer[index:index + size]
        self._buffer = self._buffer[index + size:]
        return header >> 4, header & 0x0F, body

    def close(self, polite: bool = True) -> None:
        if self.sock is None:
            return
        try:
            if polite:
                self.sock.sendall(_packet(DISCONNECT, 0, b""))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None
        self._buffer = b""


#: Names of the entities in Home Assistant.
NAMES = {
    "fr": {"game": "Jeu en cours", "player": "Joueur", "remaining": "Temps restant", "playing": "Partie en cours",
           "paused": "En pause", "bedtime": "Heure du coucher", "refusal": "Dernier jeu refusé",
           "quit": "Quitter le jeu", "pause": "Pause / reprise", "add": "+10 minutes", "poweroff": "Éteindre"},
    "en": {"game": "Game", "player": "Player", "remaining": "Time left", "playing": "Playing", "paused": "Paused",
           "bedtime": "Bedtime", "refusal": "Last refused game", "quit": "Quit the game", "pause": "Pause / resume",
           "add": "+10 minutes", "poweroff": "Turn off"},
}


#: Why a game was refused (refusals.json), as shown in Home Assistant.
REASONS = {
    "fr": {"player_needed": "pas de carte joueur", "player_exhausted": "plus de temps de jeu",
           "guest_exhausted": "plus de temps sans carte joueur", "player_schedule": "en dehors de ses horaires",
           "player_not_allowed": "jeu non autorisé", "guest_expired": "carte invité plus valable",
           "curfew": "heure du coucher", "curfew_now": "heure du coucher"},
    "en": {"player_needed": "no player card", "player_exhausted": "no play time left",
           "guest_exhausted": "no play time left without a player card", "player_schedule": "outside their hours",
           "player_not_allowed": "game not allowed", "guest_expired": "guest card no longer valid",
           "curfew": "bedtime", "curfew_now": "bedtime"},
}


def refusal_text(row, language: str = "fr") -> str:
    """"Lea · plus de temps de jeu · Super Mario World" ("" without a refusal)."""
    if not row:
        return ""
    reasons = REASONS.get(language, REASONS["en"])
    parts = [row.get("player") or "", reasons.get(row.get("reason"), row.get("reason") or ""), row.get("game") or ""]
    return " · ".join(part for part in parts if part)


def discovery(topic: str, prefix: str, node: str, version: str, language: str = "fr") -> list:
    """[(config topic, payload)] of the Home Assistant entities."""
    names = NAMES.get(language, NAMES["en"])
    device = {"identifiers": [node], "name": "Recalbox RFID", "manufacturer": "Recalbox RFID Launcher",
              "model": "RFID reader", "sw_version": version}
    common = {"availability_topic": topic + "/availability", "device": device}
    state = topic + "/state"
    entities = [
        ("sensor", "game", {"state_topic": state, "value_template": "{{ value_json.game }}", "icon": "mdi:gamepad-variant"}),
        ("sensor", "player", {"state_topic": state, "value_template": "{{ value_json.player }}", "icon": "mdi:account"}),
        ("sensor", "remaining", {"state_topic": state, "value_template": "{{ value_json.remaining_min }}",
                                 "unit_of_measurement": "min", "device_class": "duration", "icon": "mdi:timer-sand"}),
        ("binary_sensor", "playing", {"state_topic": state, "value_template": "{{ 'ON' if value_json.playing else 'OFF' }}",
                                      "icon": "mdi:controller"}),
        ("binary_sensor", "paused", {"state_topic": state, "value_template": "{{ 'ON' if value_json.paused else 'OFF' }}",
                                     "icon": "mdi:pause"}),
        ("binary_sensor", "bedtime", {"state_topic": state, "value_template": "{{ 'ON' if value_json.bedtime else 'OFF' }}",
                                      "icon": "mdi:weather-night"}),
        ("sensor", "refusal", {"state_topic": state, "value_template": "{{ value_json.refusal }}",
                               "json_attributes_topic": state,
                               "json_attributes_template": "{{ value_json.refusal_info | tojson }}",
                               "icon": "mdi:cancel"}),
    ]
    for command, icon in (("quit", "mdi:exit-to-app"), ("pause", "mdi:play-pause"), ("add", "mdi:timer-plus"),
                          ("poweroff", "mdi:power")):
        entities.append(("button", command, {"command_topic": "%s/cmd/%s" % (topic, command), "payload_press": "PRESS",
                                             "icon": icon}))
    result = []
    for component, key, extra in entities:
        config = dict(common, name=names[key], unique_id="%s_%s" % (node, key), object_id="%s_%s" % (node, key))
        config.update(extra)
        result.append(("%s/%s/%s/%s/config" % (prefix, component, node, key), json.dumps(config, ensure_ascii=False)))
    return result


class Bridge:
    """The thread that keeps the connection, publishes the state and takes the commands."""

    def __init__(self, settings: dict, log=None, version: str = "", language: str = "fr", client_factory=None):
        self.settings = dict(settings)
        self.log = log
        self.version = version
        self.language = language
        self.client_factory = client_factory or (lambda host, port: Client(host, port))
        self.topic = (self.settings.get("topic") or "recalbox_rfid").strip("/")
        self.node = self.topic.replace("/", "_")
        self._state = None
        self._published = None
        self._commands = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.connected = False
        self.error = ""

    # ---- called by the service
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="rfid-mqtt", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)

    def update(self, state: dict) -> None:
        with self._lock:
            self._state = dict(state)

    def take_commands(self) -> list:
        with self._lock:
            commands, self._commands = self._commands, []
        return commands

    def status(self) -> dict:
        return {"connected": self.connected, "error": self.error}

    # ---- the thread
    def _say(self, level: str, message: str) -> None:
        if self.log:
            getattr(self.log, level)(message)

    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            client = self.client_factory(self.settings.get("host") or "", int(self.settings.get("port") or 1883))
            try:
                self._session(client)
                attempt = 0
            except (OSError, MqttError, ValueError) as exc:
                if self.error != str(exc):
                    self._say("warning", "MQTT : %s" % exc)
                self.error = str(exc) or exc.__class__.__name__
            finally:
                if self.connected:
                    self._say("info", "MQTT : deconnecte")
                self.connected = False
                client.close(polite=self._stop.is_set())
            if self._stop.is_set():
                break
            self._stop.wait(RETRY_S[min(attempt, len(RETRY_S) - 1)])
            attempt += 1

    def _session(self, client) -> None:
        availability = self.topic + "/availability"
        client.connect("recalbox-rfid-%s" % self.node, self.settings.get("user") or "",
                       self.settings.get("password") or "", will=(availability, "offline"))
        self.connected, self.error = True, ""
        self._say("info", "MQTT : connecte a %s" % self.settings.get("host"))
        prefix = (self.settings.get("discovery") or "homeassistant").strip("/")
        for config_topic, payload in discovery(self.topic, prefix, self.node, self.version, self.language):
            client.publish(config_topic, payload, retain=True)
        client.publish(availability, "online", retain=True)
        client.subscribe(self.topic + "/cmd/#")
        self._published = None
        while not self._stop.is_set():
            with self._lock:
                state = self._state
            if state is not None and state != self._published:
                client.publish(self.topic + "/state", json.dumps(state, ensure_ascii=False), retain=True)
                self._published = state
            packet = client.read_packet(1.0)
            if packet is not None and packet[0] == PUBLISH:
                topic, payload = parse_publish(packet[1], packet[2])
                command = topic.rsplit("/", 1)[-1]
                if topic.startswith(self.topic + "/cmd/") and command in COMMANDS:
                    self._say("info", "MQTT : commande %s" % command)
                    with self._lock:
                        self._commands.append(command)
            client.ping_if_due()
        client.publish(availability, "offline", retain=True)
