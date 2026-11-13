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
* To withdraw every authorization: restart the Recalbox. To disable the agent:
  `enabled = 0` in `[agent]`.

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

## Printing the cards

Tab **Cards**: the size is the one of a bank card (CR80, 85.6 × 54 mm), at
300 dpi.

1. **Choose a game** (or "Create its card" from a badge or a search result):
   the page fetches its scraped picture, the **logo** and the **drawing of its
   console** from the Recalbox theme, and the main colour of the logo. **My
   image** uses your own picture instead (any size: it is fitted to the card).
2. **Choose a template**: Cartridge, Banner, Game box, Arcade, Minimal,
   Collection (with the console drawing), Picture only. **Landscape** or
   **Portrait**.
3. **Adjust each element** (Picture, Title, Logo, Console, Colours): touch it on
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
   saves one card as a PNG (for a print shop, for example).

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

* **Backup**: "Save the list" in the page (CSV), or copy
  `tags.json`, `config.ini`, `card-templates.json` and `playtime.json` from
  `\\RECALBOX\share\system\rfid`.
* **Restore**: "Restore a list", or copy the files back.
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
