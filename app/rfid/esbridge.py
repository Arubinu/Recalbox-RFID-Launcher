"""Dialogue avec le frontend Recalbox (EmulationStation).

Deux mecanismes officiels sont utilises, sans modifier l'OS :

1. **Lecture** de ``/tmp/es_state.inf`` : le frontend y ecrit a chaque evenement
   le systeme et le jeu actuellement selectionnes. C'est ce qui permet au bouton
   poussoir de savoir a quel jeu associer le badge.

2. **Lancement** d'un jeu : depuis Recalbox 9, le frontend ecoute le port UDP
   1337 et attend une trame texte ::

       START|<identifiant systeme>|<chemin du jeu relatif au dossier du systeme>

   paquet = un seul datagramme UDP, sans saut de ligne final. Le frontend
   resout ensuite le jeu exactement comme s'il avait ete lance depuis le menu
   (splash screen, sauvegardes, retroachievements, etc.).
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from .consts import ES_STATE_FILE, ES_UDP_HOST, ES_UDP_PORT


@dataclass
class Target:
    """Jeu selectionne dans l'interface Recalbox."""

    system: str
    game: str
    name: str = ""
    path: str = ""

    def describe(self) -> str:
        return "%s / %s" % (self.system, self.name or self.game)


def read_state(path: str = ES_STATE_FILE):
    """Lit ``es_state.inf`` et retourne un dictionnaire (None si absent)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return None

    state = {}
    for line in lines:
        line = line.strip("\r\n")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


def game_is_running(state) -> bool:
    """True si un jeu est en cours (d'apres le fichier d'etat)."""
    return bool(state) and state.get("State") == "playing"


def relative_game_key(system: str, absolute_path: str) -> str:
    """Convertit un chemin absolu de ROM en cle attendue par la commande UDP.

    Le frontend cherche le jeu par son chemin relatif au dossier du systeme,
    extension comprise, sans tenir compte de la casse. Par exemple
    ``/recalbox/share/roms/snes/Super Mario World.smc`` -> ``Super Mario World.smc``.
    """
    if not absolute_path:
        return ""
    normalized = absolute_path.replace("\\", "/")
    candidates = [
        "/recalbox/share/roms/%s/" % system,
        "/recalbox/share/roms/%s" % system,
    ]
    for prefix in candidates[:-1]:
        if normalized.startswith(prefix):
            return normalized[len(prefix):]

    marker = "/roms/"
    index = normalized.find(marker)
    if index >= 0:
        remainder = normalized[index + len(marker):]
        parts = remainder.split("/")
        if len(parts) > 1:
            return "/".join(parts[1:])
        return parts[0]
    return os.path.basename(normalized)


def current_target(state) -> "Target | None":
    """Retourne le jeu selectionne, ou None si aucun jeu n'est selectionne."""
    if not state:
        return None
    system = (state.get("SystemId") or "").strip()
    absolute = (state.get("GamePath") or "").strip()
    if not system or not absolute:
        return None
    if state.get("IsFolder") == "1":
        return None
    if game_is_running(state):
        return None
    if state.get("State") == "demo":
        return None
    game = relative_game_key(system, absolute)
    if not game:
        return None
    return Target(system=system, game=game, name=(state.get("Game") or "").strip(), path=absolute)


class EsLauncher:
    """Envoi de la commande de lancement au frontend."""

    def __init__(self, host: str = ES_UDP_HOST, port: int = ES_UDP_PORT, log=None):
        self.host = host
        self.port = int(port)
        self.log = log

    @staticmethod
    def build_payload(system: str, game: str) -> bytes:
        """Construit la trame ``START|systeme|jeu`` (octets du systeme de fichiers)."""
        system = str(system)
        game = str(game)
        if not system or not game:
            raise ValueError("systeme ou jeu vide")
        if "|" in system or "|" in game:
            raise ValueError(
                "le caractere '|' n'est pas accepte dans le nom d'un jeu (trame UDP)"
            )
        return b"START|" + os.fsencode(system) + b"|" + os.fsencode(game)

    def start_game(self, system: str, game: str) -> bool:
        """Envoie la commande ; True si le datagramme est parti."""
        try:
            payload = self.build_payload(system, game)
        except ValueError as exc:
            if self.log:
                self.log.error("Lancement impossible : %s" % exc)
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.settimeout(1.0)
                sock.sendto(payload, (self.host, self.port))
            finally:
                sock.close()
        except OSError as exc:
            if self.log:
                self.log.error(
                    "Commande de lancement non envoyee (%s:%s) : %s" % (self.host, self.port, exc)
                )
            return False
        if self.log:
            self.log.info("Commande envoyee : START|%s|%s" % (system, game))
        return True


def supports_start_command(binary: str = "/usr/bin/emulationstation", chunk_size: int = 1 << 20) -> bool:
    """Detecte le support de la commande UDP dans le binaire du frontend.

    Recalbox 9 a introduit le fil "UDPCommand" ; le message d'erreur qu'il ecrit
    dans le journal est present dans le binaire. Cette verification permet a
    l'installeur de prevenir l'utilisateur sur une version trop ancienne.
    """
    needle = b"Wrong network command"
    try:
        with open(binary, "rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    return False
                if needle in chunk:
                    return True
    except OSError:
        return False
