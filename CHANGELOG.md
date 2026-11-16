# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
semantic versioning. The current version is also in the `VERSION` file and shown
by `rfidctl version`.

## [1.2.0]

### Added

* **A card design for each console** (the new default card): about a hundred
  consoles, each drawn from its own distinctive signs (shape, colours, buttons,
  ports...), the game picture in a window, and the title on the tab that sticks
  out of the reader. Option: the Mega Drive tab on every card, so that a
  collection looks the same in the reader.
* **One choice for the way the card goes in the reader**: landscape with the
  tab on the left or on the right (slot on the side of the box), or portrait
  with the tab at the bottom (slot in the front). It replaces the direction and
  slot-edge settings.
* Title in **capitals** and with a **shadow** (options); **compact** number of
  players (an icon and "1–2"); the **console name** written instead of its
  logo (the default of the console design).
* A console without a design of its own gets its name and initials from the
  Recalbox.
* The page served by the Recalbox goes straight to the connection.

### Changed

* **"Automatic" logo colour**, first in the list and the default: a logo of
  several colours keeps them, a one-colour logo is painted light or dark
  against what is under it, with a halo when it would melt into the background.
* Changing the direction of the card keeps the settings of each element.
* Without a console logo, the title is centred (Cartouche, Bandeau, Minimal).

### Fixed

* In reader mode, console logos and drawings are read from the theme files
  (EmulationStation and its API are stopped).
* A newly chosen game shows on the card at once.
* Printing with bleed: the corners are filled; no light edge around the card.

## [Unreleased]

### Added

* **Bedtime**: no games between two hours, a warning 5 minutes before, then
  the game is saved and quit; option to turn the Recalbox off.
* **Continue card**: starts again the last game of the active player.
* **Reader screen**: dims after a while (like Recalbox's screen saver, or a
  chosen delay); facts and trophies now and then in place of the hint
  (START + SELECT, favourite game, last trophy, game of the week); a message
  written in the page; restart of the reader screen from the page.
* **Trophies** for the players (consoles, games, days in a row, hours).
* **Refused games** in the statistics: who, what, when and why.
* **Reader screen straight at boot**: the Recalbox interface no longer
  starts first (`system.es.atstartup=0` and a block of `custom.sh`, both
  given back when the reader screen is left), with a safety that brings the
  interface back if the service does not start.
* **Several players per game** (option): player cards add up before a game
  (placed again, a card leaves the group or stays alone; or cards placed one
  after the other); the time counts for each. **Controllers allowed**: all,
  or one per active player (RetroArch games).
* **Updates from GitHub**: the page offers the latest published version in
  one click (option).
* **Add several cards** to the print sheet: paired games, favourites or
  every game of a console.
* **Another time per day** on a player card (for example more at the
  weekend, on chosen days) and **holidays** (two dates in the settings) when
  that other time applies every day.
* **Guest card**: a player card for a friend dropping by, with its time per
  day and an end date; left out of the trophies and the weekly summary.
* **Remote control in the page**: a "Playing" bar with the game, the
  player and the time left, and Pause, +10 min, Quit and Turn off buttons.
* **Home Assistant** (MQTT, option): the reader shows up by itself (MQTT
  discovery) with the game, the player, the time left, bedtime, the last
  refused game, and Quit, Pause, +10 minutes and Turn off buttons. A small
  MQTT client is included (no package to install).
* **Status light**: purple at bedtime, orange when the active player has no
  time left (option).
* **Reader screen**: light colours and large small texts (options); a
  **weekly summary** on the first day of the week (time played by each
  player and new trophies; the first day of the week is the one of the
  player cards).
* **Fades to black on the reader screen** (option, on by default): from black
  when it shows, to black (with the music) when a game starts.
* **Background music on the reader screen**, like the Recalbox interface:
  the music of its theme and of `/recalbox/share/music`, at random, with the
  track name (when Recalbox shows it); played with SDL2_mixer, the library of
  the Recalbox interface. Like Recalbox (default), always or off, and its own
  volume or Recalbox's.
* **Volume of the Recalbox in the START + SELECT menu**: a Volume line
  (left and right, 5% steps) for every sound, kept in `recalbox.conf`.
* **Cartridge sounds**: when a game card starts its game, and when the card
  of the running game is removed. Nintendo DS insertion and removal by
  default; Nintendo 64 insertion and removal, Super Nintendo (short, very
  short, full) or a synthetic clack to
  choose for each; a volume in percent and a Listen button in the settings.
  Muted with the Recalbox sound.

## [1.1.0]

### Added

* **Turn off and restart from the reader screen**: START + SELECT open a menu
  (Turn off, Restart, Cancel), then a 5-second countdown that any button
  cancels. Option: both, turn off only, or off.
* **Turn off when nobody plays** (reader screen, option): after a chosen number
  of minutes with no card and no game, a 30-second countdown that a button or
  a card cancels.

### Changed

* The **Turn off** card waits 10 seconds (removing the card cancels) and quits
  the game running first, so it is saved. Option to turn off at once.

## [1.0.0]

First public release.

### Badges and games

* **One badge, one game**: an RC522 reader (13.56 MHz) on a Raspberry Pi
  running Recalbox 9 or newer starts the paired game, as from the Recalbox
  menu. Cartridge mode, and an option to quit the game when the badge is
  removed.
* **Pairing** with the box button (the game highlighted in Recalbox), from the
  management page, or from a phone; badges saved in `tags.json`, CSV export
  and import, portable cards that carry their game.
* **Save before quitting** (on by default) and resume at the next start, one
  save per player.
* **New game** with a double press of the button (RetroArch reset, or a new
  start for the other emulators).

### Special cards

* Random game (every console, one console, the favourites or a collection of
  chosen games), bonus time, quit the game, turn off, unlock, pause (the play
  time stops too), save now, sound on/off, time left, reward.

### Players and play time

* **Player cards**: play time per day or week, reset hour and day, time slots
  (days and hours), allowed consoles and games, avatars, a guest time,
  blocking of the games without a card or without time left, the player kept
  active until their time is up (option), change of player during a game
  (on by default).
* **Time limits** per badge or for all, warnings before the end, bonus cards
  with a quota.
* **Statistics** per player and game (60 days), a week summary, CSV export.
* **Menu lock**: favourites only and no START menu, undone by the unlock card
  or the settings; a safety net brings the menu back if Recalbox cannot start.

### Reader screen (option)

* Replaces the Recalbox interface on the TV: the consoles with games (artwork
  and logos of the Recalbox theme), the active player and their time, the
  messages of the reader. Games start with the cards only, with the very
  command the Recalbox interface would run (checked against it).
* The game placed is shown before it starts; it can also wait for a controller
  button. The active player's games can replace the consoles.
* Drawn by the graphics chip (about 45 frames per second on a Pi 3), smooth
  edges, the resolution of Recalbox or the screen's own, vertical screens
  (Recalbox's rotation setting). The Recalbox interface always comes back
  (setting, unlock card, service stopped, repeated crashes).

### Management page

* A single HTML file opened on the computer (nothing to install), also served
  to phones by the Recalbox: guided installation, wiring diagram, hardware
  check, reader tuning, one-click updates, authorization with the box button.
* Printable cards: seven templates, the game's picture, its console's logo and
  colours, frames of your own, ten cards per A4 sheet.
* Full backup and restore (badges, settings, players, avatars, statistics).
* 6 languages (English, French, German, Spanish, Italian, Portuguese), light
  and dark themes.

### Hardware

* Status light (RGB LED or WS2812 programmable LEDs), beeps, messages on the
  game screen (RetroArch).
* No dependency: only the Python 3 shipped with Recalbox.
