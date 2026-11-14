# Usage

## The principle

* Each badge is paired with **a game** (system + path of the game), or is a
  **special card** (random game, bonus time, quit, turn off).
* Placing a badge on the reader starts its game.
* The **button** of the case pairs a badge with the game selected on the TV,
  and authorizes a computer or a phone (3 s press).

The pairings are stored in `/recalbox/share/system/rfid/tags.json`, a text file
you can read and back up (see below).

## The management page

Two ways to open it:

* **On a computer**: double-click `recalbox-rfid-installer.html` (Edge or
  Chrome). The page opens from the disk (`file://`) and talks to the Recalbox.
* **On a phone or a tablet**: open `http://recalbox.local:8765/` (or
  `http://<IP of the Recalbox>:8765/`). The Recalbox serves the page itself:
  nothing to install. On a computer that is already connected, the phone
  button of the header shows a **QR code** to scan with the camera.

Either way, the device is authorized once by **holding the case button for
3 seconds** during the countdown.

| Tab | What it does |
| --- | --- |
| **Badges** | game selected on the TV and "Pair a badge with this game"; **search a game** of the Recalbox and pair it without the TV; the badge list (rename, time limit, card, delete, CSV backup); **special cards** |
| **Cards** | design and print the cards to put on the badges |
| **Hardware** | state of the reader, the button and the game launch; **Test with a badge**; **automatic tuning** of the reader |
| **Settings** | every setting, saved and applied at once |
| **Updates** | one-click update, service, restart of the Recalbox, logs |

The **`EN` / `FR` / `DE` / `ES` / `IT` / `PT`** button switches the language:
a click picks the next one and keeps it; a **long press** goes back to the
system language. The **sun / moon** button switches the theme the same way.

### Authorization and security

The authorization is **confirmed physically**: the page drops one request (one
at a time, 30 s), the Recalbox waits for a 3 s press on the button, then
authorizes this device. A press started before the request is refused. During
a RetroArch game, the request is also shown on the TV.

* No secret on the network share: the session secret is drawn at random and
  lives in a private folder of the Recalbox (`/tmp`). It survives a page
  refresh, a service restart and an update, not a full restart of the
  Recalbox: the page then asks for a new 3 s press.
* The agent only accepts the page opened from the disk (`file://`) or the page
  it serves itself, and only from the local network. A web site cannot drive
  it, even with a name pointing to the Recalbox.
* Never expose port 8765 on the Internet; for remote access, use a VPN
  (WireGuard, Tailscale…).
* **Page password** (Settings › Security, optional): asked after the 3 s press.
  A child can hold the button too; with a password, only those who know it can
  change the badges, the play time or the settings. Setting or changing it logs
  out every other device. 5 attempts per request. Only a salted hash is stored
  (`access.json`). Forgotten: delete `access.json` from
  `\\RECALBOX\share\system\rfid` and restart the Recalbox.
* **Page for phones** (Settings › Connection): on by default. The page itself
  holds no secret and every action still needs the button (and the password, if
  set), so serving it adds no access that the agent did not already offer on
  port 8765. Turn it off to only allow the page saved on a computer.
* To withdraw every authorization: restart the Recalbox, or set/change the
  password. To disable the agent: `enabled = 0` in `[agent]`.

When the connection drops (restart, network), the page greys out, shows "Connection
lost for N s" and reconnects on its own.

## Pairing a badge

**From the TV**, with the button of the case:

1. On the Recalbox, move to the game in the list (selected, not started). Not
   a folder.
2. **Short press** on the button: one high beep, you have **10 seconds**.
3. Place the badge: two rising beeps, it is paired.

**From the page**: Badges › "Pair a badge with this game" does the same thing
for the game selected on the TV.

**Without the TV**: Badges › **Find a game**, type a few letters, choose the
console if needed, then the badge button of the game, and place the badge. This
is the handy way on a phone.

Pairing a badge that is already known **replaces** its previous game.

## Starting a game

Place the badge. The frontend shows the loading screen of the game, then
starts the emulator; this is the confirmation (no beep).

* A badge placed during a game is ignored ("Do not interrupt a game in
  progress"), except the quit, bonus and turn-off cards.
* An unknown badge: two low beeps (and a message during a RetroArch game).
* "When a paired badge is placed" › "beep only": the badge is recognized, nothing
  starts (handy to check badges).

## Cartridge mode

A badge left on the reader acts **only once**. To start it again, remove it
for about two seconds and put it back. Another badge acts at once.

With **"Quit the game when the badge is removed"**, removing the badge quits
the game and the Recalbox goes back to its menu, like pulling a cartridge out.
This is the setting of the "slot in the case" idea.

**New game**: with a game card on the reader, **press the button twice
quickly**. The game starts again from the beginning, for the same player:

* a RetroArch game (most consoles) is **reset on the spot**, like the reset
  button of a console: instant, the emulator keeps running, "New game" shows
  on the screen;
* another emulator is quit without saving and started again; the saved game
  is not resumed this time (it is replaced at the next save).

A single short press still pairs a badge.

With **"Save the game before quitting"** (Settings, off by default), every
game the reader quits (badge removed, time up, "Quit" card, player card
removed) is saved first, and **resumed where it stopped** the next time it
starts, from a card or from the menu ("Game resumed" on the screen). It uses
RetroArch's save states: the save is kept as the game's "auto" save state
(`saves/<console>/<game>.state.auto`, the same file as Recalbox's own "auto
save/load" option), and your own save slots are left as they were. RetroArch
games only (most consoles); the stand-alone emulators are quit without saving.
With the **player cards**, each player has **their own save**: they find their
game, never someone else's (a player who never saved this game starts it new;
games without a player card use the shared save). These saves are kept in
`player-saves/` in the reader folder: a full uninstall removes them,
`--keep-data` keeps them, and the full backup does not include them yet.

## Special cards

Badges › **Special cards**: choose the card, set it up, then place the badge.

| Card | What it does |
| --- | --- |
| **Random game** | starts a game drawn at random: every console, one console, or only the favourites. Can carry a play time limit |
| **Bonus time** | adds minutes to a time-limited game (see below), a limited number of times per period |
| **Quit the game** | quits the running game, back to the menu |
| **Turn off** | turns the Recalbox off cleanly |

The pencil of a badge changes its name, its time limit, or the parameters of a
special card.

## Portable cards

A pairing lives in the Recalbox (`tags.json`): a badge paired here does nothing
on a friend's Recalbox. The pencil of a game badge › **Write the game into the
badge** stores the game in the chip of the badge itself; place the badge on the
reader within 15 seconds. The page confirms once the game is written and read
back.

* Any Recalbox running this program then starts the game when the badge is
  placed, even if the badge is not in its list, provided the same game is
  installed (same console folder, same file name). Otherwise: two low beeps and
  a line in the log.
* The list of the Recalbox always comes first: a badge paired there keeps its
  local game.
* Compatible badges: **MIFARE Classic** (factory keys; sectors 1 and 2 are
  used), **MIFARE Ultralight** and **NTAG** (from page 4). Some cheap clone
  badges only give their identifier and cannot store anything: the page then
  says so.
* What is written: `RL1|<console>|<file>` (96 bytes at most), not an NDEF record.

## Play time

* **Settings › Play time per game**: a limit for every game badge without its
  own limit (0 = no limit).
* **Per badge** (pencil): empty = the general setting, `0` = never limited,
  otherwise a number of minutes.
* The Recalbox warns **5 minutes** and **1 minute** before the end (message on
  the game screen, beep, yellow light), shows "Play time is over", then quits
  the game 3 seconds later. The page shows the time left.

**Bonus card**: minutes added (1 to 240), number of uses (0 = no limit), and
the period after which the counter starts again (1 hour, 3 h, 12 h, a day, a
week).

* During a limited game: the minutes are added at once.
* Within 15 minutes after the end of a limited game (time up, badge removed,
  game quit): the game starts again with the bonus time plus the time that
  was left. In cartridge mode, simply put the bonus card in the slot instead
  of the game card; if the swap is fast enough, the game does not even stop.
* Once the uses are spent: two low beeps and "Bonus card already used".

The uses are kept in `playtime.json` (they survive a restart). Without a
battery, the Recalbox clock may restart in 1980 until the network gives the
time: the quota then starts again from zero.

## Player cards

Optional (**Settings › Player cards**, off by default). Each person gets a
**player card** (Badges › Special cards › Player card): a first name and a play
time per **day** or per **week** (0 = no limit). The counter restarts at
midnight, or on Monday.

**One card per game**, so that the next person is never counted as the
previous one:

* **With a game card**: place the player card, then the game card within 90
  seconds. The game counts for that player and lasts at most the time left.
  When the game ends, the player card is used up: the next game needs a player
  card again.
* **With a game started from the Recalbox menu**: leave the player card on the
  reader. The game counts for that player; **removing the card ends the game**.
* **Without a player card**: the game counts for the "guest", with its own
  optional time (Settings › Player cards).

The Badges tab shows, per player, the time played and left, with a **Reset**
button, and the **Statistics**: for each player, the time played per day and
their most played games over 7, 30 or 60 days (hover a bar for the day's
time). **Export (CSV)** gives every line kept (day, player, console, game,
minutes), to open in a spreadsheet. A reset only clears the time limit
count, never the statistics. Messages on the game screen: welcome with the time left, "no play time
left", "player card removed". The time is saved per day in `players.json`
(kept 60 days).

Options:

* **Block games without a player card**: a game started without one, even from
  the menu, is quit about two seconds after it starts, with a message on the
  screen (Recalbox itself cannot refuse to start a game).
* **Block games when the time is up** (on by default): the games started from
  the menu by a player (or the guest) with no time left are quit too. Game
  cards are always refused in that case.
* **Lock the Recalbox menu**: the lists only show the **favourite** games (mark
  the allowed games as favourites) and the **START menu is hidden**, so the
  lock cannot be removed from the TV. The menu restarts for a few seconds;
  refused while a game runs. Turned off (or the reader uninstalled), the
  previous settings of `recalbox.conf` come back exactly.

## Printing the cards

Tab **Cards**: the size is the one of a bank card (CR80, 85.6 × 54 mm), at
300 dpi.

1. **Choose a game** (or "Create its card" from a badge or a search result):
   the page fetches its scraped picture, the **logo** and the **drawing of its
   console** from the Recalbox theme, and the main colour of the logo. **My
   image** uses your own picture instead (any size: it is fitted to the card).
   The Cards tab starts from the game selected on the Recalbox.
   **Online pictures**: the Recalbox also looks the game up in the RetroArch
   picture database (libretro thumbnails, no account). When found, the
   **Source** list of the Picture element offers **Box art**, **Screenshot** and
   **Title screen**, and the **Style** of the Title element offers the **Game
   logo** instead of the written title (the Logo element stays the console
   logo: both can be shown together). Matching uses the file name (No-Intro names such as
   "Tetris (World) (Rev 1)" work best), then the game name; homebrews are
   rarely there. It needs internet on the Recalbox; only the console and the
   game name are sent. The folder lists are cached for two weeks in
   `cache/libretro`. Turn it off in Settings › Cards.
2. **Choose a template**: Cartridge, Banner, Game box, Arcade, Minimal,
   Collection (with the console drawing), Box cover and Info card (with the
   **number of players**), Picture only. **Landscape** or **Portrait**.
3. **Adjust each element** (Picture, Title, Logo, Console, Players, Colours): touch it on
   the card and drag it; two fingers to enlarge and rotate it (wheel and
   Shift + wheel with a mouse; arrows to nudge it). The controls under the card
   do the same thing precisely: size, rotation (and quarter turns), font, text
   colour, outline, logo colour, card colour, rounded corners. **Reset
   position** puts an element back where the template had it.
4. **Part sticking out of the slot**: a yellow band shows the edge that stays
   visible when the card is in the slot (top, bottom, left or right): put the
   title and the logo there. The band is never printed.
5. **Save as a template**: keeps the direction, the place, size and rotation of
   every element (and the colour, if you tick it). Templates are saved on the
   Recalbox: they are found on every computer and phone. The × of a template
   deletes it.
6. **Add to the sheet**, then **Print**: ten cards per A4 page, with cut lines.
   Print at **100 %** (actual size, no "fit to page"). **Download the image**
   saves one card as a PNG.
7. **For a print shop**: turn on "bleed and crop marks" (2, 3 or 5 mm). The
   background goes past the cut line, crop marks show where to cut, corners are
   left square (the shop cuts them), and a red dotted line in the editor shows
   the safe area where the text must stay. Eight cards per A4 page then; the
   downloaded PNG gets the bleed too.

**Players**: "1 player", "1–2 players"... with silhouettes, on a pill
(card colour, white, dark) or without background. The number comes from the
Recalbox game list; type it when the game has none (for example `1-2`). Every
template has it, hidden: turn it on with **Show**.

**Undo / redo**: the arrows above the card, or Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z).
One step per gesture, up to 80 steps.

### Your own frames

**Cards › My frames › Import a frame**: a card-sized picture (85.6 × 54 mm,
PNG, SVG, WEBP or JPEG; landscape or portrait) with a **transparent area**
where the game picture goes.

* The page finds the window by itself (the largest transparent area that does
  not touch the edges: transparent rounded corners do not count) and shows it
  striped before saving.
* Tick the **consoles** the frame is meant for: choosing one of their games
  picks the frame. A frame also appears among the templates.
* The game picture shows under the frame and stays movable and zoomable;
  title, logo and console are hidden by default (turn them on if needed).
* Frames are stored on the Recalbox (`frames/`), found on every device.
  **Download** gives the original picture back, to share it: whoever imports
  it gets the same window.

## Status light and on-screen messages

* **Status light** (optional): see [WIRING.md](WIRING.md) for the wiring and
  the colours. Settings › Status light.
* **On-screen messages**: during a RetroArch game (most consoles), the
  Recalbox shows the time left, the bonus time, an unknown badge, an access
  request… The Recalbox menu itself cannot show a message from another
  program: in the menu, the beeps and the light do the job. Settings ›
  On-screen messages during games.

## Sounds

| Sound | Meaning |
| --- | --- |
| 1 high beep | pairing mode armed (also the 5 and 1 minute warnings) |
| 2 rising beeps | badge paired, special card done |
| 1 medium beep | badge recognized without action (`action = none`) |
| no sound | a game starts: its loading screen is enough |
| 2 low beeps | erase mode armed |
| 2 falling low beeps | unknown badge or refused action |
| 3 falling beeps | time out (10 s to place the badge), end of play time |

The beeps are generated on the fly and played by `paplay` (PulseAudio) or
`aplay` (ALSA). Settings › Beeps turns them off.

## Commands (SSH)

```sh
RFID="sh /recalbox/share/system/rfid/rfidctl"

$RFID test              # hardware check (SPI, badge, button, frontend)
$RFID list              # saved pairings
$RFID add <UID> --current
$RFID add <UID> <system> <game> [name]
$RFID remove <UID>
$RFID export <file.csv>
$RFID import <file.csv> [--keep]
$RFID status            # service state (PID, badge, armed mode)
$RFID start|stop|restart
$RFID logs              # last 40 lines of the log
$RFID frontend          # can Recalbox start a game from a script?
$RFID self-update [URL] # update
$RFID simulate          # simulation (PC, no hardware)
$RFID config            # effective configuration
```

The identifier of a badge is shown by `rfidctl test`, in the page and in the
log, as `A1:B2:C3:D4` (`A1B2C3D4`, `a1-b2-c3-d4` and `A1 B2 C3 D4` are accepted
too).

## The CSV file

"Save the list" / "Restore a list" in the page, or `rfidctl export / import`:

```csv
uid;system;game;name;kind;action;params;limit_min
A1:B2:C3:D4;snes;Super Mario World.smc;Super Mario World;game;;;30
01:02:03:04:05:06:07;nes;Zelda.nes;Zelda;game;;;
0A:0B:0C:0D;;;Bonus +10 min;action;bonus;"{""minutes"": 10, ""period_h"": 24, ""uses"": 2}";
```

* Separator `;` (like Excel in French); `,` is accepted on import.
* `system`: short identifier of the Recalbox system (`snes`, `nes`,
  `megadrive`, `gba`…).
* `game`: path of the game **relative to the system folder**, extension
  included.
* `kind`, `action`, `params`, `limit_min`: optional; a file with only the first
  four columns (older versions) is still read.

## Configuration

File: `/recalbox/share/system/rfid/config.ini`. Almost everything is in the
Settings tab of the page; by hand, run `sh rfidctl restart` afterwards.

| Key | Default | Role |
| --- | --- | --- |
| `[general] log_level` | `INFO` | `DEBUG` to trace everything |
| `[rfid] spi_device` | `/dev/spidev0.0` | reader port (CE0) |
| `[rfid] spi_speed_hz` | `1000000` | set by the automatic tuning |
| `[rfid] reset_pin` | `25` | RST pin of the RC522 (`-1` if not wired) |
| `[rfid] poll_interval_ms` | `150` | how often the reader is read |
| `[rfid] same_tag_cooldown_s` | `2.5` | ignores re-reads of the same badge |
| `[rfid] rearm_absent_ms` | `1200` | **cartridge mode**: absence before the badge can act again |
| `[button] enabled` / `pin` | `1` / `17` | push button (BCM pin) |
| `[button] hold_press_s` | `3.0` | press that authorizes a device |
| `[button] arm_timeout_s` | `10` | time to place the badge |
| `[launch] action` | `launch` | `launch` = start the game; `none` = beep only |
| `[launch] ignore_when_game_running` | `1` | ignore badges during a game |
| `[launch] stop_on_remove` | `0` | quit the game when the badge is removed |
| `[time] default_limit_min` | `0` | play time of the badges without their own limit (0 = none) |
| `[screen] messages` | `1` | messages on the game screen (RetroArch) |
| `[screen] retroarch_port` | `55355` | RetroArch network command port |
| `[led] type` | `none` | `none`, `rgb` or `ws2812` |
| `[led] pin_red` / `pin_green` / `pin_blue` | `22` / `23` / `24` | RGB LED pins (BCM) |
| `[led] common` | `cathode` | `cathode` (to GND) or `anode` (to 3.3 V) |
| `[led] count` / `brightness` | `1` / `40` | programmable LEDs: number, brightness (%) |
| `[led] idle` | `1` | green when nothing happens (`0` = off at rest) |
| `[feedback] sound` | `1` | beeps |
| `[agent] enabled` / `port` | `1` / `8765` | management agent and page for phones |
| `[update] url` | empty | URL of the update ZIP |

## Backup and restore

* **Full backup**: Settings › Backup › **Download** gives one ZIP file with the
  badges, settings, card templates and frames, players, play time, statistics
  and reader calibration. The page password is never included. The ZIP also
  holds `statistics.csv` (the same table as the statistics export), readable
  as is; it is not needed to restore.
* **Restore**: Settings › Backup › **Restore…**. The whole file is checked
  first (known files only, readable content); the files it replaces are kept
  in `backups/` (the last five), then the reader service restarts.
* **Badges only**: "Save the list" / "Restore a list" in the Badges tab (CSV).
* At every save, the previous `tags.json` is kept as `tags.json.bak`.

## Log

```sh
$RFID logs
# or
cat /recalbox/share/system/rfid/logs/rfid.log
```

Example (the log itself is in French):

```
2026-01-01 12:00:00 [INFO   ] Lecteur RC522 pret (version 0x92)
2026-01-01 12:00:42 [INFO   ] Commande envoyee : START|snes|/recalbox/share/roms/snes/Super Mario World.smc
2026-01-01 12:00:42 [INFO   ] Temps de jeu limite a 30 min (Super Mario World)
2026-01-01 12:00:42 [INFO   ] Lancement de Super Mario World (snes / Super Mario World.smc)
```
