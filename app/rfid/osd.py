"""On-screen messages during a game (RetroArch network commands).

The Recalbox menu cannot show a message sent by another program: the
frontend listens to no display command (checked on Recalbox 10.1). During a
game run by RetroArch (most consoles), Recalbox enables RetroArch's network
commands (``network_cmd_enable = true``, UDP port 55355): the ``SHOW_MSG``
command shows a message at the bottom of the game screen.

Stand-alone emulators (Dolphin, PPSSPP...) ignore it: the message is simply
lost, the beeps and the light still work.

Every message is also written to ``SCREEN_MESSAGE_FILE`` (in RAM): the
reader screen, shown between the games, displays it as a toast.
"""

from __future__ import annotations

import json
import os
import socket
import time

RETROARCH_PORT = 55355

#: Last message, read by the reader screen (in /tmp: no SD card writes).
SCREEN_MESSAGE_FILE = "/tmp/rfid-screen-message.json"

#: Recalbox settings (the interface language is read there).
RECALBOX_CONF = "/recalbox/share/system/recalbox.conf"

#: Messages shown on the TV, in the Recalbox interface language.
MESSAGES = {
    "player_hello": {
        "fr": "{name} : {n} min de jeu", "en": "{name}: {n} min of play",
        "de": "{name}: {n} Min. Spielzeit", "es": "{name}: {n} min de juego",
        "it": "{name}: {n} min di gioco", "pt": "{name}: {n} min de jogo"},
    "player_unlimited": {
        "fr": "Bon jeu, {name} !", "en": "Have fun, {name}!",
        "de": "Viel Spaß, {name}!", "es": "¡Buen juego, {name}!",
        "it": "Buon divertimento, {name}!", "pt": "Bom jogo, {name}!"},
    "player_needed": {
        "fr": "Pose ta carte joueur pour jouer", "en": "Place your player card to play",
        "de": "Leg deine Spielerkarte auf, um zu spielen", "es": "Pon tu tarjeta de jugador para jugar",
        "it": "Appoggia la tua carta giocatore per giocare", "pt": "Pousa o teu cartão de jogador para jogar"},
    "player_exhausted": {
        "fr": "{name} : plus de temps de jeu pour le moment", "en": "{name}: no play time left for now",
        "de": "{name}: im Moment keine Spielzeit mehr", "es": "{name}: no queda tiempo de juego por ahora",
        "it": "{name}: niente più tempo di gioco per ora", "pt": "{name}: sem tempo de jogo por agora"},
    "guest_exhausted": {
        "fr": "Plus de temps de jeu sans carte joueur", "en": "No play time left without a player card",
        "de": "Ohne Spielerkarte keine Spielzeit mehr", "es": "No queda tiempo de juego sin tarjeta de jugador",
        "it": "Niente più tempo di gioco senza carta giocatore", "pt": "Sem tempo de jogo sem cartão de jogador"},
    "player_left": {
        "fr": "Carte joueur retirée : fin de la partie", "en": "Player card removed: game over",
        "de": "Spielerkarte entfernt: Spielende", "es": "Tarjeta de jugador retirada: fin de la partida",
        "it": "Carta giocatore tolta: fine della partita", "pt": "Cartão de jogador retirado: fim do jogo"},
    "new_game": {
        "fr": "Nouvelle partie", "en": "New game", "de": "Neues Spiel",
        "es": "Nueva partida", "it": "Nuova partita", "pt": "Novo jogo"},
    "game_resumed": {
        "fr": "Partie reprise là où elle s'était arrêtée", "en": "Game resumed where it stopped",
        "de": "Spiel dort fortgesetzt, wo es aufgehört hat", "es": "Partida reanudada donde se quedó",
        "it": "Partita ripresa da dove si era fermata", "pt": "Jogo retomado onde tinha parado"},
    "paused": {
        "fr": "Pause : le temps de jeu est arrêté", "en": "Paused: the play time is stopped",
        "de": "Pause: Die Spielzeit ist angehalten", "es": "Pausa: el tiempo de juego está detenido",
        "it": "Pausa: il tempo di gioco è fermo", "pt": "Pausa: o tempo de jogo está parado"},
    "resumed": {
        "fr": "C'est reparti !", "en": "Back to the game!", "de": "Weiter geht's!",
        "es": "¡Seguimos!", "it": "Si riparte!", "pt": "Vamos lá!"},
    "saved": {
        "fr": "Partie sauvegardée", "en": "Game saved", "de": "Spiel gespeichert",
        "es": "Partida guardada", "it": "Partita salvata", "pt": "Jogo guardado"},
    "save_failed": {
        "fr": "Sauvegarde impossible pour ce jeu", "en": "This game cannot be saved",
        "de": "Dieses Spiel kann nicht gespeichert werden", "es": "No se puede guardar este juego",
        "it": "Impossibile salvare questo gioco", "pt": "Não é possível guardar este jogo"},
    "sound_off": {
        "fr": "Son coupé", "en": "Sound off", "de": "Ton aus", "es": "Sonido apagado",
        "it": "Audio disattivato", "pt": "Som desligado"},
    "sound_on": {
        "fr": "Son remis", "en": "Sound on", "de": "Ton an", "es": "Sonido activado",
        "it": "Audio attivato", "pt": "Som ligado"},
    "time_left": {
        "fr": "{name} : {t} de jeu restantes", "en": "{name}: {t} of play left",
        "de": "{name}: noch {t} Spielzeit", "es": "{name}: quedan {t} de juego",
        "it": "{name}: restano {t} di gioco", "pt": "{name}: faltam {t} de jogo"},
    "time_unlimited": {
        "fr": "{name} : temps de jeu sans limite", "en": "{name}: no play time limit",
        "de": "{name}: Spielzeit ohne Limit", "es": "{name}: tiempo de juego sin límite",
        "it": "{name}: tempo di gioco senza limiti", "pt": "{name}: tempo de jogo sem limite"},
    "guest": {
        "fr": "Invité", "en": "Guest", "de": "Gast", "es": "Invitado", "it": "Ospite", "pt": "Convidado"},
    "player_switched": {
        "fr": "La partie compte maintenant pour {name}", "en": "The game now counts for {name}",
        "de": "Das Spiel zählt jetzt für {name}", "es": "La partida cuenta ahora para {name}",
        "it": "La partita ora conta per {name}", "pt": "O jogo conta agora para {name}"},
    "player_next": {
        "fr": "{name} joue la prochaine partie", "en": "{name} plays the next game",
        "de": "{name} spielt das nächste Spiel", "es": "{name} juega la próxima partida",
        "it": "{name} gioca la prossima partita", "pt": "{name} joga o próximo jogo"},
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
                 log=None, sender=None, screen_file: str = None, clock=None):
        self.enabled = bool(enabled)
        self.screen_file = screen_file
        self._clock = clock or time.time
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

    def _write_screen(self, text: str) -> None:
        if not self.screen_file:
            return
        temporary = self.screen_file + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"text": text, "at": self._clock()}, handle, ensure_ascii=False)
            os.replace(temporary, self.screen_file)
        except OSError as exc:
            if self.log:
                self.log.debug("Message pour l'ecran du lecteur non ecrit : %s" % exc)

    def show(self, text: str) -> bool:
        """Shows ``text`` on the game screen (True if the datagram left)."""
        if not self.enabled or not text:
            return False
        clean = " ".join(str(text).split())[:120]
        self._write_screen(clean)
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
