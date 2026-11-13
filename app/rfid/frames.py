"""Card frames: pictures made by the user, with a transparent window.

A frame is a PNG (or SVG, WEBP, JPEG) the size of a card, with a transparent
zone where the game picture shows. It is stored in ``frames/`` next to a
small JSON file: name, consoles it is meant for, orientation and the place of
the window (in millimetres, found by the page from the transparency).

Files are only written by the agent, under names it chooses (``<id>.png``,
``<id>.json``): nothing sent by the page becomes a path.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time

FRAMES_DIR = "frames"
MAX_FRAMES = 80
MAX_FRAME_BYTES = 12 * 1024 * 1024
TYPES = {
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
}
_ID = re.compile(r"^[a-z0-9]{6,32}$")
_SYSTEM = re.compile(r"^[a-z0-9_-]{1,32}$")


class FrameError(Exception):
    pass


def sniff_type(data: bytes) -> str:
    """Content type from the first bytes (the page's claim is not trusted)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:2048].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in head:
        return "image/svg+xml"
    return ""


def _number(value, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise FrameError("valeur invalide")
    if number != number or number < low or number > high:
        raise FrameError("valeur hors limites")
    return round(number, 3)


def clean_meta(meta: dict) -> dict:
    """Name, consoles, orientation and window, checked."""
    if not isinstance(meta, dict):
        raise FrameError("description du cadre manquante")
    name = str(meta.get("name") or "").strip()[:60]
    if not name:
        raise FrameError("donnez un nom au cadre")
    systems = []
    for system in meta.get("systems") or []:
        system = str(system).strip().lower()
        if _SYSTEM.match(system) and system not in systems:
            systems.append(system)
    orientation = "portrait" if meta.get("orientation") == "portrait" else "landscape"
    width, height = (54.0, 85.6) if orientation == "portrait" else (85.6, 54.0)
    window = meta.get("window")
    if not isinstance(window, dict):
        raise FrameError("zone de l'image manquante")
    clean_window = {
        "x": _number(window.get("x"), 0, width),
        "y": _number(window.get("y"), 0, height),
        "w": _number(window.get("w"), 1, width),
        "h": _number(window.get("h"), 1, height),
    }
    return {"name": name, "systems": systems[:40], "orientation": orientation, "window": clean_window}


class FrameStore:
    def __init__(self, home: str, now=None):
        self.folder = os.path.join(home, FRAMES_DIR)
        self._now = now or time.time
        self._lock = threading.Lock()

    def _meta_path(self, frame_id: str) -> str:
        if not _ID.match(frame_id or ""):
            raise FrameError("cadre inconnu")
        return os.path.join(self.folder, frame_id + ".json")

    def _read_meta(self, frame_id: str):
        try:
            with open(self._meta_path(frame_id), "r", encoding="utf-8") as handle:
                meta = json.load(handle)
        except (OSError, ValueError, FrameError):
            return None
        return meta if isinstance(meta, dict) else None

    def _write_meta(self, frame_id: str, meta: dict) -> None:
        path = self._meta_path(frame_id)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)

    def list(self) -> list:
        if not os.path.isdir(self.folder):
            return []
        frames = []
        for name in sorted(os.listdir(self.folder)):
            if not name.endswith(".json") or not _ID.match(name[:-5]):
                continue
            meta = self._read_meta(name[:-5])
            if meta and os.path.isfile(os.path.join(self.folder, name[:-5] + meta.get("ext", ""))):
                frames.append(dict(meta, id=name[:-5]))
        frames.sort(key=lambda item: (item.get("name") or "").lower())
        return frames

    def get(self, frame_id: str):
        """(content type, bytes) of a frame picture, or None."""
        meta = self._read_meta(frame_id)
        if not meta:
            return None
        try:
            with open(os.path.join(self.folder, frame_id + meta.get("ext", "")), "rb") as handle:
                return meta.get("type") or "image/png", handle.read()
        except OSError:
            return None

    def save(self, meta: dict, data: bytes) -> dict:
        clean = clean_meta(meta)
        if not data:
            raise FrameError("image manquante")
        if len(data) > MAX_FRAME_BYTES:
            raise FrameError("image trop volumineuse (12 Mo au plus)")
        kind = sniff_type(data)
        if kind not in TYPES:
            raise FrameError("format non pris en charge (PNG, SVG, WEBP ou JPEG)")
        with self._lock:
            if len(self.list()) >= MAX_FRAMES:
                raise FrameError("trop de cadres (%d au plus)" % MAX_FRAMES)
            os.makedirs(self.folder, exist_ok=True)
            frame_id = secrets.token_hex(6)
            ext = TYPES[kind]
            path = os.path.join(self.folder, frame_id + ext)
            with open(path + ".tmp", "wb") as handle:
                handle.write(data)
            os.replace(path + ".tmp", path)
            stored = dict(clean, ext=ext, type=kind, size=len(data), created=int(self._now()))
            self._write_meta(frame_id, stored)
        return dict(stored, id=frame_id)

    def update(self, frame_id: str, changes: dict) -> dict:
        """New name, consoles or window (the picture stays)."""
        with self._lock:
            meta = self._read_meta(frame_id)
            if not meta:
                raise FrameError("cadre inconnu")
            merged = dict(meta)
            for key in ("name", "systems", "window"):
                if key in changes:
                    merged[key] = changes[key]
            clean = clean_meta(merged)
            meta.update(clean)
            self._write_meta(frame_id, meta)
        return dict(meta, id=frame_id)

    def delete(self, frame_id: str) -> bool:
        with self._lock:
            meta = self._read_meta(frame_id)
            if not meta:
                return False
            for path in (os.path.join(self.folder, frame_id + meta.get("ext", "")), self._meta_path(frame_id)):
                try:
                    os.remove(path)
                except OSError:
                    pass
        return True
