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


class Feedback:
    """Confirmation beeps, silent when no audio player is available."""

    def __init__(self, enabled: bool = True, player: str = "auto", log=None, card_sound: bool = False):
        self.log = log
        self.enabled = bool(enabled)
        #: The "clack" of a cartridge when a game card starts its game (its own setting).
        self.card_sound = bool(card_sound)
        self.requested_player = (player or "auto").lower()
        self._player = None
        self._cache_dir = os.path.join(tempfile.gettempdir(), "rfid-launcher")
        self._failed = 0
        if self.enabled or self.card_sound:
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

    def cartridge(self) -> None:
        """A game card starts its game (option [feedback] card_sound)."""
        if self.card_sound and self._player:
            self._spawn(self._clack_file)

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
            subprocess.Popen(
                [self._player, wav],
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
