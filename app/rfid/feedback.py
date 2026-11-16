"""User feedback: beeps (no external dependency).

The Recalbox interface unfortunately exposes no API to show a notification
from a script (the frontend only publishes its events over MQTT, it listens
to nothing). The reliable immediate feedback is therefore:

* the game launch itself (the frontend shows the game loading screen);
* a short beep, generated on the fly (WAV) and played by ``paplay``
  (PulseAudio, used by Recalbox) or ``aplay`` (ALSA), both shipped in the image.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import struct
import subprocess
import tempfile

SAMPLE_RATE = 22050


#: Sounds of the cartridges (files of the "sounds" folder; None: synthetic).
CARD_SOUNDS = {
    "ds_insert": "ds-insert.wav",
    "ds_remove": "ds-remove.wav",
    "n64_insert": "n64-insert.wav",
    "n64_remove": "n64-remove.wav",
    "snes": "snes.wav",
    "snes_dry": "snes-dry.wav",
    "snes_full": "snes-full.wav",
    "synth": None,
}
SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
#: [feedback] card_sound (a game card starts its game) and card_out_sound
#: (the card of the running game is removed): defaults.
DEFAULT_IN, DEFAULT_OUT = "ds_insert", "ds_remove"


def card_sound_style(value, default: str = DEFAULT_IN) -> str:
    """A key of CARD_SOUNDS or "off" (1 and 0 of the first version: the
    default sound and "off"; "ds": the DS sound)."""
    text = str(value if value is not None else "").strip().lower()
    if text in CARD_SOUNDS or text == "off":
        return text
    if text == "ds":
        return default
    if text in ("1", "true", "yes", "on", "oui"):
        return default
    if text in ("0", "false", "no", "non"):
        return "off"
    return default


def scaled_wav(path: str, volume, cache_dir: str) -> str:
    """A 16-bit PCM WAV at ``volume`` percent (written once in ``cache_dir``)."""
    try:
        volume = max(0, min(100, int(volume)))
    except (TypeError, ValueError):
        volume = 100
    if volume >= 100:
        return path
    target = os.path.join(cache_dir, "%s-v%d.wav" % (os.path.splitext(os.path.basename(path))[0], volume))
    if os.path.isfile(target) and os.path.getmtime(target) >= os.path.getmtime(path):
        return target
    from array import array
    import sys

    with open(path, "rb") as handle:
        data = handle.read()
    start = data.find(b"data")
    if data[:4] != b"RIFF" or start < 0:
        return path
    size = struct.unpack("<I", data[start + 4:start + 8])[0]
    samples = array("h")
    samples.frombytes(data[start + 8:start + 8 + size - size % 2])
    if sys.byteorder != "little":
        samples.byteswap()
    factor = volume / 100.0
    scaled = array("h", (int(value * factor) for value in samples))
    if sys.byteorder != "little":
        scaled.byteswap()
    os.makedirs(cache_dir, exist_ok=True)
    temporary = target + ".tmp"
    with open(temporary, "wb") as handle:
        handle.write(data[:start + 8] + scaled.tobytes() + data[start + 8 + len(scaled) * 2:])
    os.replace(temporary, target)
    return target


def audio_env(environ=None, runtime_root: str = "/run/user") -> dict:
    """Environment for paplay: the PulseAudio of Recalbox runs for root with
    XDG_RUNTIME_DIR=/run/user/0. A service started without it (by the
    installer, over SSH...) would not find the sound server."""
    env = dict(os.environ if environ is None else environ)
    if env.get("PULSE_SERVER") or env.get("XDG_RUNTIME_DIR"):
        return env
    getuid = getattr(os, "getuid", None)
    folder = os.path.join(runtime_root, str(getuid() if getuid else 0))
    if os.path.exists(os.path.join(folder, "pulse", "native")):
        env["XDG_RUNTIME_DIR"] = folder
    return env


class Feedback:
    """Confirmation beeps, silent when no audio player is available."""

    def __init__(self, enabled: bool = True, player: str = "auto", log=None, card_sound="off", card_out_sound="off",
                 card_volume: int = 100):
        self.log = log
        self.enabled = bool(enabled)
        #: The "clack" of a cartridge when a game card starts its game (its own setting).
        self.card_sound = card_sound_style(card_sound, DEFAULT_IN)
        self.card_out_sound = card_sound_style(card_out_sound, DEFAULT_OUT)
        #: Volume of the cartridge sounds, in percent of the files.
        self.card_volume = card_volume
        self.requested_player = (player or "auto").lower()
        self._player = None
        self._cache_dir = os.path.join(tempfile.gettempdir(), "rfid-launcher")
        self._failed = 0
        if self.enabled or self.cards_on():
            wanted = self.enabled
            self._detect_player()
            self.enabled = wanted and bool(self._player)

    # ------------------------------------------------------------------ interne
    def _candidates(self):
        if self.requested_player not in ("auto", ""):
            return [self.requested_player]
        return ["paplay", "aplay"]

    def _detect_player(self) -> None:
        for name in self._candidates():
            path = shutil.which(name)
            if not path:
                continue
            # A real attempt: paplay fails if the PulseAudio server cannot be
            # reached, aplay if the sound card is busy.
            try:
                sample = self._wav_file([(880.0, 0.01)])
                result = subprocess.run(
                    [path, sample],
                    env=audio_env(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                    check=False,
                )
                if result.returncode == 0:
                    self._player = path
                    if self.log:
                        self.log.info("Retour sonore actif (%s)" % os.path.basename(path))
                    return
            except (OSError, subprocess.SubprocessError):
                continue
        self.enabled = False
        if self.log:
            self.log.info("Retour sonore indisponible (pas de lecteur audio utilisable)")

    @staticmethod
    def _tone_wave(frequency: float, duration: float, volume: float = 0.25) -> bytes:
        """Generates a 16-bit mono sine with fade in/out."""
        frames = max(1, int(SAMPLE_RATE * duration))
        fade = max(1, min(frames // 4, int(SAMPLE_RATE * 0.005)))
        data = bytearray()
        for index in range(frames):
            envelope = 1.0
            if index < fade:
                envelope = index / fade
            elif index > frames - fade:
                envelope = max(0.0, (frames - index) / fade)
            sample = volume * envelope * math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE)
            data += struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
        return bytes(data)

    def _wav_file(self, tones) -> str:
        """Writes (once) the WAV matching a sequence of (frequency, duration)."""
        digest = hashlib.sha1(repr(tones).encode("utf-8")).hexdigest()[:12]
        path = os.path.join(self._cache_dir, "beep-%s.wav" % digest)
        if os.path.isfile(path):
            return path
        os.makedirs(self._cache_dir, exist_ok=True)
        samples = b"".join(self._tone_wave(freq, duration) for freq, duration in tones)
        header = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
        header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        header += b"data" + struct.pack("<I", len(samples))
        temporary = path + ".tmp"
        with open(temporary, "wb") as handle:
            handle.write(header + samples)
        os.replace(temporary, path)
        return path

    @staticmethod
    def _clack_wave() -> bytes:
        """A cartridge pushed into its slot: a click, a low thump, then the latch."""
        import random

        rng = random.Random(7)  # the same sound every time
        frames = int(SAMPLE_RATE * 0.16)
        latch = int(SAMPLE_RATE * 0.075)
        data = bytearray()
        for index in range(frames):
            t = index / SAMPLE_RATE
            sample = 0.55 * rng.uniform(-1, 1) * math.exp(-t / 0.004)              # click
            sample += 0.5 * math.sin(2 * math.pi * 110 * t) * math.exp(-t / 0.03)  # thump
            if index >= latch:
                tl = (index - latch) / SAMPLE_RATE
                sample += 0.35 * rng.uniform(-1, 1) * math.exp(-tl / 0.003)        # latch
                sample += 0.25 * math.sin(2 * math.pi * 1800 * tl) * math.exp(-tl / 0.006)
            data += struct.pack("<h", int(max(-1.0, min(1.0, sample * 0.6)) * 32767))
        return bytes(data)

    def _clack_file(self) -> str:
        path = os.path.join(self._cache_dir, "cartridge-1.wav")
        if os.path.isfile(path):
            return path
        os.makedirs(self._cache_dir, exist_ok=True)
        samples = self._clack_wave()
        header = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
        header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        header += b"data" + struct.pack("<I", len(samples))
        temporary = path + ".tmp"
        with open(temporary, "wb") as handle:
            handle.write(header + samples)
        os.replace(temporary, path)
        return path

    def cards_on(self) -> bool:
        return self.card_sound != "off" or self.card_out_sound != "off"

    def _card_file(self, style: str, volume=None):
        """Path of a cartridge sound (the synthetic clack when its file is
        missing), at ``volume`` percent (default: self.card_volume)."""
        name = CARD_SOUNDS.get(style)
        path = None
        if name:
            path = os.path.join(SOUNDS_DIR, name)
            if not os.path.isfile(path):
                path = None
        path = path or self._clack_file()
        volume = self.card_volume if volume is None else volume
        return scaled_wav(path, volume, self._cache_dir)

    def cartridge(self) -> None:
        """A game card starts its game (option [feedback] card_sound)."""
        style = self.card_sound
        if style != "off" and self._player:
            self._spawn(lambda: self._card_file(style))

    def cartridge_out(self) -> None:
        """The game card of the running game is removed (option [feedback] card_out_sound)."""
        style = self.card_out_sound
        if style != "off" and self._player:
            self._spawn(lambda: self._card_file(style))

    def play(self, tones) -> None:
        """Plays a sequence of beeps; never blocks the caller."""
        if not self.enabled:
            return
        self._spawn(lambda: self._wav_file(tones))

    def _spawn(self, make) -> None:
        if not self._player or self._failed >= 3:
            return
        try:
            wav = make()
            from . import music

            if music.screen_mixing():
                music.queue_sound(wav)  # played over the music by the reader screen
                return
            subprocess.Popen(
                [self._player, wav],
                env=audio_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            self._failed += 1
            if self.log:
                self.log.warning("Lecture du bip impossible : %s" % exc)

    # ------------------------------------------------------------------ signaux
    def ok(self) -> None:
        """Badge reconnu / lancement."""
        self.play([(880.0, 0.06), (1318.0, 0.09)])

    def recognized(self) -> None:
        """Badge recognized without action (action = none, "cartridge" mode)."""
        self.play([(1046.0, 0.07)])

    def removed(self) -> None:
        """Badge efface."""
        self.play([(784.0, 0.06), (587.0, 0.09)])

    def armed(self) -> None:
        """Association mode armed (short press on the button)."""
        self.play([(1318.0, 0.07)])

    def armed_delete(self) -> None:
        """Delete mode armed (from the web interface)."""
        self.play([(659.0, 0.07), (659.0, 0.07)])

    def error(self) -> None:
        """Badge inconnu ou action refusee."""
        self.play([(233.0, 0.16), (196.0, 0.18)])

    def timeout(self) -> None:
        """The armed mode has expired."""
        self.play([(392.0, 0.10), (330.0, 0.10), (262.0, 0.12)])
