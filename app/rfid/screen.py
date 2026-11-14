"""The reader screen: shown instead of Recalbox's interface (option).

An attract screen drawn with pygame (SDL2, the same library as Recalbox's
interface) from the Recalbox theme itself: one console at a time in the
spotlight (its drawing, its logo, its number of games, on a glow of its
colour), a band with the logos of every console that has games, the clock,
and the active player with their play time. Games start with the cards.

No sound and no controller are opened: the screen must never hold a device
the next game needs. It quits on SIGTERM (the service stops it before a
game and starts it again afterwards).

``RFID_SCREEN_ASSETS`` points to a copy of the theme files (preview on a
computer: ``python -m rfid.screen --preview out.png``).
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import signal
import sys
import threading
import time

from .es_command import ROMS_DIRS, read_conf
from .osd import recalbox_language

STATUS_FILENAME = "status.json"
THEME = "/recalbox/share_init/system/.emulationstation/themes/recalbox-next/data"
PATHS = {
    "systemlist": "/recalbox/share_init/system/.emulationstation/systemlist.xml",
    "logos": "/recalbox/system/resources/logos",
    "arts": THEME + "/arts/systems_assets",
    "fonts": THEME + "/fonts",
}
#: Seconds a console stays in the spotlight, and length of the change.
HOLD_S = 7.0
FADE_S = 0.9

TEXTS = {
    "hint": {"fr": "Pose une carte pour jouer", "en": "Place a card to play", "de": "Leg eine Karte auf, um zu spielen",
             "es": "Pon una tarjeta para jugar", "it": "Appoggia una carta per giocare", "pt": "Pousa um cartão para jogar"},
    "games": {"fr": "jeux", "en": "games", "de": "Spiele", "es": "juegos", "it": "giochi", "pt": "jogos"},
    "game": {"fr": "jeu", "en": "game", "de": "Spiel", "es": "juego", "it": "gioco", "pt": "jogo"},
    "left": {"fr": "{t} restantes", "en": "{t} left", "de": "noch {t}", "es": "quedan {t}", "it": "{t} rimasti",
             "pt": "faltam {t}"},
    "unlimited": {"fr": "sans limite", "en": "no limit", "de": "ohne Limit", "es": "sin límite", "it": "senza limiti",
                  "pt": "sem limite"},
    "played": {"fr": "{t} jouées aujourd'hui", "en": "{t} played today", "de": "heute {t} gespielt",
               "es": "{t} jugados hoy", "it": "{t} giocati oggi", "pt": "{t} jogados hoje"},
    "played_week": {"fr": "{t} jouées cette semaine", "en": "{t} played this week", "de": "diese Woche {t} gespielt",
                    "es": "{t} jugados esta semana", "it": "{t} giocati questa settimana", "pt": "{t} jogados esta semana"},
    "guest": {"fr": "Invité", "en": "Guest", "de": "Gast", "es": "Invitado", "it": "Ospite", "pt": "Convidado"},
    "next": {"fr": "prochaine partie", "en": "next game", "de": "nächstes Spiel", "es": "próxima partida",
             "it": "prossima partita", "pt": "próximo jogo"},
    "consoles": {"fr": "{n} consoles", "en": "{n} consoles", "de": "{n} Konsolen", "es": "{n} consolas",
                 "it": "{n} console", "pt": "{n} consolas"},
}

BACKGROUND = (10, 12, 17)
TEXT = (240, 243, 248)
MUTED = (150, 158, 175)
FAINT = (92, 100, 116)
DEFAULT_ACCENT = (84, 112, 246)
PLATE = (244, 245, 248, 255)
#: How long the screen waits for a busy display (boot) before giving up.
DISPLAY_WAIT_S = 60.0


def text(key: str, language: str, **values) -> str:
    entry = TEXTS.get(key, {})
    value = entry.get(language) or entry.get("en") or key
    for name, replacement in values.items():
        value = value.replace("{" + name + "}", str(replacement))
    return value


def duration(seconds) -> str:
    minutes = max(0, int(round((seconds or 0) / 60.0)))
    if minutes < 60:
        return "%d min" % minutes
    return "%d h %02d" % (minutes // 60, minutes % 60)


def paths() -> dict:
    root = os.environ.get("RFID_SCREEN_ASSETS")
    if not root:
        return dict(PATHS)
    return {"systemlist": os.path.join(root, "systemlist.xml"), "logos": os.path.join(root, "logos"),
            "arts": os.path.join(root, "arts"), "fonts": os.path.join(root, "fonts")}


# ------------------------------------------------------------------ data
def count_games(roms_dirs=ROMS_DIRS, systemlist: str = None) -> list:
    """Consoles that have games, in the Recalbox order:
    [{"id", "name", "count", "maker", "year"}].

    The files with an extension of the console (as Recalbox's interface
    counts them), in the console folder and its sub-folders.
    """
    found = []
    try:
        from xml.etree import ElementTree
        root = ElementTree.parse(systemlist or paths()["systemlist"]).getroot()
    except Exception:  # noqa: BLE001 - no list: nothing to show
        return found
    for node in root.iter("system"):
        name = node.get("name") or ""
        descriptor = node.find("descriptor")
        if not name or descriptor is None:
            continue
        extensions = tuple(ext.lower().rstrip("!") for ext in (descriptor.get("extensions") or "").split())
        if not extensions:
            continue
        seen = set()
        for base in roms_dirs:
            folder = os.path.join(base, name)
            if not os.path.isdir(folder):
                continue
            for path, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("media", "downloaded_images")]
                for file in files:
                    if file.lower().endswith(extensions) and not file.startswith((".", "_")):
                        seen.add(os.path.relpath(os.path.join(path, file), folder).lower())
        if seen:
            properties = node.find("properties")
            props = properties.attrib if properties is not None else {}
            found.append({"id": name, "name": node.get("fullname") or name, "count": len(seen),
                          "maker": props.get("manufacturer", ""), "year": (props.get("releasedate") or "")[:4]})
    return found


def read_players(home: str) -> dict:
    try:
        with open(os.path.join(home, STATUS_FILENAME), "r", encoding="utf-8") as handle:
            return json.load(handle).get("players") or {}
    except (OSError, ValueError):
        return {}


def player_info(players: dict, language: str):
    """{"name", "uid", "detail", "ratio"} of the active or waiting player
    (or of the guest when the guest has a time limit), or None.

    detail: the time left when the player has a limit, otherwise the time
    played today (or this week).
    """
    current = players.get("current") or {}
    rows = {row.get("uid"): row for row in players.get("players") or []}
    uid = current.get("uid") if current.get("uid") != "guest" else None
    waiting = False
    if not current.get("uid") and players.get("pending"):
        uid, waiting = players.get("pending_uid"), True
    if uid or waiting:
        row = rows.get(uid, {})
        name = current.get("name") or players.get("pending") or row.get("name") or ""
        info = {"name": name, "uid": uid or "", "ratio": None, "avatar": row.get("avatar", 0)}
        quota = (row.get("quota_min") or 0) * 60
        if quota and row.get("remaining_s") is not None:
            left = max(0, row.get("remaining_s") or 0)
            info.update(detail=text("left", language, t=duration(left)), ratio=left / float(quota))
        elif row.get("used_s", 0) >= 60:
            key = "played_week" if row.get("period") == "week" else "played"
            info["detail"] = text(key, language, t=duration(row["used_s"]))
        else:
            info["detail"] = text("next" if waiting else "unlimited", language)
        return info
    guest = players.get("guest") or {}
    if guest.get("quota_min"):
        left = max(0, guest.get("remaining_s") or 0)
        return {"name": text("guest", language), "uid": "", "ratio": left / float(guest["quota_min"] * 60),
                "detail": text("left", language, t=duration(left))}
    return None


def accent_from_svg(svg: str):
    """Main colour of a logo: its most used saturated colour (as the page does)."""
    counts = {}
    for match in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", svg or ""):
        value = match[1:]
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        rgb = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        high, low = max(rgb), min(rgb)
        saturation = (high - low) / high if high else 0
        light = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0
        if saturation < 0.35 or light > 0.92 or light < 0.06:
            continue
        counts[rgb] = counts.get(rgb, 0) + 1
    if not counts:
        return None
    best = max(counts.items(), key=lambda item: (item[1], max(item[0]) - min(item[0])))[0]
    return best


# ------------------------------------------------------------------ drawing
def sized_svg(data: bytes, width: int, height: int) -> bytes:
    """The SVG with its size set, so that it is rasterized sharp at that size."""
    textual = data.decode("utf-8", "replace")
    match = re.search(r"<svg\b[^>]*>", textual)
    if not match:
        return data
    tag = match.group(0)
    view = re.search(r'viewBox\s*=\s*"([^"]+)"', tag)
    if not view:
        w = re.search(r'\bwidth\s*=\s*"([\d.]+)', tag)
        h = re.search(r'\bheight\s*=\s*"([\d.]+)', tag)
        if not (w and h):
            return data
        tag = tag[:-1] + ' viewBox="0 0 %s %s">' % (w.group(1), h.group(1))
    tag = re.sub(r'\s(width|height)\s*=\s*"[^"]*"', "", tag)
    tag = tag[:-1] + ' width="%d" height="%d" preserveAspectRatio="xMidYMid meet">' % (width, height)
    return (textual[:match.start()] + tag + textual[match.end():]).encode("utf-8")


class Painter:
    """Builds the frames (no display needed: also used for the preview)."""

    def __init__(self, pygame, width: int, height: int, consoles: list, language: str, region: str = "eu"):
        self.pg = pygame
        self.w, self.h = width, height
        self.u = height / 100.0
        self.consoles = consoles
        self.language = language
        self.region = region
        self.p = paths()
        self.cache = {}
        self.lock = threading.Lock()
        self.fonts = {}
        self.strip = None
        self.strip_centres = []
        self.dark = None
        self.shown = 0
        self._clock = None
        self._hint = None
        self.gap = 0
        self.home = None          # where the player avatars are (avatars/<UID>.jpg)
        self._avatars = {}

    # ---- resources
    def font(self, name: str, size: float):
        key = (name, int(size))
        if key not in self.fonts:
            path = os.path.join(self.p["fonts"], name)
            try:
                self.fonts[key] = self.pg.font.Font(path if os.path.isfile(path) else None, int(size))
            except Exception:  # noqa: BLE001
                self.fonts[key] = self.pg.font.Font(None, int(size))
        return self.fonts[key]

    def svg(self, path: str, width: int, height: int):
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            return None, ""
        try:
            image = self.pg.image.load(io.BytesIO(sized_svg(data, width, height)), "image.svg")
        except Exception:  # noqa: BLE001 - unreadable picture
            return None, ""
        # Cut to the drawing itself (the pictures have transparent margins).
        box = image.get_bounding_rect()
        if box.width and box.height and box.size != image.get_size():
            image = image.subsurface(box).copy()
        return image, data.decode("utf-8", "replace")

    def art_path(self, console_id: str) -> str:
        for name in ("%s-%s-consolegame.svg" % (console_id, self.region), "%s-consolegame.svg" % console_id,
                     "%s-%s-console.svg" % (console_id, self.region), "%s-console.svg" % console_id):
            path = os.path.join(self.p["arts"], name)
            if os.path.isfile(path):
                return path
        return ""

    def plate(self, image, pad_x: int, pad_y: int):
        """A logo on a light rounded plate: every logo stays readable in its own colours."""
        pg = self.pg
        width, height = image.get_width() + 2 * pad_x, image.get_height() + 2 * pad_y
        plate = pg.Surface((width, height), pg.SRCALPHA)
        pg.draw.rect(plate, PLATE, plate.get_rect(), border_radius=min(height // 2, int(self.u * 1.6)))
        plate.blit(image, (pad_x, pad_y))
        return plate

    def glow(self, colour, radius: int):
        """A soft round glow (small, then enlarged smoothly)."""
        small = self.pg.Surface((64, 64), self.pg.SRCALPHA)
        for step in range(32, 0, -1):
            alpha = int(150 * (1 - step / 32.0) ** 2.2)
            self.pg.draw.circle(small, colour + (alpha,), (32, 32), step)
        return self.pg.transform.smoothscale(small, (radius * 2, radius * 2))

    # ---- one console: background, drawing and texts (built once)
    def hero(self, index: int):
        with self.lock:
            if index in self.cache:
                return self.cache[index]
        pg, u, w, h = self.pg, self.u, self.w, self.h
        console = self.consoles[index]
        logo, logo_svg = self.svg(os.path.join(self.p["logos"], console["id"] + ".svg"), int(w * 0.26), int(h * 0.11))
        accent = accent_from_svg(logo_svg) or DEFAULT_ACCENT
        art = None
        art_path = self.art_path(console["id"])
        if art_path:
            art, art_svg = self.svg(art_path, int(w * 0.52), int(h * 0.6))
            accent = accent_from_svg(logo_svg) or accent_from_svg(art_svg) or accent
        frame = pg.Surface((w, h))
        frame.fill(BACKGROUND)
        # Floor light and glow of the console colour.
        floor = pg.Surface((w, h), pg.SRCALPHA)
        for y in range(int(h * 0.55), h, 4):
            alpha = int(36 * (y - h * 0.55) / (h * 0.45))
            pg.draw.rect(floor, accent + (alpha,), (0, y, w, 4))
        frame.blit(floor, (0, 0))
        halo = self.glow(accent, int(h * 0.62))
        frame.blit(halo, (int(w * 0.31) - halo.get_width() // 2, int(h * 0.46) - halo.get_height() // 2))
        second = self.glow(tuple(min(255, c + 40) for c in accent), int(h * 0.28))
        frame.blit(second, (int(w * 0.80) - second.get_width() // 2, int(h * 0.12) - second.get_height() // 2))
        # The console drawing, with its shadow.
        if art is not None:
            box_w, box_h = int(w * 0.52), int(h * 0.56)
            scale = min(box_w / art.get_width(), box_h / art.get_height(), 1.0)
            if scale < 1.0:
                art = pg.transform.smoothscale(art, (int(art.get_width() * scale), int(art.get_height() * scale)))
            cx, bottom = int(w * 0.31), int(h * 0.73)
            shadow = pg.Surface((int(art.get_width() * 0.9), int(u * 5)), pg.SRCALPHA)
            pg.draw.ellipse(shadow, (0, 0, 0, 110), shadow.get_rect())
            frame.blit(shadow, (cx - shadow.get_width() // 2, bottom - shadow.get_height() // 2))
            frame.blit(art, (cx - art.get_width() // 2, bottom - art.get_height()))
        # Logo, name, number of games.
        x = int(w * 0.62)
        y = int(h * 0.25)
        if logo is not None:
            scale = min(w * 0.26 / logo.get_width(), h * 0.1 / logo.get_height(), 1.0)
            if scale < 1.0:
                logo = pg.transform.smoothscale(logo, (int(logo.get_width() * scale), int(logo.get_height() * scale)))
            logo = self.plate(logo, int(u * 3), int(u * 2))
            shade = pg.Surface((logo.get_width(), logo.get_height()), pg.SRCALPHA)
            pg.draw.rect(shade, (0, 0, 0, 90), shade.get_rect(), border_radius=int(u * 1.6))
            frame.blit(shade, (x + int(u * 0.6), y + int(u * 0.9)))
            frame.blit(logo, (x, y))
            y += logo.get_height() + int(u * 3)
        name = self.font("OpenSans-CondLight.ttf", u * 4.6).render(console["name"], True, TEXT)
        frame.blit(name, (x, y))
        y += name.get_height() + int(u * 0.6)
        facts = " · ".join(part for part in (console.get("maker"), console.get("year")) if part)
        if facts:
            line = self.font("OpenSans-CondLight.ttf", u * 3.4).render(facts, True, MUTED)
            frame.blit(line, (x, y))
            y += line.get_height()
        y += int(u * 3)
        number = self.font("Exo2-Bold.ttf", u * 15).render(str(console["count"]), True, TEXT)
        frame.blit(number, (x, y))
        label = self.font("Exo2-SemiBoldCondensed.otf", u * 5).render(
            text("game" if console["count"] == 1 else "games", self.language), True, accent)
        frame.blit(label, (x + number.get_width() + int(u * 2), y + number.get_height() - label.get_height() - int(u * 2.2)))
        pg.draw.rect(frame, accent, (x, y + number.get_height() + int(u * 0.5), int(u * 9), int(u * 0.7)),
                     border_radius=int(u * 0.35))
        try:
            frame = frame.convert()  # same format as the screen: much faster to show
        except Exception:  # noqa: BLE001 - no display (tests)
            pass
        result = {"frame": frame, "accent": accent}
        with self.lock:
            self.cache[index] = result
            # Kept: the console shown, the one before (during a change) and
            # the next ones (memory of a Pi 3).
            count = len(self.consoles)
            for key in list(self.cache):
                if (key - self.shown) % count not in (0, 1, 2, count - 1):
                    del self.cache[key]
        return result

    def cached(self, index: int) -> bool:
        with self.lock:
            return index in self.cache

    # ---- the band with every logo (built once)
    def build_strip(self):
        pg, u, w, h = self.pg, self.u, self.w, self.h
        height = int(u * 4.6)
        logos = []
        for console in self.consoles:
            image, _svg = self.svg(os.path.join(self.p["logos"], console["id"] + ".svg"), int(u * 30), height)
            if image is None:
                image = self.font("Exo2-SemiBoldCondensed.otf", u * 4.2).render(console["name"], True, (40, 44, 52))
            scale = min(height / image.get_height(), u * 20 / image.get_width(), 1.0)
            if scale < 1.0:
                image = pg.transform.smoothscale(image, (int(image.get_width() * scale), int(image.get_height() * scale)))
            box = pg.Surface((int(u * 20), height), pg.SRCALPHA)
            box.blit(image, ((box.get_width() - image.get_width()) // 2, (height - image.get_height()) // 2))
            logos.append(self.plate(box, int(u * 1.6), int(u * 1.2)))
        self.gap = int(u * 2.4)
        total = sum(image.get_width() for image in logos) + self.gap * max(0, len(logos) - 1)
        height = logos[0].get_height() if logos else height
        strip = pg.Surface((max(1, total), height), pg.SRCALPHA)
        centres = []
        x = 0
        self.plates = []
        for image in logos:
            strip.blit(image, (x, 0))
            centres.append((x + image.get_width() / 2.0, image.get_width()))
            self.plates.append((x, image))
            x += image.get_width() + self.gap
        dim = strip.copy()
        dim.fill((255, 255, 255, 70), special_flags=pg.BLEND_RGBA_MULT)
        self.strip, self.strip_dim, self.strip_centres = self._fast(strip), self._fast(dim), centres
        self.band_y, self.band_h = int(h * 0.84), int(h * 0.16)
        band = pg.Surface((w, self.band_h), pg.SRCALPHA)
        band.fill((0, 0, 0, 120))
        band.fill((255, 255, 255, 34), (0, 0, w, max(1, int(u * 0.15))))
        self.band = self._fast(band)
        fade = pg.Surface((int(w * 0.18), self.band_h), pg.SRCALPHA)
        for x in range(fade.get_width()):
            alpha = int(255 * (1 - x / fade.get_width()) ** 1.6)
            fade.fill(BACKGROUND + (alpha,), (x, 0, 1, self.band_h))
        self.fade_left = self._fast(fade)
        self.fade_right = self._fast(pg.transform.flip(fade, True, False))
        self.dark = pg.Surface((w, h))
        self.dark.fill(BACKGROUND)
        try:
            self.dark = self.dark.convert()
        except Exception:  # noqa: BLE001
            pass

    def _fast(self, surface):
        try:
            return surface.convert_alpha()
        except Exception:  # noqa: BLE001 - no display (tests)
            return surface

    # ---- the scene: console in the spotlight and band (redrawn on changes)
    def scene(self, surface, index: int, previous, progress: float) -> None:
        if self.strip is None:
            self.build_strip()
        changing = previous is not None and progress < 1.0
        if changing:
            # The console leaves into the dark, the next one comes out of it.
            first = progress < 0.5
            surface.blit(self.hero(previous if first else index)["frame"], (0, 0))
            depth = ease(progress * 2) if first else 1 - ease((progress - 0.5) * 2)
            self.dark.set_alpha(int(255 * depth))
            surface.blit(self.dark, (0, 0))
        else:
            surface.blit(self.hero(index)["frame"], (0, 0))
        accent = self.hero(index)["accent"]
        w, u = self.w, self.u
        surface.blit(self.band, (0, self.band_y))
        centre_now = self.strip_centres[index][0]
        if changing:
            start = self.strip_centres[previous][0]
            if index < previous and len(self.strip_centres) > 1:  # wrapped around: slide forward anyway
                start = centre_now - (self.strip_centres[1][0] - self.strip_centres[0][0])
            centre_now = start + (centre_now - start) * ease(progress)
        offset = int(w / 2 - centre_now)
        strip_y = self.band_y + (self.band_h - self.strip.get_height()) // 2
        surface.blit(self.strip_dim, (offset, strip_y))
        loop = self.strip.get_width() + self.gap
        if offset + self.strip.get_width() < w:  # seamless loop
            surface.blit(self.strip_dim, (offset + loop, strip_y))
        if offset > 0:
            surface.blit(self.strip_dim, (offset - loop, strip_y))
        centre, width = self.strip_centres[index]
        alpha = ease(max(0.0, progress - 0.7) / 0.3) if changing else 1.0
        if alpha > 0:
            bright = self.strip.subsurface((int(centre - width / 2), 0, int(width), self.strip.get_height()))
            if alpha < 1.0:
                bright = bright.copy()
                bright.set_alpha(int(255 * alpha))
            surface.blit(bright, (int(w / 2 - width / 2), strip_y))
            self.pg.draw.rect(surface, accent, (int(w / 2 - width / 2), strip_y + self.strip.get_height() + int(u * 1.2),
                                                int(width), int(u * 0.6)), border_radius=int(u * 0.3))
        surface.blit(self.fade_left, (0, self.band_y))
        surface.blit(self.fade_right, (w - self.fade_right.get_width(), self.band_y))

    # ---- the top: invitation (pulsing), player, clock (redrawn often, small)
    def top_rect(self):
        return self.pg.Rect(0, 0, self.w, int(self.u * 15))

    def top(self, surface, index: int, players: dict, now: float, background: bool = True,
            hint: bool = True) -> None:
        pg, u, w = self.pg, self.u, self.w
        rect = self.top_rect()
        if background:
            surface.blit(self.hero(index)["frame"], rect.topleft, rect)
        accent = self.hero(index)["accent"]
        margin = int(u * 5)
        minute = time.strftime("%H:%M")
        if self._clock is None or self._clock[0] != minute:
            self._clock = (minute, self._fast(self.font("Exo2-SemiBoldCondensed.otf", u * 7).render(minute, True, TEXT)))
        clock = self._clock[1]
        surface.blit(clock, (w - margin - clock.get_width(), margin - int(u * 1)))
        icon = pg.Rect(margin, margin + int(u * 0.6), int(u * 5.4), int(u * 3.6))
        pg.draw.rect(surface, accent, icon, width=max(2, int(u * 0.45)), border_radius=int(u * 0.7))
        pg.draw.rect(surface, accent, (icon.x + int(u * 0.9), icon.y + int(u * 0.9), int(u * 1.6), int(u * 1.2)),
                     border_radius=int(u * 0.25))
        if hint:
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(now * 2.2))
            image = self.hint_image()
            image.set_alpha(int(255 * pulse))
            surface.blit(image, self.hint_position(image))
        player = player_info(players, self.language)
        if player:
            self.player_chip(surface, player, accent, w - margin - clock.get_width() - int(u * 3), margin)

    def hint_image(self):
        if self._hint is None:
            self._hint = self._fast(self.font("Raleway-SemiBold.ttf", self.u * 3.6).render(
                text("hint", self.language), True, TEXT))
        return self._hint

    def hint_position(self, image):
        u = self.u
        margin = int(u * 5)
        icon_right = margin + int(u * 5.4)
        centre_y = margin + int(u * 0.6) + int(u * 3.6) // 2
        return icon_right + int(u * 1.6), centre_y - image.get_height() // 2

    def compose(self, surface, index: int, previous, progress: float, players: dict, now: float) -> None:
        """The whole frame (preview, first frame)."""
        self.shown = index
        self.scene(surface, index, previous, progress)
        self.top(surface, index, players, now)

    def avatar(self, uid, version, size: int):
        """The player's picture cut in a disc (None: show the initial)."""
        if not uid or not self.home:
            return None
        key = (uid, version, size)
        if key not in self._avatars:
            pg = self.pg
            picture = None
            try:
                from .avatars import path as avatar_path
                image = self._fast(pg.image.load(avatar_path(self.home, uid)))
                side = min(image.get_width(), image.get_height())
                square = image.subsurface(((image.get_width() - side) // 2, (image.get_height() - side) // 2, side, side))
                big = pg.Surface((size * 2, size * 2), pg.SRCALPHA)  # a JPEG has no alpha
                big.blit(pg.transform.smoothscale(square, (size * 2, size * 2)), (0, 0))
                mask = pg.Surface((size * 2, size * 2), pg.SRCALPHA)
                pg.draw.circle(mask, (255, 255, 255, 255), (size, size), size)
                big.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MIN)
                picture = pg.transform.smoothscale(big, (size, size))  # smooth edge
            except Exception:  # noqa: BLE001 - missing or unreadable: the initial
                picture = None
            self._avatars = {k: v for k, v in self._avatars.items() if k[0] != uid}
            self._avatars[key] = picture
        return self._avatars[key]

    def player_chip(self, surface, player, accent, right: int, top: int):
        pg, u = self.pg, self.u
        name = self.font("Exo2-Bold.ttf", u * 3.6).render(player["name"], True, TEXT)
        detail = self.font("OpenSans-CondLight.ttf", u * 2.9).render(player["detail"], True, MUTED)
        size = int(u * 7)
        width = size + int(u * 2) + max(name.get_width(), detail.get_width(), int(u * 16)) + int(u * 3)
        x = right - width
        chip = pg.Surface((width, size + int(u * 1.6)), pg.SRCALPHA)
        pg.draw.rect(chip, (255, 255, 255, 18), chip.get_rect(), border_radius=chip.get_height() // 2)
        surface.blit(chip, (x, top - int(u * 0.8)))
        centre = (x + int(u * 0.8) + size // 2, top + size // 2)
        pg.draw.circle(surface, accent, centre, size // 2)
        picture = self.avatar(player.get("uid"), player.get("avatar"), size - int(u * 0.5))
        if picture is not None:
            surface.blit(picture, (centre[0] - picture.get_width() // 2, centre[1] - picture.get_height() // 2))
        else:
            initial = self.font("Exo2-Bold.ttf", u * 4.2).render((player["name"][:1] or "?").upper(), True, TEXT)
            surface.blit(initial, (centre[0] - initial.get_width() // 2, centre[1] - initial.get_height() // 2))
        tx = x + int(u * 0.8) + size + int(u * 2)
        surface.blit(name, (tx, top - int(u * 0.9)))
        detail_y = top + name.get_height() - int(u * 1.9)
        surface.blit(detail, (tx, detail_y))
        if player.get("ratio") is not None:
            bar_w = max(name.get_width(), detail.get_width(), int(u * 16))
            bar_y = detail_y + detail.get_height() - int(u * 0.1)
            pg.draw.rect(surface, (255, 255, 255, 40), (tx, bar_y, bar_w, int(u * 0.6)), border_radius=int(u * 0.3))
            colour = accent if player["ratio"] > 0.2 else (234, 165, 59)
            pg.draw.rect(surface, colour, (tx, bar_y, max(int(u * 0.6), int(bar_w * player["ratio"])), int(u * 0.6)),
                         border_radius=int(u * 0.3))


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


# ------------------------------------------------------------------ screen
def screen_size(conf: dict):
    """The resolution of Recalbox's interface (``es.videomode``/``global.videomode``)."""
    for key in ("es.videomode", "global.videomode"):
        match = re.match(r"^(\d{3,4})x(\d{3,4})$", conf.get(key, ""))
        if match:
            return int(match.group(1)), int(match.group(2))
    return 0, 0


def region(conf: dict) -> str:
    language = (conf.get("system.language") or "")[:5].lower()
    if language.startswith("ja"):
        return "jp"
    if language in ("en_us",) or language.startswith("pt_br"):
        return "us"
    return "eu"


class GpuScreen:
    """Drawn by the graphics chip: every frame is a few texture copies."""

    def __init__(self, pygame, painter, window, renderer):
        from pygame._sdl2.video import Texture

        self.pg = pygame
        self.painter = painter
        self.window = window
        self.renderer = renderer
        self.Texture = Texture
        self.heroes = {}
        self.static = None
        self.top_key = None
        self.top_texture = None
        self.hint_texture = None

    def texture(self, surface):
        return self.Texture.from_surface(self.renderer, surface)

    def hero(self, index: int):
        if index not in self.heroes:
            self.heroes[index] = self.texture(self.painter.hero(index)["frame"])
            for key in list(self.heroes):
                if key != index and len(self.heroes) > 3:
                    if key not in (self.painter.shown, (self.painter.shown - 1) % len(self.painter.consoles)):
                        del self.heroes[key]
        return self.heroes[index]

    def build_static(self):
        painter = self.painter
        if painter.strip is None:
            painter.build_strip()
        self.static = {
            "band": self.texture(painter.band),
            "left": self.texture(painter.fade_left),
            "right": self.texture(painter.fade_right),
        }
        for name in ("band", "left", "right"):
            self.static[name].blend_mode = 1  # SDL_BLENDMODE_BLEND
        self.plates = []
        for x, image in painter.plates:
            texture = self.texture(image)
            texture.blend_mode = 1
            self.plates.append((x, image.get_width(), texture))

    def draw(self, index: int, previous, progress: float, players: dict, now: float) -> None:
        pg, painter, renderer = self.pg, self.painter, self.renderer
        w, h, u = painter.w, painter.h, painter.u
        if self.static is None:
            self.build_static()
        changing = previous is not None and progress < 1.0
        full = pg.Rect(0, 0, w, h)
        renderer.draw_color = BACKGROUND + (255,)
        renderer.clear()
        if changing:
            first = progress < 0.5
            self.hero(previous if first else index).draw(dstrect=full)
            depth = ease(progress * 2) if first else 1 - ease((progress - 0.5) * 2)
            renderer.draw_blend_mode = 1
            renderer.draw_color = BACKGROUND + (int(255 * depth),)
            renderer.fill_rect(full)
        else:
            self.hero(index).draw(dstrect=full)
        accent = painter.hero(index)["accent"]
        static = self.static
        band_y, band_h = painter.band_y, painter.band_h
        static["band"].draw(dstrect=(0, band_y, w, band_h))
        centre_now = painter.strip_centres[index][0]
        if changing:
            start = painter.strip_centres[previous][0]
            if index < previous and len(painter.strip_centres) > 1:
                start = centre_now - (painter.strip_centres[1][0] - painter.strip_centres[0][0])
            centre_now = start + (centre_now - start) * ease(progress)
        strip_w, strip_h = painter.strip.get_width(), painter.strip.get_height()
        strip_y = band_y + (band_h - strip_h) // 2
        offset = w / 2.0 - centre_now
        loop = strip_w + painter.gap
        centre, width = painter.strip_centres[index]
        alpha = ease(max(0.0, progress - 0.7) / 0.3) if changing else 1.0
        for shift in (-loop, 0, loop):
            for number, (x, plate_w, texture) in enumerate(self.plates):
                left = offset + shift + x
                if left + plate_w < 0 or left > w:
                    continue
                texture.alpha = 70
                texture.draw(dstrect=(int(left), strip_y, plate_w, strip_h))
        if alpha > 0:
            texture = self.plates[index][2]
            texture.alpha = int(255 * alpha)
            texture.draw(dstrect=(int(w / 2 - width / 2), strip_y, int(width), strip_h))
            renderer.draw_color = accent + (int(255 * alpha),)
            renderer.fill_rect((int(w / 2 - width / 2), strip_y + strip_h + int(u * 1.2), int(width), int(u * 0.6)))
        static["left"].draw(dstrect=(0, band_y, painter.fade_left.get_width(), band_h))
        static["right"].draw(dstrect=(w - painter.fade_right.get_width(), band_y, painter.fade_right.get_width(), band_h))
        # Top: drawn on a transparent surface when it changes (minute, player, console).
        key = (index, time.strftime("%H:%M"), json.dumps(players, sort_keys=True))
        if key != self.top_key:
            self.top_key = key
            layer = pg.Surface(painter.top_rect().size, pg.SRCALPHA)
            painter.top(layer, index, players, now, background=False, hint=False)
            self.top_texture = self.texture(layer)
            self.top_texture.blend_mode = 1
        self.top_texture.draw(dstrect=painter.top_rect())
        if self.hint_texture is None:
            self.hint_texture = self.texture(painter.hint_image())
            self.hint_texture.blend_mode = 1
        pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(now * 2.2))
        self.hint_texture.alpha = int(255 * pulse)
        x, y = painter.hint_position(painter.hint_image())
        self.hint_texture.draw(dstrect=(x, y, self.hint_texture.width, self.hint_texture.height))
        renderer.present()


class Screen:
    def __init__(self, home: str):
        self.home = home
        self.language = recalbox_language()
        self.running = True

    def run(self) -> int:
        os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        import pygame

        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))
        conf = read_conf()
        # At boot the display can stay busy for a while after Recalbox's
        # interface was stopped: wait for it instead of failing.
        deadline = time.monotonic() + DISPLAY_WAIT_S
        while True:
            try:
                pygame.display.init()
                break
            except pygame.error as exc:
                if not self.running or time.monotonic() >= deadline:
                    raise
                print("display busy (%s): retrying" % exc, flush=True)
                pygame.display.quit()
                time.sleep(2.0)
        pygame.font.init()
        if not os.environ.get("RFID_SCREEN_SOFTWARE"):
            try:
                return self.run_gpu(pygame, conf)
            except Exception as exc:  # noqa: BLE001 - drawn by the processor instead
                print("graphics chip not available (%s): software drawing" % exc, flush=True)
        try:
            surface = pygame.display.set_mode(screen_size(conf), pygame.FULLSCREEN)
        except pygame.error:
            surface = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
        width, height = surface.get_size()
        surface.fill(BACKGROUND)
        pygame.display.flip()
        consoles = count_games()
        if not consoles:
            consoles = [{"id": "", "name": "Recalbox", "count": 0, "maker": "", "year": ""}]
        painter = Painter(pygame, width, height, consoles, self.language, region(conf))
        painter.home = self.home
        index, previous, changed = 0, None, time.monotonic()
        painter.hero(0)
        worker = {"thread": None}

        def prepare(target):
            try:
                painter.hero(target)
            except Exception:  # noqa: BLE001 - drawn when shown instead
                pass

        debug = bool(os.environ.get("RFID_SCREEN_DEBUG"))
        frames, slowest, counted = 0, 0.0, time.monotonic()
        players, players_at = {}, 0.0
        print("screen %dx%d, %d consoles" % (width, height, len(consoles)), flush=True)
        painter.compose(surface, index, None, 1.0, players, time.time())
        pygame.display.flip()
        while self.running:
            started = time.monotonic()
            for _event in pygame.event.get():
                pass
            now = time.monotonic()
            if now - players_at >= 1.0:
                players, players_at = read_players(self.home), now
            following = (index + 1) % len(consoles)
            if now - changed >= HOLD_S and len(consoles) > 1 and painter.cached(following):
                previous, index, changed = index, following, now
                painter.shown = index
            progress = (now - changed) / FADE_S if previous is not None else 1.0
            if progress < 1.0:
                painter.scene(surface, index, previous, progress)
                painter.top(surface, index, players, time.time())
                pygame.display.flip()
            else:
                if previous is not None:  # end of a change: last full frame
                    previous = None
                    painter.scene(surface, index, None, 1.0)
                    painter.top(surface, index, players, time.time())
                    pygame.display.flip()
                else:
                    painter.top(surface, index, players, time.time())
                    pygame.display.update(painter.top_rect())
                # The next console is prepared during the pause, never during a change.
                nxt = (index + 1) % len(consoles)
                thread = worker["thread"]
                if not painter.cached(nxt) and (thread is None or not thread.is_alive()):
                    worker["thread"] = threading.Thread(target=prepare, args=(nxt,), daemon=True)
                    worker["thread"].start()
            if debug:
                frames += 1
                slowest = max(slowest, time.monotonic() - started)
                if time.monotonic() - counted >= 5:
                    print("%.1f fps, slowest %.0f ms" % (frames / (time.monotonic() - counted), slowest * 1000), flush=True)
                    frames, slowest, counted = 0, 0.0, time.monotonic()
            time.sleep(0.004 if progress < 1.0 else 0.08)
        pygame.display.quit()
        return 0


def _consoles():
    consoles = count_games()
    return consoles or [{"id": "", "name": "Recalbox", "count": 0, "maker": "", "year": ""}]


def _run_gpu(self, pygame, conf) -> int:
    from pygame._sdl2.video import Renderer, Window

    size = screen_size(conf)
    if not size[0]:
        info = pygame.display.Info()
        size = (info.current_w or 1280, info.current_h or 720)
    window = Window("Recalbox RFID", size=size, fullscreen=True)
    renderer = Renderer(window, accelerated=1, vsync=True)
    pygame.mouse.set_visible(False)
    width, height = size
    renderer.draw_color = BACKGROUND + (255,)
    renderer.clear()
    renderer.present()
    consoles = _consoles()
    painter = Painter(pygame, width, height, consoles, self.language, region(conf))
    painter.home = self.home
    gpu = GpuScreen(pygame, painter, window, renderer)
    index, previous, changed = 0, None, time.monotonic()
    painter.hero(0)
    worker = {"thread": None}

    def prepare(target):
        try:
            painter.hero(target)
        except Exception:  # noqa: BLE001 - drawn when shown instead
            pass

    debug = bool(os.environ.get("RFID_SCREEN_DEBUG"))
    frames, slowest, counted = 0, 0.0, time.monotonic()
    players, players_at = {}, 0.0
    print("screen %dx%d, %d consoles, graphics chip" % (width, height, len(consoles)), flush=True)
    while self.running:
        started = time.monotonic()
        for _event in pygame.event.get():
            pass
        now = time.monotonic()
        if now - players_at >= 1.0:
            players, players_at = read_players(self.home), now
        following = (index + 1) % len(consoles)
        if now - changed >= HOLD_S and len(consoles) > 1 and painter.cached(following):
            previous, index, changed = index, following, now
            painter.shown = index
            gpu.hero(index)  # sent to the chip before the change starts
        progress = (now - changed) / FADE_S if previous is not None else 1.0
        if progress >= 1.0:
            previous = None
            nxt = (index + 1) % len(consoles)
            thread = worker["thread"]
            if not painter.cached(nxt) and (thread is None or not thread.is_alive()):
                worker["thread"] = threading.Thread(target=prepare, args=(nxt,), daemon=True)
                worker["thread"].start()
        gpu.draw(index, previous, progress, players, time.time())  # waits for the screen (vsync)
        if debug:
            frames += 1
            slowest = max(slowest, time.monotonic() - started)
            if time.monotonic() - counted >= 5:
                print("%.1f fps, slowest %.0f ms" % (frames / (time.monotonic() - counted), slowest * 1000), flush=True)
                frames, slowest, counted = 0, 0.0, time.monotonic()
        if progress >= 1.0:
            time.sleep(0.02)  # the pulse only: no need for every screen refresh
    # Textures first, then the renderer and the window: freed in another
    # order, SDL crashes while quitting.
    gpu.heroes.clear()
    gpu.plates = []
    gpu.static = gpu.top_texture = gpu.hint_texture = None
    del gpu
    del renderer
    window.destroy()
    del window
    sys.stdout.flush()
    os._exit(0)


Screen.run_gpu = _run_gpu


def run(home: str) -> int:
    return Screen(home).run()


def preview(output: str, width: int = 1280, height: int = 720, at=(0.0,), players=None, counts=None,
            home: str = None) -> list:
    """Draws frames into PNG files (no screen): output-<n>.png."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    import pygame

    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))
    consoles = counts if counts is not None else count_games()
    painter = Painter(pygame, width, height, consoles, "fr")
    painter.home = home
    written = []
    for number, (index, previous, progress) in enumerate(at):
        surface = pygame.Surface((width, height))
        painter.compose(surface, index, previous, progress, players or {}, 1.0)
        path = "%s-%d.png" % (output, number)
        pygame.image.save(surface, path)
        written.append(path)
    return written
