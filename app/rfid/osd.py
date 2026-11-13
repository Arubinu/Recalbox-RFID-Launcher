"""On-screen messages during a game (RetroArch network commands).

The Recalbox menu cannot show a message sent by another program: the
frontend listens to no display command (checked on Recalbox 10.1). During a
game run by RetroArch (most consoles), Recalbox enables RetroArch's network
commands (``network_cmd_enable = true``, UDP port 55355): the ``SHOW_MSG``
command shows a message at the bottom of the game screen.

Stand-alone emulators (Dolphin, PPSSPP...) ignore it: the message is simply
lost, the beeps and the light still work.
"""

from __future__ import annotations

import socket

RETROARCH_PORT = 55355

#: Recalbox settings (the interface language is read there).
RECALBOX_CONF = "/recalbox/share/system/recalbox.conf"

#: Messages shown on the TV, in the Recalbox interface language.
MESSAGES = {
    "warn300": {
        "fr": "Plus que 5 minutes de jeu", "en": "5 minutes of play left",
        "de": "Noch 5 Minuten Spielzeit", "es": "Quedan 5 minutos de juego",
        "it": "Restano 5 minuti di gioco", "pt": "Faltam 5 minutos de jogo"},
    "warn60": {
        "fr": "Plus qu'une minute de jeu", "en": "1 minute of play left",
        "de": "Noch 1 Minute Spielzeit", "es": "Queda 1 minuto de juego",
        "it": "Resta 1 minuto di gioco", "pt": "Falta 1 minuto de jogo"},
    "expired": {
        "fr": "Temps de jeu terminé", "en": "Play time is over",
        "de": "Spielzeit ist vorbei", "es": "Se acabó el tiempo de juego",
        "it": "Tempo di gioco finito", "pt": "O tempo de jogo acabou"},
    "bonus": {
        "fr": "+{n} min de jeu", "en": "+{n} min of play",
        "de": "+{n} Min. Spielzeit", "es": "+{n} min de juego",
        "it": "+{n} min di gioco", "pt": "+{n} min de jogo"},
    "bonus_left": {
        "fr": "+{n} min de jeu (encore {k} fois)", "en": "+{n} min of play ({k} more uses)",
        "de": "+{n} Min. Spielzeit (noch {k}x)", "es": "+{n} min de juego (quedan {k} usos)",
        "it": "+{n} min di gioco (ancora {k} volte)", "pt": "+{n} min de jogo (mais {k} usos)"},
    "exhausted": {
        "fr": "Carte bonus déjà utilisée", "en": "Bonus card already used",
        "de": "Bonuskarte schon benutzt", "es": "Tarjeta de bonus ya usada",
        "it": "Carta bonus già usata", "pt": "Cartão bónus já usado"},
    "pairing": {
        "fr": "Un appareil demande l'accès : maintenez le bouton 3 s",
        "en": "A device asks for access: hold the button for 3 s",
        "de": "Ein Gerät bittet um Zugriff: Taste 3 s gedrückt halten",
        "es": "Un dispositivo pide acceso: mantén el botón 3 s",
        "it": "Un dispositivo chiede l'accesso: tieni premuto il pulsante 3 s",
        "pt": "Um dispositivo pede acesso: mantenha o botão 3 s"},
    "paired": {
        "fr": "Appareil autorisé", "en": "Device authorized", "de": "Gerät autorisiert",
        "es": "Dispositivo autorizado", "it": "Dispositivo autorizzato", "pt": "Dispositivo autorizado"},
    "armed": {
        "fr": "Posez le badge à associer", "en": "Place the badge to pair",
        "de": "Badge zum Verknüpfen auflegen", "es": "Coloca la tarjeta que quieres asociar",
        "it": "Appoggia il badge da associare", "pt": "Coloque a tag a associar"},
    "bound": {
        "fr": "Badge associé", "en": "Badge paired", "de": "Badge verknüpft",
        "es": "Tarjeta asociada", "it": "Badge associato", "pt": "Tag associada"},
    "unknown": {
        "fr": "Badge inconnu", "en": "Unknown badge", "de": "Unbekannter Badge",
        "es": "Tarjeta desconocida", "it": "Badge sconosciuto", "pt": "Tag desconhecida"},
}


def recalbox_language(path: str = RECALBOX_CONF) -> str:
    """Two-letter code of the Recalbox interface language ("fr" by default)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("system.language="):
                    code = line.split("=", 1)[1].strip()[:2].lower()
                    return code if code in ("fr", "en", "de", "es", "it", "pt") else "en"
    except OSError:
        pass
    return "fr"


def message(key: str, language: str = "fr", **values) -> str:
    """Translated message (English when the language is unknown)."""
    texts = MESSAGES.get(key) or {}
    text = texts.get(language) or texts.get("en") or key
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


class ScreenMessages:
    """Sends short messages to RetroArch (never blocking, never failing)."""

    def __init__(self, enabled: bool = True, port: int = RETROARCH_PORT, host: str = "127.0.0.1",
                 log=None, sender=None):
        self.enabled = bool(enabled)
        self.port = int(port)
        self.host = host
        self.log = log
        self._sender = sender or self._send
        self.sent = []
        self.language = recalbox_language()

    def say(self, key: str, **values) -> bool:
        """Shows one of the MESSAGES, in the Recalbox language."""
        return self.show(message(key, self.language, **values))

    def _send(self, payload: bytes) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(0.5)
            sock.sendto(payload, (self.host, self.port))
        finally:
            sock.close()

    def show(self, text: str) -> bool:
        """Shows ``text`` on the game screen (True if the datagram left)."""
        if not self.enabled or not text:
            return False
        clean = " ".join(str(text).split())[:120]
        try:
            self._sender(("SHOW_MSG " + clean).encode("utf-8"))
        except OSError as exc:
            if self.log:
                self.log.debug("Message a l'ecran non envoye : %s" % exc)
            return False
        self.sent.append(clean)
        if len(self.sent) > 20:
            del self.sent[:-20]
        return True
