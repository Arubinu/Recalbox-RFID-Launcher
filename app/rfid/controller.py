"""Business logic: a badge starts a game, the button pairs or erases.

This class touches neither the hardware nor the file system: it receives a
badge store, a launcher, a user feedback and a state source. That is what
makes it testable on a PC, without a Raspberry Pi.
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

# Action to perform when an already registered badge is scanned.
ACTION_LAUNCH = "launch"   # starts the game (historical behaviour)
ACTION_NONE = "none"       # confirmation beep and log, without starting anything


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

        self.ignore_when_running = True
        self.arm_timeout_s = 10.0
        self.action = ACTION_LAUNCH
        if cfg is not None:
            self.ignore_when_running = cfg.get_bool("launch", "ignore_when_game_running", True)
            self.arm_timeout_s = cfg.get_float("button", "arm_timeout_s", 10.0)
            self.action = cfg.get("launch", "action", ACTION_LAUNCH).strip().lower()

        self.mode = MODE_IDLE
        self.target = None
        self._deadline = 0.0
        self.last_action = ""

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
        """To call regularly: handles the expiry of the armed mode."""
        if self.armed and self.clock() >= self._deadline:
            self.disarm("delai depasse")
            self.feedback.timeout()
            return "expired"
        return ""

    # ------------------------------------------------------------------ button
    def on_button(self, gesture: str) -> str:
        """Short press: pair the badge with the selected game; long press: erase."""
        if gesture == "long":
            self._arm(MODE_DELETE)
            self.feedback.armed_delete()
            self._log(
                "info",
                "Appui long : scannez le badge a effacer (%.0f s)" % self.arm_timeout_s,
            )
            return "armed_delete"

        state = self.state_provider()
        # allow_running: the frontend sometimes leaves State=playing while the
        # user is simply on a game's page (no game running). For an association,
        # the displayed game is indeed the one wanted.
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
        """Handles a badge read (hex UID without separator)."""
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

        # action = none: the badge is recognized but nothing is started
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
        # The frame is validated right away: a game name holding '|' cannot be
        # sent to the frontend.
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
        return "bound"

    def game_running(self) -> bool:
        """True if an emulator is really running (not just started)."""
        try:
            return bool(self.launcher.game_running())
        except Exception:  # noqa: BLE001 - unreadable /proc: nothing is concluded
            return False

    def stop_game(self) -> bool:
        """Quits the running game (badge removed, option enabled)."""
        if not self.launcher.stop_game():
            self._log("info", "Aucun jeu en cours a arreter")
            self.last_action = ""
            return False
        self.last_action = ""
        self._log("info", "Jeu arrete : le badge a ete retire")
        return True

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
        # The frontend identifies a game by its FULL PATH, as it writes it itself
        # in /tmp/es_state.inf (e.g. /recalbox/share_init/roms/...). The file name
        # alone is refused since Recalbox 10 ("Couldn't find game ..."). The
        # relative name is kept as a fallback (older entries).
        game = entry.get("path") or entry.get("game", "")
        if self.launcher.start_game(system, game):
            if touch:
                try:
                    self.store.touch(uid)
                except StorageError as exc:
                    self._log("warning", "Statistiques non mises a jour : %s" % exc)
            # No beep: the launch is visible on screen (game splash).
            self.last_action = "launched"
            self._log(
                "info",
                "Lancement de %s (%s / %s)"
                % (entry.get("name") or game, system, entry.get("game") or game),
            )
            return "launched"
        self.feedback.error()
        self._log("error", "Le frontend n'a pas pu etre contacte pour lancer %s" % game)
        return "failed"
