"""Background music of the reader screen and volume of the Recalbox."""

from __future__ import annotations

import os
import random
import shutil
import tempfile
import unittest
from types import SimpleNamespace

import support  # noqa: F401 - puts app/ on the path
from rfid import music, volume


class FakeMixer:
    """SDL2 and SDL2_mixer: what was asked."""

    def __init__(self):
        self.calls, self.playing, self.loaded = [], True, []

    def SDL_InitSubSystem(self, flags):
        return 0

    def Mix_OpenAudio(self, *args):
        return 0

    def Mix_VolumeMusic(self, value):
        self.calls.append(("volume", value))

    def Mix_LoadMUS(self, path):
        self.loaded.append(os.path.basename(path.decode()))
        return len(self.loaded)

    def Mix_FadeInMusic(self, track, loops, ms):
        self.calls.append(("play", track))
        self.playing = True

    def Mix_PlayingMusic(self):
        return self.playing

    def Mix_FreeMusic(self, track):
        pass

    def Mix_FadeOutMusic(self, ms):
        pass

    def Mix_HaltMusic(self):
        self.calls.append(("halt",))

    def Mix_CloseAudio(self):
        self.calls.append(("close",))


class MusicTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rfid-music-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        theme = os.path.join(self.dir, "themes", "recalbox-next", "data", "music")
        os.makedirs(theme)
        self.user = os.path.join(self.dir, "music")
        os.makedirs(self.user)
        for folder, name in ((theme, "Main Theme 00.ogg"), (theme, "Main Theme 01.ogg"), (self.user, "Mine.mp3"),
                             (self.user, "readme.txt")):
            open(os.path.join(folder, name), "w").close()

    def test_morceaux(self):
        found = music.tracks({}, themes=os.path.join(self.dir, "themes"), user=self.user)
        self.assertEqual([os.path.basename(path) for path in found], ["Main Theme 00.ogg", "Main Theme 01.ogg", "Mine.mp3"])

    def test_reglages(self):
        conf = {"audio.bgmusic": "1", "audio.music.volume": "60"}
        self.assertEqual(music.settings("recalbox", "recalbox", conf), (True, 60))
        self.assertEqual(music.settings("recalbox", "30", conf), (True, 30))
        self.assertEqual(music.settings("recalbox", "recalbox", dict(conf, **{"audio.bgmusic": "0"}))[0], False)
        self.assertEqual(music.settings("on", "recalbox", {"audio.bgmusic": "0"}), (True, 60))
        self.assertEqual(music.settings("off", "80", conf), (False, 0))

    def test_lecture(self):
        mixer = FakeMixer()
        files = music.tracks({}, themes=os.path.join(self.dir, "themes"), user=self.user)
        clock = support.FakeClock()
        player = music.Music(files, 60, popup_s=3, loader=lambda: (mixer, mixer), rng=random.Random(1), clock=clock)
        self.assertTrue(player.start())
        self.assertIn(("volume", 77), mixer.calls, "60 % de 128")
        first = player.current
        self.assertEqual(player.popup(), music.title(first))
        self.assertIsNone(player.popup(), "une seule fois")
        mixer.playing = False
        clock.advance(1)
        player.step()
        self.assertNotEqual(player.current, first, "jamais deux fois de suite")
        player.stop()
        self.assertEqual(mixer.calls[-1], ("close",))

    def test_sons_courts_par_l_ecran(self):
        mixer = FakeMixer()
        played = []
        mixer.SDL_RWFromFile = lambda path, mode: path
        mixer.Mix_LoadWAV_RW = lambda rw, free: rw
        mixer.Mix_PlayChannelTimed = lambda channel, chunk, loops, ticks: played.append(chunk)
        flag, queue = os.path.join(self.dir, "mixer.pid"), os.path.join(self.dir, "sounds.txt")
        self.assertFalse(music.screen_mixing(flag))
        player = music.Music(["a.ogg"], 60, loader=lambda: (mixer, mixer), flag=flag, queue=queue,
                             clock=support.FakeClock())
        self.assertTrue(player.start())
        self.assertTrue(music.screen_mixing(flag), "le service sait que l'ecran mixe")
        music.queue_sound("/s/ds-insert.wav", queue)
        music.queue_sound("/s/beep.wav", queue)
        player.step()
        self.assertEqual(played, [b"/s/ds-insert.wav", b"/s/beep.wav"])
        player.step()
        self.assertEqual(len(played), 2, "joues une seule fois")
        player.stop()
        self.assertFalse(music.screen_mixing(flag))

    def test_fondu_de_sortie(self):
        mixer = FakeMixer()
        mixer.Mix_FadeOutMusic = lambda ms: mixer.calls.append(("fade", ms))
        clock = support.FakeClock()
        player = music.Music(["a.ogg", "b.ogg"], 60, loader=lambda: (mixer, mixer), clock=clock,
                             flag=os.path.join(self.dir, "f.pid"), queue=os.path.join(self.dir, "q.txt"))
        player.start()
        player.fade_out(450)
        player.fade_out(450)
        self.assertEqual([c for c in mixer.calls if c[0] == "fade"], [("fade", 450)], "une seule fois")
        mixer.playing = False
        clock.advance(1)
        played = len([c for c in mixer.calls if c[0] == "play"])
        player.step()
        self.assertEqual(len([c for c in mixer.calls if c[0] == "play"]), played, "pas d'autre morceau")
        player.stop()
        self.assertEqual([c for c in mixer.calls if c[0] == "fade"], [("fade", 450)], "pas de second fondu")

    def test_voile_noir(self):
        from rfid.screen import black_alpha

        self.assertEqual(black_alpha(0, 0.6), 255)
        self.assertEqual(black_alpha(0.6, 0.6), 0)
        self.assertTrue(0 < black_alpha(0.3, 0.6) < 255)
        self.assertEqual(black_alpha(0, 0.45, True), 0)
        self.assertEqual(black_alpha(0.45, 0.45, True), 255)
        self.assertEqual(black_alpha(0, 0.45, True, start=200), 200, "depuis un fondu d'entree coupe")

    def test_noir_avant_le_fondu(self):
        from rfid.screen import screen_hold

        self.assertEqual(screen_hold({}), 0.0)
        self.assertEqual(screen_hold({"RFID_SCREEN_HOLD": "3.0"}), 3.0)
        self.assertEqual(screen_hold({"RFID_SCREEN_HOLD": "99"}), 10.0)
        self.assertEqual(screen_hold({"RFID_SCREEN_HOLD": "x"}), 0.0)

    def test_sans_musique(self):
        self.assertFalse(music.Music([], 60, loader=lambda: (FakeMixer(), FakeMixer())).start())
        self.assertFalse(music.Music(["a.ogg"], 0, loader=lambda: (FakeMixer(), FakeMixer())).start())


class VolumeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rfid-volume-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.conf = os.path.join(self.dir, "recalbox.conf")
        with open(self.conf, "w", encoding="utf-8") as handle:
            handle.write("## volume\naudio.volume=90\naudio.bgmusic=1\n")

    def test_lecture_et_ecriture(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout="Volume: front-left: 52429 /  80% / -5.81 dB")

        self.assertEqual(volume.current(run, self.conf), 80, "la sortie son d'abord")
        self.assertTrue(volume.apply(85, run))
        self.assertEqual(calls[-1], ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "85%"])
        self.assertTrue(volume.save(85, self.conf))
        self.assertFalse(volume.save(85, self.conf), "deja enregistre")
        self.assertEqual(volume.read_saved(self.conf), 85)
        with open(self.conf, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "## volume\naudio.volume=85\naudio.bgmusic=1\n")

    def test_sans_pactl(self):
        def run(args, **kwargs):
            raise OSError("pactl absent")

        self.assertEqual(volume.current(run, self.conf), 90, "recalbox.conf ensuite")


if __name__ == "__main__":
    unittest.main()
