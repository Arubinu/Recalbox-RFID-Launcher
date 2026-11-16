"""Background music of the reader screen, like Recalbox's interface.

Recalbox's interface plays, at random, the music of its theme
(``themes/<theme>/data/music``) and the user's music (``MusicDirectory`` of
es_settings.cfg, ``/recalbox/share/music`` by default), with SDL2_mixer, at
``audio.music.volume`` percent when ``audio.bgmusic=1`` (recalbox.conf). The
reader screen does the same with the same library, called through ctypes
(pygame of Recalbox has no mixer module). The name of a new track can be
shown like Recalbox's popup (``MusicPopupTime``, seconds, 0 = never).

The screen quits before each game: the music stops with it, and another
track starts when the screen comes back.

While the music plays, the short sounds of the service (cartridge sounds,
beeps) are played by the screen too, in the same mixer (``SOUND_QUEUE``):
started by paplay, a new PulseAudio stream makes the Pi's output rewind,
and the music jumps a little.
"""

from __future__ import annotations

import ctypes
import os
import random
import re
import time

from .es_command import read_conf

THEMES = "/recalbox/share_init/system/.emulationstation/themes"
ES_SETTINGS = "/recalbox/share/system/.emulationstation/es_settings.cfg"
USER_MUSIC = "/recalbox/share/music"
EXTENSIONS = (".ogg", ".mp3", ".flac", ".wav", ".mod", ".xm", ".s3m", ".it", ".opus")
#: Written while the music plays (the pid of the screen); RAM.
MIXER_FLAG = "/tmp/rfid-screen-mixer.pid"
#: Paths of WAV files to play, one per line (added by the service).
SOUND_QUEUE = "/tmp/rfid-screen-sounds.txt"
FADE_IN_MS = 1000
FADE_OUT_MS = 300
SDL_INIT_AUDIO = 0x10
AUDIO_S16SYS = 0x8010


def es_setting(name: str, path: str = ES_SETTINGS) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    except OSError:
        return ""
    found = re.search(r'name="%s"\s+value="([^"]*)"' % re.escape(name), content)
    return found.group(1) if found else ""


def theme_name(conf: dict) -> str:
    """The theme of Recalbox's interface (recalbox-next by default)."""
    return es_setting("ThemeSet") or str(conf.get("emulationstation.theme.folder") or "") or "recalbox-next"


def tracks(conf: dict, themes: str = THEMES, user: str = None) -> list:
    """Every music file: the theme's, then the user's."""
    folders = [os.path.join(themes, theme_name(conf), "data", "music"),
               user or es_setting("MusicDirectory") or USER_MUSIC]
    found = []
    for folder in folders:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        found += [os.path.join(folder, name) for name in names if name.lower().endswith(EXTENSIONS)]
    return found


def title(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def settings(enabled: str, volume: str, conf: dict):
    """(on, volume percent) from the options of the reader screen
    ("recalbox": like Recalbox's interface) and recalbox.conf."""
    if enabled == "off":
        return False, 0
    on = str(conf.get("audio.bgmusic", "1")).strip() != "0" if enabled == "recalbox" else True
    if volume == "recalbox" or not str(volume).strip().isdigit():
        try:
            percent = int(float(conf.get("audio.music.volume", 60)))
        except (TypeError, ValueError):
            percent = 60
    else:
        percent = int(volume)
    return on, max(0, min(100, percent))


def screen_mixing(flag: str = MIXER_FLAG) -> bool:
    """True while the reader screen plays music (and takes the short sounds)."""
    try:
        with open(flag, "r", encoding="ascii") as handle:
            pid = int(handle.read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def queue_sound(path: str, queue: str = SOUND_QUEUE) -> None:
    with open(queue, "a", encoding="utf-8") as handle:
        handle.write(path + "\n")


def take_sounds(queue: str = SOUND_QUEUE) -> list:
    """The sounds waiting (the queue is emptied)."""
    taking = queue + ".taking"
    try:
        os.replace(queue, taking)
    except OSError:
        return []
    try:
        with open(taking, "r", encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except OSError:
        return []
    finally:
        try:
            os.remove(taking)
        except OSError:
            pass


class Music:
    """One track after the other, at random (never the same twice in a row)."""

    def __init__(self, files, volume: int, popup_s: float = 0.0, loader=None, rng=None, clock=None,
                 flag: str = MIXER_FLAG, queue: str = SOUND_QUEUE):
        self.files = list(files)
        self.volume = volume
        self.popup_s = popup_s
        self.rng = rng or random.Random()
        self.clock = clock or time.monotonic
        self.lib = None
        self.mix = None
        self.current = None
        self.track = None
        self.next_check = 0.0
        self.announce = None
        self._loader = loader
        self.flag, self.queue = flag, queue
        self.chunks = {}

    def _load_libraries(self):
        if self._loader is not None:
            return self._loader()
        sdl = ctypes.CDLL("libSDL2-2.0.so.0")
        mix = ctypes.CDLL("libSDL2_mixer-2.0.so.0")
        mix.Mix_LoadMUS.restype = ctypes.c_void_p
        mix.Mix_LoadMUS.argtypes = [ctypes.c_char_p]
        mix.Mix_FadeInMusic.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        mix.Mix_FreeMusic.argtypes = [ctypes.c_void_p]
        sdl.SDL_RWFromFile.restype = ctypes.c_void_p
        sdl.SDL_RWFromFile.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        mix.Mix_LoadWAV_RW.restype = ctypes.c_void_p
        mix.Mix_LoadWAV_RW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        mix.Mix_PlayChannelTimed.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        return sdl, mix

    def start(self) -> bool:
        """Opens the sound and plays a first track. False: no music."""
        if not self.files or self.volume <= 0:
            return False
        try:
            sdl, mix = self._load_libraries()
            if sdl.SDL_InitSubSystem(SDL_INIT_AUDIO) != 0 or mix.Mix_OpenAudio(44100, AUDIO_S16SYS, 2, 2048) != 0:
                return False
        except OSError:
            return False
        self.lib, self.mix = sdl, mix
        self.set_volume(self.volume)
        self._next()
        take_sounds(self.queue)  # old requests: not played now
        try:
            with open(self.flag, "w", encoding="ascii") as handle:
                handle.write("%d\n" % os.getpid())
        except OSError:
            pass
        return True

    def play_sound(self, path: str) -> None:
        """A short sound over the music (same mixer: no new output stream)."""
        chunk = self.chunks.get(path)
        if chunk is None:
            rw = self.lib.SDL_RWFromFile(path.encode("utf-8"), b"rb")
            chunk = self.mix.Mix_LoadWAV_RW(rw, 1) if rw else None
            if not chunk:
                return
            self.chunks[path] = chunk
        self.mix.Mix_PlayChannelTimed(-1, chunk, 0, -1)

    def set_volume(self, percent: int) -> None:
        self.volume = max(0, min(100, int(percent)))
        if self.mix is not None:
            self.mix.Mix_VolumeMusic(int(round(128 * self.volume / 100.0)))

    def _next(self) -> None:
        choices = [path for path in self.files if path != self.current] or self.files
        for _attempt in range(len(choices)):
            path = self.rng.choice(choices)
            track = self.mix.Mix_LoadMUS(path.encode("utf-8"))
            if track:
                if self.track:
                    self.mix.Mix_FreeMusic(self.track)
                self.track, self.current = track, path
                self.mix.Mix_FadeInMusic(track, 1, FADE_IN_MS)
                if self.popup_s > 0:
                    self.announce = title(path)
                return
            choices = [other for other in choices if other != path] or choices

    def step(self) -> None:
        """To call often: the next track when one ends."""
        if self.mix is None:
            return
        for path in take_sounds(self.queue):
            self.play_sound(path)
        now = self.clock()
        if now < self.next_check:
            return
        self.next_check = now + 0.5
        if not self.mix.Mix_PlayingMusic():
            self._next()

    def popup(self):
        """The title of the track that just started (once), or None."""
        text, self.announce = self.announce, None
        return text

    def stop(self) -> None:
        if self.mix is None:
            return
        try:
            os.remove(self.flag)  # the service plays its sounds itself again
        except OSError:
            pass
        try:
            self.mix.Mix_FadeOutMusic(FADE_OUT_MS)
            time.sleep(FADE_OUT_MS / 1000.0)
            self.mix.Mix_HaltMusic()
            if self.track:
                self.mix.Mix_FreeMusic(self.track)
            self.mix.Mix_CloseAudio()
        except Exception:  # noqa: BLE001 - the screen quits anyway
            pass
        self.mix = self.track = None
        self.chunks = {}
        # Asked while the screen was quitting: played the usual way.
        for path in take_sounds(self.queue):
            try:
                import shutil
                import subprocess

                from .feedback import audio_env

                player = shutil.which("paplay") or shutil.which("aplay")
                if player:
                    subprocess.Popen([player, path], env=audio_env(), stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                pass
