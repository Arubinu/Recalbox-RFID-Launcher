"""Business logic: a badge starts a game, the button pairs or erases.

This class touches neither the hardware nor the file system: it receives a
badge store, a launcher, a user feedback and a state source. That is what
makes it testable on a PC, without a Raspberry Pi.

Optional helpers (all may be None):

* ``library``  -- game list, for the "random game" cards;
* ``playtime`` -- time-limited games and bonus cards;
* ``screen``   -- messages on the game screen (RetroArch);
* ``light``    -- status light;
* ``power``    -- function that turns the Recalbox off;
* ``card_reader`` -- function returning the memory of the badge on the reader
  (portable cards: the game is written in the badge).
"""

from __future__ import annotations

import os
import time

from .esbridge import (
    EsLauncher,
    Target,
    describe_state,
    game_is_running,
    read_state,
    selected_target,
)
from . import portable
from .library import LibraryError, relative_to_system
from .storage import KIND_ACTION, StorageError, pretty_uid

MODE_IDLE = ""
MODE_ASSOCIATE = "associate"
MODE_DELETE = "delete"

# Action to perform when an already registered badge is scanned.
ACTION_LAUNCH = "launch"   # starts the game (historical behaviour)
ACTION_NONE = "none"       # confirmation beep and log, without starting anything

#: Special cards that act even while a game is running.
ACTIONS_DURING_GAME = ("quit", "bonus", "poweroff", "player")


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
        library=None,
        playtime=None,
        screen=None,
        light=None,
        power=None,
        card_reader=None,
        players=None,
        saver=None,
        unlock=None,
        unlocked=None,
    ):
        self.store = store
        self.launcher = launcher
        self.feedback = feedback
        self.cfg = cfg
        self.log = log
        self.state_provider = state_provider or (lambda: read_state())
        self.clock = clock or time.monotonic
        self.library = library
        self.playtime = playtime
        self.screen = screen
        self.light = light
        self.power = power
        self.card_reader = card_reader
        self.players = players
        #: Saves the game before quitting it (savegame.GameSaver).
        self.saver = saver
        #: "unlock" card: callable doing the switch; unlocked(): is it open.
        self.unlock = unlock
        self._unlocked = unlocked

        self.ignore_when_running = True
        self.save_on_quit = False
        self.arm_timeout_s = 10.0
        self.action = ACTION_LAUNCH
        self.default_limit_min = 0
        self.players_enabled = False
        self.require_player = False
        self.block_exhausted = True
        self.guest_quota_min = 0
        self.guest_period = "day"
        if cfg is not None:
            self.players_enabled = cfg.get_bool("players", "enabled", False)
            self.require_player = cfg.get_bool("players", "require", False)
            self.block_exhausted = cfg.get_bool("players", "block_exhausted", True)
            self.guest_quota_min = max(0, cfg.get_int("players", "guest_quota_min", 0))
            period = cfg.get("players", "guest_period", "day").strip()
            self.guest_period = "week" if period == "week" else "day"
            if self.players is not None:
                self.players.keep = cfg.get_bool("players", "keep_active", False)
                if not self.players.keep:
                    self.players.kept = None
        if cfg is not None:
            self.ignore_when_running = cfg.get_bool("launch", "ignore_when_game_running", True)
            self.save_on_quit = cfg.get_bool("launch", "save_on_quit", False)
            self.arm_timeout_s = cfg.get_float("button", "arm_timeout_s", 10.0)
            self.action = cfg.get("launch", "action", ACTION_LAUNCH).strip().lower()
            self.default_limit_min = max(0, cfg.get_int("time", "default_limit_min", 0))

        self.mode = MODE_IDLE
        self.target = None
        #: Entry to store at the next badge (special card or game chosen in the page).
        self.pending_entry = None
        self._deadline = 0.0
        self.last_action = ""
        #: UID of the card that started the running game (None otherwise).
        self.launched_uid = None

    # ------------------------------------------------------------------ helpers
    def _log(self, level: str, message: str) -> None:
        if self.log:
            getattr(self.log, level)(message)

    def _flash(self, event: str) -> None:
        if self.light is not None:
            self.light.flash(event)

    def _say(self, key: str, **values) -> None:
        if self.screen is not None:
            self.screen.say(key, **values)

    def _arm(self, mode: str, target=None) -> None:
        self.mode = mode
        self.target = target
        self._deadline = self.clock() + self.arm_timeout_s

    def disarm(self, reason: str = "") -> None:
        if self.mode:
            self._log("info", "Mode %s termine%s" % (self.mode, (" (%s)" % reason) if reason else ""))
        self.mode = MODE_IDLE
        self.target = None
        self.pending_entry = None
        self._deadline = 0.0

    @property
    def armed(self) -> bool:
        return self.mode != MODE_IDLE

    def status(self) -> dict:
        if self.pending_entry is not None:
            label = self.pending_entry.get("name") or self.pending_entry.get("action") or ""
        else:
            label = self.target.describe() if self.target else None
        return {
            "mode": self.mode,
            "target": label,
            "seconds_left": max(0.0, round(self._deadline - self.clock(), 1)) if self.armed else 0.0,
        }

    # -------------------------------------------------------------------- tick
    def tick(self) -> str:
        """To call regularly: handles the expiry of the armed mode."""
        if self.armed and self.clock() >= self._deadline:
            self.disarm("delai depasse")
            self.feedback.timeout()
            self._flash("error")
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
        # During the screensaver, the frontend blanks the state file: the last
        # selected game (remembered by the service) is still the right one.
        target, _remembered = selected_target(state, allow_running=True)
        if target is None:
            self.feedback.error()
            self._flash("error")
            self._log(
                "warning",
                "Aucun jeu selectionne dans Recalbox (%s) : choisissez un jeu dans la "
                "liste, puis appuyez sur le bouton." % describe_state(state),
            )
            return "no_target"

        return self.arm_target(target)

    def arm_target(self, target: Target) -> str:
        """Waits for a badge to pair with ``target`` (selected or chosen in the page)."""
        self._arm(MODE_ASSOCIATE, target)
        self.feedback.armed()
        self._say("armed")
        self._log(
            "info",
            "Association en attente : scannez un badge pour l'associer a %s (%.0f s)"
            % (target.describe(), self.arm_timeout_s),
        )
        return "armed_associate"

    def arm_entry(self, entry: dict) -> str:
        """Waits for a badge to become a special card (or any prepared entry)."""
        self._arm(MODE_ASSOCIATE, None)
        self.pending_entry = dict(entry)
        self.feedback.armed()
        self._log(
            "info",
            "Association en attente : scannez un badge pour en faire la carte %s (%.0f s)"
            % (entry.get("name") or entry.get("action"), self.arm_timeout_s),
        )
        return "armed_associate"

    # ------------------------------------------------------------------- badge
    def on_badge(self, uid: str) -> str:
        """Handles a badge read (hex UID without separator)."""
        uid = str(uid).upper()
        # "launched" only describes THIS badge (the service uses it to know
        # which card holds the running game).
        self.last_action = ""

        if self.mode == MODE_ASSOCIATE and self.pending_entry is not None:
            return self._bind_entry(uid, self.pending_entry)
        if self.mode == MODE_ASSOCIATE and self.target is not None:
            return self._bind(uid, self.target)
        if self.mode == MODE_DELETE:
            return self._delete(uid)

        try:
            entry = self.store.get(uid)
        except StorageError as exc:
            self.feedback.error()
            self._flash("error")
            self._log("error", "Base de badges illisible : %s" % exc)
            return "failed"

        if not entry:
            entry = self._portable(uid)
            if entry is not None and entry.get("missing"):
                self.feedback.error()
                self._flash("error")
                self._log("info", "Badge %s : %s / %s n'est pas installe sur cette Recalbox"
                          % (pretty_uid(uid), entry["system"], entry["game"]))
                return "missing"

        if not entry:
            self.feedback.error()
            self._flash("error")
            self._say("unknown")
            self._log("info", "Badge inconnu : %s" % pretty_uid(uid))
            return "unknown"

        is_action = entry.get("kind") == KIND_ACTION
        if self.ignore_when_running and not (is_action and entry.get("action") in ACTIONS_DURING_GAME):
            state = self.state_provider()
            if game_is_running(state):
                self._log("info", "Jeu deja en cours : badge %s ignore" % pretty_uid(uid))
                return "ignored"

        # action = none: the badge is recognized but nothing is started
        if self.action == ACTION_NONE:
            self.feedback.recognized()
            self._flash("ok")
            self._log(
                "info",
                "Badge %s reconnu : %s (%s) -- action desactivee (action = none)"
                % (pretty_uid(uid), entry.get("name") or entry.get("game"), entry.get("system")),
            )
            return "recognized"

        if is_action:
            return self._special(uid, entry)
        return self._launch_for_player(entry, uid)

    def _portable(self, uid: str):
        """Game written in the memory of an unknown badge (portable card)."""
        if self.card_reader is None:
            return None
        try:
            data = self.card_reader()
        except Exception as exc:  # noqa: BLE001 - never blocking
            self._log("debug", "Memoire du badge illisible : %s" % exc)
            return None
        entry = portable.entry_from(data)
        if entry is not None and not entry.get("missing"):
            self._log("info", "Badge %s : jeu ecrit dans le badge (%s / %s)"
                      % (pretty_uid(uid), entry["system"], entry["game"]))
        return entry

    # ------------------------------------------------------------------ interne
    def _bind(self, uid: str, target) -> str:
        self.disarm("association")
        # The frame is validated right away: a game name holding '|' cannot be
        # sent to the frontend.
        try:
            EsLauncher.build_payload(target.system, target.game)
        except ValueError as exc:
            self.feedback.error()
            self._flash("error")
            self._log("error", "Association impossible : %s" % exc)
            return "failed"

        try:
            self.store.put(uid, target.system, target.game, target.name, target.path)
        except StorageError as exc:
            self.feedback.error()
            self._flash("error")
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
        self._flash("ok")
        self._say("bound")
        self._log(
            "info",
            "Badge %s associe a %s (%s / %s)"
            % (pretty_uid(uid), target.name or target.game, target.system, target.game),
        )
        return "bound"

    def _bind_entry(self, uid: str, entry: dict) -> str:
        self.disarm("association")
        try:
            saved = self.store.put_entry(uid, entry)
        except StorageError as exc:
            self.feedback.error()
            self._flash("error")
            self._log("error", "Enregistrement de la carte impossible : %s" % exc)
            return "failed"
        self.feedback.ok()
        self._flash("ok")
        self._say("bound")
        self._log("info", "Badge %s devenu la carte « %s »" % (pretty_uid(uid), saved.get("name")))
        return "bound"

    def game_running(self) -> bool:
        """True if an emulator is really running (not just started)."""
        try:
            return bool(self.launcher.game_running())
        except Exception:  # noqa: BLE001 - unreadable /proc: nothing is concluded
            return False

    def save_owner(self) -> str:
        """Card of the player whose game is saved ("" = the shared save)."""
        current = self.players.current if self.counting_players else None
        if not isinstance(current, dict) or current.get("uid") in ("", "guest"):
            return ""
        return current["uid"]

    def running_game(self):
        """{"system", "name"} of the game the frontend runs (None if unknown)."""
        try:
            state = self.state_provider() or {}
        except Exception:  # noqa: BLE001 - unreadable state file
            return None
        system = str(state.get("SystemId") or "").strip()
        name = str(state.get("Game") or "").strip()
        if not name:
            path = str(state.get("GamePath") or "")
            name = os.path.splitext(os.path.basename(path))[0] if path else ""
        return {"system": system, "name": name} if system and name else None

    def stop_game(self, reason: str = "removed") -> bool:
        """Quits the running game (badge removed, quit card, time up).

        reason "refused" (a game not allowed to start) or "new" (a new game is
        wanted): the game is not saved.
        """
        if self.save_on_quit and self.saver is not None and reason not in ("refused", "new"):
            try:
                self.saver.save(owner=self.save_owner())
            except Exception as exc:  # noqa: BLE001 - the game is quit anyway
                self._log("warning", "Sauvegarde de la partie impossible : %s" % exc)
        if self.playtime is not None:
            self.playtime.end(reason)
        if self.players is not None:
            self.players.finish()
        self.launched_uid = None
        if not self.launcher.stop_game():
            self._log("info", "Aucun jeu en cours a arreter")
            self.last_action = ""
            return False
        self.last_action = ""
        self._log("info", "Jeu arrete (%s)" % reason)
        return True

    def _delete(self, uid: str) -> str:
        self.disarm("suppression")
        try:
            removed = self.store.delete(uid)
        except StorageError as exc:
            self.feedback.error()
            self._flash("error")
            self._log("error", "Effacement impossible : %s" % exc)
            return "failed"
        if removed:
            self.feedback.removed()
            self._flash("ok")
            self._log("info", "Badge %s efface" % pretty_uid(uid))
            return "deleted"
        self.feedback.error()
        self._flash("error")
        self._log("info", "Badge %s inconnu : rien a effacer" % pretty_uid(uid))
        return "unknown"

    def limit_for(self, entry: dict) -> int:
        """Minutes of play allowed by a card (0 = no limit)."""
        limit = entry.get("limit_min")
        if limit is None:
            return self.default_limit_min
        return max(0, int(limit))

    # ------------------------------------------------------------ players
    @property
    def unlocked(self) -> bool:
        """The "unlock" card opened the menu: no game is blocked."""
        try:
            return bool(self._unlocked and self._unlocked())
        except Exception:  # noqa: BLE001 - unreadable state: keep the rules
            return False

    @property
    def counting_players(self) -> bool:
        return self.players is not None and self.players_enabled

    def player_left(self, uid: str, entry: dict):
        """Seconds left to a player card (None = no limit)."""
        params = entry.get("params") or {}
        return self.players.remaining_s(uid, int(params.get("quota_min") or 0), params.get("period") or "day")

    def guest_left(self):
        return self.players.remaining_s("", self.guest_quota_min, self.guest_period)

    def _refuse(self, key: str, message: str, **values) -> None:
        self.feedback.error()
        self._flash("error")
        self._say(key, **values)
        self._log("info", message)

    def game_card(self, uid: str):
        """Entry of a game card (None for an unknown or special card)."""
        try:
            entry = self.store.get(str(uid or "").upper())
        except StorageError:
            return None
        if not entry or entry.get("kind") == KIND_ACTION:
            return None
        return entry

    def new_game(self, uid: str, player=None) -> str:
        """Starts the game card ``uid`` again from the beginning (button double press).

        player: (uid, entry) of the player of the game that was just quit.
        """
        entry = self.game_card(uid)
        if entry is None:
            return "no_card"
        return self._launch_for_player(entry, str(uid).upper(), touch=False, player=player)

    def _launch_for_player(self, entry, uid: str, touch: bool = True, player=None) -> str:
        """Starts a game card for the waiting player card (or the guest).

        player: (uid, entry) to use instead of the waiting card (a new game).
        """
        if not self.counting_players:
            return self._launch(entry, uid, touch=touch)
        pending = self.players.take_pending()
        if player is not None and player[0]:
            pending = {"uid": player[0], "entry": player[1]}
        free = self.unlocked
        if pending is not None:
            player = (pending["uid"], pending["entry"])
            left = self.player_left(*player)
            name = self.players.player_name(pending["entry"])
            if free:
                left = None
            if left is not None and left <= 0:
                if pending.get("kept"):
                    self.players.release("temps ecoule")
                self._refuse("player_exhausted", "Carte joueur %s : plus de temps de jeu" % name, name=name)
                return "exhausted"
        else:
            if self.require_player and not free:
                self._refuse("player_needed", "Jeu refuse : posez d'abord une carte joueur")
                return "player_needed"
            player = ("", {})
            left = None if free else self.guest_left()
            if left is not None and left <= 0:
                self._refuse("guest_exhausted", "Jeu refuse : plus de temps de jeu sans carte joueur")
                return "exhausted"
        minutes = None
        if left is not None:
            card = self.limit_for(entry)
            minutes = left / 60.0 if not card else min(float(card), left / 60.0)
        return self._launch(entry, uid, touch=touch, minutes=minutes, player=player)

    def _player_card(self, uid: str, entry: dict) -> str:
        """Player card: counts for the next game, or the game just started from the menu."""
        if not self.counting_players:
            self.feedback.error()
            self._flash("error")
            self._log("info", "Carte joueur : les cartes joueurs sont desactivees dans les reglages")
            return "disabled"
        name = self.players.player_name(entry)
        left = self.player_left(uid, entry)
        if left is not None and left <= 0:
            self._refuse("player_exhausted", "Carte joueur %s : plus de temps de jeu" % name, name=name)
            return "exhausted"
        self._touch(uid)
        current = self.players.current
        if self.game_running() and (current is None or current["uid"] == "guest"):
            # Game started from the menu without a card: it becomes this
            # player's, and lasts while the card stays on the reader.
            self.players.begin(uid, entry, via="reader", game=self.running_game())
            if self.playtime is not None and left is not None and self.playtime.session is None:
                self.playtime.start(uid, {"name": name}, left / 60.0)
            self.feedback.ok()
            self._flash("ok")
            self._greet(name, left)
            self._log("info", "Carte joueur %s : la partie en cours lui est comptee" % name)
            return "player_game"
        self.players.arm(uid, entry)
        self.feedback.ok()
        self._flash("ok")
        self._log("info", "Carte joueur %s : pour la prochaine partie" % name)
        return "player"

    def _greet(self, name: str, left) -> None:
        if left is None:
            self._say("player_unlimited", name=name)
        else:
            self._say("player_hello", name=name, n=max(1, int(round(left / 60.0))))

    def _launch(self, entry, uid: str, touch: bool = True, minutes=None, player=None) -> str:
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
            self.launched_uid = uid
            self._flash("launch")
            if self.playtime is not None:
                self.playtime.start(uid, entry, self.limit_for(entry) if minutes is None else minutes)
            if self.counting_players:
                who = player if player is not None else self.players.resume_player()
                name = entry.get("name") or os.path.splitext(os.path.basename(str(game)))[0]
                self.players.begin(who[0], who[1], via="card", game={"system": system, "name": name})
            self._log(
                "info",
                "Lancement de %s (%s / %s)"
                % (entry.get("name") or game, system, entry.get("game") or game),
            )
            return "launched"
        self.feedback.error()
        self._flash("error")
        self._log("error", "Le frontend n'a pas pu etre contacte pour lancer %s" % game)
        return "failed"

    # --------------------------------------------------------- special cards
    def _special(self, uid: str, entry: dict) -> str:
        action = entry.get("action")
        params = entry.get("params") or {}
        if action == "quit":
            if self.stop_game("quit"):
                self.feedback.ok()
                self._flash("ok")
                self._touch(uid)
                return "quit"
            self.feedback.error()
            self._flash("error")
            return "nothing"
        if action == "poweroff":
            self._log("info", "Carte « eteindre » : arret de la Recalbox")
            self.feedback.ok()
            self._flash("ok")
            self._touch(uid)
            if self.power is not None:
                self.power()
            return "poweroff"
        if action == "random":
            return self._random(uid, entry, params)
        if action == "bonus":
            return self._bonus(uid, params)
        if action == "player":
            return self._player_card(uid, entry)
        if action == "unlock":
            if self.unlock is None:
                self.feedback.error()
                self._flash("error")
                return "failed"
            self._touch(uid)
            return self.unlock()
        self.feedback.error()
        return "unknown"

    def _touch(self, uid: str) -> None:
        try:
            self.store.touch(uid)
        except StorageError:
            pass

    def _random(self, uid: str, entry: dict, params: dict) -> str:
        if self.library is None:
            self.feedback.error()
            self._flash("error")
            return "failed"
        try:
            game = self.library.pick_random(params.get("system") or "", bool(params.get("favorites")))
        except LibraryError as exc:
            game = None
            self._log("warning", "Liste des jeux illisible : %s" % exc)
        if not game:
            self.feedback.error()
            self._flash("error")
            self._log("info", "Carte « jeu au hasard » : aucun jeu trouve")
            return "nothing"
        chosen = {
            "system": game["system"],
            "game": relative_to_system(game["system"], game["path"]),
            "path": game["path"],
            "name": game["name"],
            "limit_min": entry.get("limit_min"),
        }
        self._log("info", "Jeu au hasard : %s (%s)" % (game["name"], game["system"]))
        self._touch(uid)
        return self._launch_for_player(chosen, uid, touch=False)

    def _bonus(self, uid: str, params: dict) -> str:
        if self.playtime is None:
            self.feedback.error()
            return "nothing"
        result = self.playtime.bonus(uid, params)
        kind = result["result"]
        if kind == "exhausted":
            self.feedback.error()
            self._flash("error")
            self._say("exhausted")
            self._log("info", "Carte bonus : plus d'utilisation possible pour cette periode")
            return "exhausted"
        if kind == "nothing":
            self.feedback.error()
            self._flash("error")
            self._log("info", "Carte bonus : aucun jeu limite en cours ou juste termine")
            return "nothing"
        self._touch(uid)
        left = result.get("left")
        if kind == "extended":
            self.feedback.ok()
            self._flash("bonus")
            if left is None:
                self._say("bonus", n=result["minutes"])
            else:
                self._say("bonus_left", n=result["minutes"], k=left)
            self._log("info", "Carte bonus : +%d min" % result["minutes"])
            return "extended"
        # Game just ended: started again with the bonus time.
        self._flash("bonus")
        self._log("info", "Carte bonus : reprise de %s pour %d min"
                  % (result["entry"].get("name"), result["minutes"]))
        outcome = self._launch(result["entry"], uid, touch=False, minutes=result["minutes"])
        return "resumed" if outcome == "launched" else outcome
