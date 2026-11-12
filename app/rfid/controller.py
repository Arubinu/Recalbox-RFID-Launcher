"""Logique metier : un badge lance un jeu, le bouton associe ou efface.

Cette classe ne touche ni au materiel ni au systeme de fichiers : elle recoit un
magasin de badges, un lanceur, un retour utilisateur et une source d'etat. C'est
ce qui la rend testable sur un PC, sans Raspberry Pi.
"""

from __future__ import annotations

import time

from .esbridge import (
    EsLauncher,
    current_target,
    describe_state,
    game_is_running,
    read_state,
)
from .storage import StorageError, pretty_uid

MODE_IDLE = ""
MODE_ASSOCIATE = "associate"
MODE_DELETE = "delete"

# Action a effectuer quand un badge deja enregistre est scanne.
ACTION_LAUNCH = "launch"   # lance le jeu (comportement historique)
ACTION_NONE = "none"       # bip de confirmation et journal, sans rien lancer


class Controller:
    """Machine a etats : repos <-> association / suppression."""

    def __init__(
        self,
        store,
        launcher: EsLauncher,
        feedback,
        cfg=None,
        log=None,
        state_provider=None,
        clock=None,
    ):
        self.store = store
        self.launcher = launcher
        self.feedback = feedback
        self.cfg = cfg
        self.log = log
        self.state_provider = state_provider or (lambda: read_state())
        self.clock = clock or time.monotonic

        self.launch_after_bind = True
        self.ignore_when_running = True
        self.arm_timeout_s = 10.0
        self.action = ACTION_LAUNCH
        if cfg is not None:
            self.launch_after_bind = cfg.get_bool("launch", "launch_after_bind", True)
            self.ignore_when_running = cfg.get_bool("launch", "ignore_when_game_running", True)
            self.arm_timeout_s = cfg.get_float("button", "arm_timeout_s", 10.0)
            self.action = cfg.get("launch", "action", ACTION_LAUNCH).strip().lower()

        self.mode = MODE_IDLE
        self.target = None
        self._deadline = 0.0

    # ------------------------------------------------------------------ helpers
    def _log(self, level: str, message: str) -> None:
        if self.log:
            getattr(self.log, level)(message)

    def _arm(self, mode: str, target=None) -> None:
        self.mode = mode
        self.target = target
        self._deadline = self.clock() + self.arm_timeout_s

    def disarm(self, reason: str = "") -> None:
        if self.mode:
            self._log("info", "Mode %s termine%s" % (self.mode, (" (%s)" % reason) if reason else ""))
        self.mode = MODE_IDLE
        self.target = None
        self._deadline = 0.0

    @property
    def armed(self) -> bool:
        return self.mode != MODE_IDLE

    def status(self) -> dict:
        return {
            "mode": self.mode,
            "target": self.target.describe() if self.target else None,
            "seconds_left": max(0.0, round(self._deadline - self.clock(), 1)) if self.armed else 0.0,
        }

    # -------------------------------------------------------------------- tick
    def tick(self) -> str:
        """A appeler regulierement : gere l'expiration du mode arme."""
        if self.armed and self.clock() >= self._deadline:
            self.disarm("delai depasse")
            self.feedback.timeout()
            return "expired"
        return ""

    # ------------------------------------------------------------------ bouton
    def on_button(self, gesture: str) -> str:
        """Appui court : associer le badge au jeu selectionne ; appui long : effacer."""
        if gesture == "long":
            self._arm(MODE_DELETE)
            self.feedback.armed_delete()
            self._log(
                "info",
                "Appui long : scannez le badge a effacer (%.0f s)" % self.arm_timeout_s,
            )
            return "armed_delete"

        state = self.state_provider()
        # allow_running : le frontend laisse parfois State=playing alors qu'on est
        # simplement sur la fiche d'un jeu (aucune partie en cours). Pour une
        # association, c'est bien le jeu affiche que l'on veut.
        target = current_target(state, allow_running=True)
        if target is None:
            self.feedback.error()
            self._log(
                "warning",
                "Aucun jeu selectionne dans Recalbox (%s) : choisissez un jeu dans la "
                "liste, puis appuyez sur le bouton." % describe_state(state),
            )
            return "no_target"

        self._arm(MODE_ASSOCIATE, target)
        self.feedback.armed()
        self._log(
            "info",
            "Association en attente : scannez un badge pour l'associer a %s (%.0f s)"
            % (target.describe(), self.arm_timeout_s),
        )
        return "armed_associate"

    # ------------------------------------------------------------------- badge
    def on_badge(self, uid: str) -> str:
        """Traite la lecture d'un badge (UID hexa sans separateur)."""
        uid = str(uid).upper()

        if self.mode == MODE_ASSOCIATE and self.target is not None:
            return self._bind(uid, self.target)
        if self.mode == MODE_DELETE:
            return self._delete(uid)

        try:
            entry = self.store.get(uid)
        except StorageError as exc:
            self.feedback.error()
            self._log("error", "Base de badges illisible : %s" % exc)
            return "failed"

        if not entry:
            self.feedback.error()
            self._log("info", "Badge inconnu : %s" % pretty_uid(uid))
            return "unknown"

        if self.ignore_when_running:
            state = self.state_provider()
            if game_is_running(state):
                self._log("info", "Jeu deja en cours : badge %s ignore" % pretty_uid(uid))
                return "ignored"

        # action = none : le badge est reconnu mais rien n'est lance
        if self.action == ACTION_NONE:
            self.feedback.recognized()
            self._log(
                "info",
                "Badge %s reconnu : %s (%s) -- action desactivee (action = none)"
                % (pretty_uid(uid), entry.get("name") or entry.get("game"), entry.get("system")),
            )
            return "recognized"

        return self._launch(entry, uid)

    # ------------------------------------------------------------------ interne
    def _bind(self, uid: str, target) -> str:
        self.disarm("association")
        # On valide la trame tout de suite : un nom de jeu contenant '|' ne peut
        # pas etre transmis au frontend.
        try:
            EsLauncher.build_payload(target.system, target.game)
        except ValueError as exc:
            self.feedback.error()
            self._log("error", "Association impossible : %s" % exc)
            return "failed"

        try:
            self.store.put(uid, target.system, target.game, target.name, target.path)
        except StorageError as exc:
            self.feedback.error()
            self._log("error", "Enregistrement du badge impossible : %s" % exc)
            return "failed"

        attendus = (
            "/recalbox/share/roms/%s/" % target.system,
            "/recalbox/share_init/roms/%s/" % target.system,
        )
        if target.path and not target.path.startswith(attendus):
            self._log(
                "warning",
                "Chemin inhabituel pour ce jeu (%s) : verifiez le lancement." % target.path,
            )

        self.feedback.ok()
        self._log(
            "info",
            "Badge %s associe a %s (%s / %s)"
            % (pretty_uid(uid), target.name or target.game, target.system, target.game),
        )
        if self.launch_after_bind:
            self._launch(
                {
                    "system": target.system,
                    "game": target.game,
                    "path": target.path,
                    "name": target.name,
                },
                uid,
                touch=False,
            )
        return "bound"

    def _delete(self, uid: str) -> str:
        self.disarm("suppression")
        try:
            removed = self.store.delete(uid)
        except StorageError as exc:
            self.feedback.error()
            self._log("error", "Effacement impossible : %s" % exc)
            return "failed"
        if removed:
            self.feedback.removed()
            self._log("info", "Badge %s efface" % pretty_uid(uid))
            return "deleted"
        self.feedback.error()
        self._log("info", "Badge %s inconnu : rien a effacer" % pretty_uid(uid))
        return "unknown"

    def _launch(self, entry, uid: str, touch: bool = True) -> str:
        system = entry.get("system", "")
        # Le frontend identifie un jeu par son CHEMIN COMPLET, tel qu'il l'ecrit
        # lui-meme dans /tmp/es_state.inf (ex. /recalbox/share_init/roms/...).
        # Le nom de fichier seul est refuse depuis Recalbox 10 ("Couldn't find
        # game ..."). On garde le nom relatif en secours (anciennes entrees).
        game = entry.get("path") or entry.get("game", "")
        if self.launcher.start_game(system, game):
            if touch:
                try:
                    self.store.touch(uid)
                except StorageError as exc:
                    self._log("warning", "Statistiques non mises a jour : %s" % exc)
            self.feedback.ok()
            self._log(
                "info",
                "Lancement de %s (%s / %s)"
                % (entry.get("name") or game, system, entry.get("game") or game),
            )
            return "launched"
        self.feedback.error()
        self._log("error", "Le frontend n'a pas pu etre contacte pour lancer %s" % game)
        return "failed"
