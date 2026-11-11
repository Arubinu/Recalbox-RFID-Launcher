"""Retours utilisateur : bips sonores (aucune dependance externe).

L'interface Recalbox n'expose malheureusement aucune API permettant d'afficher
une notification depuis un script (le frontend ne fait qu'ecrire ses evenements
en MQTT, il n'ecoute rien). Le retour immediat fiable est donc :

* le lancement du jeu lui-meme (le frontend affiche l'ecran de chargement du jeu) ;
* un bip sonore court, genere a la volee (WAV) et joue par ``paplay`` (PulseAudio,
  utilise par Recalbox) ou ``aplay`` (ALSA), tous deux fournis par l'image.
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
    """Bips de confirmation, silencieux si aucun lecteur audio n'est disponible."""

    def __init__(self, enabled: bool = True, player: str = "auto", log=None):
        self.log = log
        self.enabled = bool(enabled)
        self.requested_player = (player or "auto").lower()
        self._player = None
        self._cache_dir = os.path.join(tempfile.gettempdir(), "rfid-launcher")
        self._failed = 0
        if self.enabled:
            self._detect_player()

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
            # Un essai reel : paplay echoue si le serveur PulseAudio n'est pas
            # joignable, aplay si la carte son est occupee.
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
        """Genere un sinus 16 bits mono avec fondu d'entree/sortie."""
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
        """Ecrit (une fois) le WAV correspondant a une suite de (frequence, duree)."""
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

    def play(self, tones) -> None:
        """Joue une suite de bips ; jamais bloquant pour l'appelant."""
        if not self.enabled or not self._player or self._failed >= 3:
            return
        try:
            wav = self._wav_file(tones)
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

    def armed(self) -> None:
        """Mode association arme (appui court sur le bouton)."""
        self.play([(1318.0, 0.07)])

    def armed_delete(self) -> None:
        """Mode suppression arme (appui long sur le bouton)."""
        self.play([(659.0, 0.07), (659.0, 0.07)])

    def error(self) -> None:
        """Badge inconnu ou action refusee."""
        self.play([(233.0, 0.16), (196.0, 0.18)])

    def timeout(self) -> None:
        """Le mode arme a expire."""
        self.play([(392.0, 0.10), (330.0, 0.10), (262.0, 0.12)])
