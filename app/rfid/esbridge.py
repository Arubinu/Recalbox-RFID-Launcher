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
import signal
import socket
import time
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


#: Cles que le frontend Recalbox peut employer selon la version.
CLES_SYSTEME = ("SystemId", "System", "SystemName")
CLES_CHEMIN = ("GamePath", "Path", "File", "RomPath")


def state_snapshot(state, limite: int = 120) -> dict:
    """Resume lisible de ``es_state.inf`` (pour status.json et les journaux)."""
    if not state:
        return {}
    resume = {}
    for cle, valeur in state.items():
        texte = str(valeur or "")
        if len(texte) > limite:
            texte = texte[: limite - 1] + "…"
        resume[cle] = texte
    return resume


def describe_state(state) -> str:
    """Explique pourquoi aucun jeu n'a ete trouve (message de journal)."""
    if not state:
        return "/tmp/es_state.inf absent ou vide"
    cles = ("Action", "State", "Type", "IsFolder", "SystemId", "System", "Game", "GamePath")
    presentes = [cle for cle in cles if cle in state]
    if not presentes:
        return "etat illisible (aucune cle connue) : %s" % sorted(state.keys())[:8]
    return ", ".join("%s=%r" % (cle, state.get(cle)) for cle in presentes)


#: Dossiers ou Recalbox range les jeux (partie inscriptible, puis base en lecture seule).
ROMS_DIRS = ("/recalbox/share/roms", "/recalbox/share_init/roms")


def resolve_rom_path(system: str, game: str) -> str:
    """Chemin complet d'un jeu, pour les entrees qui n'en ont pas.

    Le frontend identifie un jeu par son chemin complet : on le reconstruit ici
    (sans verification possible sur un PC, on renvoie alors le premier candidat).
    """
    if not system or not game:
        return ""
    if game.startswith("/"):
        return game
    # Chemins POSIX : le service tourne sous Linux, meme quand les tests
    # s'executent sous Windows.
    candidats = ["%s/%s/%s" % (base, system, game) for base in ROMS_DIRS]
    for candidat in candidats:
        if os.path.isfile(candidat):
            return candidat
    return candidats[0]


def current_target(state, allow_running: bool = False) -> "Target | None":
    """Retourne le jeu selectionne, ou None si aucun jeu n'est selectionne.

    ``allow_running`` sert a l'association : le frontend peut laisser
    ``State=playing`` (ou afficher une fiche de jeu) alors qu'aucune partie n'est
    en cours ; on accepte alors le jeu affiche. Pour le lancement par badge, on
    garde le filtre (pas d'interruption de partie).
    """
    if not state:
        return None
    system = ""
    for cle in CLES_SYSTEME:
        system = (state.get(cle) or "").strip()
        if system:
            break
    absolute = ""
    for cle in CLES_CHEMIN:
        absolute = (state.get(cle) or "").strip()
        if absolute:
            break
    if not system or not absolute:
        return None
    if state.get("IsFolder") == "1":
        return None
    if str(state.get("Type") or "").strip().lower() in ("folder", "system", "empty", "none"):
        return None
    if not allow_running:
        if game_is_running(state):
            return None
        if state.get("State") == "demo":
            return None
    game = relative_game_key(system, absolute)
    if not game:
        return None
    return Target(system=system, game=game, name=(state.get("Game") or "").strip(), path=absolute)


#: Processus d'emulateurs que l'on peut arreter (jamais EmulationStation).
EMULATEURS = (
    "retroarch",
    "emulatorlauncher",
    "dolphin",
    "ppsspp",
    "mupen64plus",
    "scummvm",
    "dosbox",
    "amiberry",
    "flycast",
    "pcsx",
    "duckstation",
    "yabasanshiro",
    "mednafen",
    "hatari",
    "vice",
    "fs-uae",
)


#: Dossier des processus (remplacable dans les tests).
PROC_DIR = "/proc"

#: Signaux utilises pour arreter un emulateur (absents sous Windows).
SIG_TERM = getattr(signal, "SIGTERM", 15)
SIG_KILL = getattr(signal, "SIGKILL", 9)

#: Programme a ne jamais arreter : le frontend lui-meme.
JAMAIS_ARRETER = ("emulationstation", "emulationstation.sh")


def _cmdline(pid: str, proc_dir: str = PROC_DIR) -> str:
    try:
        with open(os.path.join(proc_dir, str(pid), "cmdline"), "rb") as handle:
            brut = handle.read()
    except OSError:
        return ""
    return brut.decode("utf-8", "replace").replace("\x00", " ").strip()


def _programmes(ligne: str) -> list:
    """Noms de programme d'une ligne de commande (argv[0] et script eventuel).

    On ne compare que des noms de fichiers : chercher « vice » n'importe ou dans
    la ligne arreterait des processus systeme sans rapport (paquets, services).
    """
    morceaux = ligne.split()
    return [os.path.basename(morceau).lower() for morceau in morceaux[:3]]


def _est_emulateur(noms, ligne: str, rom_path: str) -> bool:
    if rom_path and rom_path in ligne:
        return True
    for nom in noms:
        if nom in JAMAIS_ARRETER:
            return False
        if nom in EMULATEURS:
            return True
        base = nom.split(".")[0]
        if base in EMULATEURS:
            return True
    return False


def emulator_pids(rom_path: str = "", proc_dir: str = PROC_DIR):
    """PID des processus d'emulation en cours (jamais ES, jamais nous)."""
    pids = []
    propre = os.getpid()
    try:
        entrees = os.listdir(proc_dir)
    except OSError:
        return pids
    for entree in entrees:
        if not entree.isdigit():
            continue
        pid = int(entree)
        if pid == propre:
            continue
        ligne = _cmdline(entree, proc_dir)
        if not ligne:
            continue
        if _est_emulateur(_programmes(ligne), ligne, rom_path):
            pids.append(pid)
    return pids


def _kill(pid: int, sig: int) -> None:
    """Point d'envoi de signal (remplace dans les tests)."""
    os.kill(pid, sig)


class EsLauncher:
    """Envoi de la commande de lancement au frontend."""

    def __init__(self, host: str = ES_UDP_HOST, port: int = ES_UDP_PORT, log=None):
        self.host = host
        self.port = int(port)
        self.log = log

    @staticmethod
    def build_payload(system: str, game: str) -> bytes:
        """Construit la trame ``START|systeme|reference`` (octets du systeme de fichiers).

        ``reference`` est le chemin **complet** du jeu tel que le frontend le
        connait (il le publie dans son fichier d'etat). Depuis Recalbox 10, le
        nom de fichier seul ne suffit plus.
        """
        system = str(system)
        game = str(game)
        if not system or not game:
            raise ValueError("systeme ou jeu vide")
        if "|" in system or "|" in game:
            raise ValueError(
                "le caractere '|' n'est pas accepte dans le nom d'un jeu (trame UDP)"
            )
        return b"START|" + os.fsencode(system) + b"|" + os.fsencode(game)

    def game_running(self, rom_path: str = "") -> bool:
        """Vrai si un emulateur tourne (independant de l'etat du frontend)."""
        return bool(emulator_pids(rom_path))

    def stop_game(self, rom_path: str = "", timeout_s: float = 8.0, proc_dir: str = PROC_DIR) -> bool:
        """Arrete le jeu en cours (SIGTERM, puis SIGKILL si necessaire).

        Le frontend ne propose aucune commande reseau pour quitter un jeu : on
        termine le processus de l'emulateur, et EmulationStation revient au menu
        comme apres une sortie normale.
        """
        cibles = emulator_pids(rom_path, proc_dir)
        if not cibles:
            return False
        for pid in cibles:
            try:
                _kill(pid, SIG_TERM)
            except OSError:
                continue
        echeance = time.monotonic() + timeout_s
        while time.monotonic() < echeance:
            if not emulator_pids(rom_path, proc_dir):
                if self.log:
                    self.log.info("Emulateur arrete (%d processus)" % len(cibles))
                return True
            time.sleep(0.2)
        for pid in emulator_pids(rom_path, proc_dir):
            try:
                _kill(pid, SIG_KILL)
            except OSError:
                continue
        if self.log:
            self.log.warning("Emulateur force a s'arreter (SIGKILL)")
        return True

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
