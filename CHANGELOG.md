# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
semantic versioning. The current version is also in the `VERSION` file and shown
by `rfidctl version`.

## [2.10.0]

### Added — printable cards

* New **Cards** tab: design the card to put on a badge, at the size of a bank
  card (CR80, 85.6 × 54 mm, 300 dpi), landscape or portrait.
* Seven original templates (Cartridge, Banner, Game box, Arcade, Minimal,
  Collection, Picture only). For each game, the page fetches its scraped
  picture, the **logo** and the **drawing of its console** from the Recalbox
  theme (Recalbox 10 web API), and the main colour of the logo: every console
  gets its own look without any extra file. "My image" formats your own
  picture instead.
* Every element (picture, title, logo, console drawing) can be moved, resized
  and **rotated**: by dragging, with two fingers, with the mouse wheel, or with
  the controls (sliders, quarter turns). Fonts, text colour and outline, logo
  colour, card colour, rounded corners.
* A yellow band shows the **part sticking out of the slot** (top, bottom, left
  or right), to place the title and the logo; it is never printed.
* **Templates can be saved** and reused: they are stored on the Recalbox
  (`card-templates.json`), so every computer and phone finds them.
* **Print sheet**: ten cards per A4 page with cut lines; portrait cards are
  turned to fit. "Download the image" saves one card as a PNG.

### Added — the page on phones and tablets

* The agent serves the management page itself: `http://recalbox.local:8765/`.
  Nothing to install on the phone; it is authorized once with the 3 s press.
  The page layout was reviewed for small screens.
* On a connected computer, a header button shows the address and a **QR code**
  (generator built into the page).
* Security: only the page served by the agent itself is accepted (same origin),
  and only under a local name or an IP address (protection against DNS
  rebinding); pairing still requires the physical button.

### Added — badges without the TV

* **Find a game** (Badges tab): search the games of the Recalbox by name (accents
  ignored), filter by console, then pair a badge or create its card. Uses the
  Recalbox 10 web API, or the `gamelist.xml` files on Recalbox 9.
* Badges can be renamed, and get a time limit, from the page.

### Added — special cards and play time

* **Special cards**: random game (every console, one console, or favourites),
  bonus time, quit the game, turn off the Recalbox.
* **Play time**: a limit per badge, or a general one (Settings › Play time per
  game). Warnings 5 and 1 minute before the end, then the game is quit.
* **Bonus card**: adds minutes to a limited game, a chosen number of times per
  period (hour, 3 h, 12 h, day, week). Right after the end of a limited game, it
  starts the game again with the bonus time; in cartridge mode, swapping the
  game card for the bonus card quickly keeps the game running. Uses are kept in
  `playtime.json`.

### Added — status light and on-screen messages

* **Status light**: an RGB LED on three GPIO pins (common cathode or anode), or
  programmable WS2812/SK6812 LEDs on the second SPI bus (data on GPIO20, pin
  38; `dtoverlay=spi1-1cs` is added to the boot configuration when they are
  chosen). Ready, pairing, erasing, access request, end of play time, errors.
  See `docs/WIRING.md` (including how to avoid soldering resistors).
* **Messages on the game screen** through RetroArch network commands
  (`SHOW_MSG`): time left, bonus, unknown badge, access request, pairing…, in
  the Recalbox language. The Recalbox menu itself cannot show messages from
  another program (no such command in the frontend).

### Changed

* Documentation and changelog translated into English; the READMEs describe the
  new features.
* `main` now holds the redesigned page (merge of `refonte-ux`).
* `uninstall.sh --remove-spi` also removes the second SPI bus line.
* The CSV export carries the new fields (`kind`, `action`, `params`,
  `limit_min`); older files are still read.

### Fixed

* Sound setting: turning the beeps back on from the page now works without
  restarting the service.

## [2.9.0]

### Added — full installation from the page, without a restart (Recalbox 10)

* The page also drops `userscripts/manual/Install-RFID-reader.sh`. Recalbox 10
  lists this folder in **START → advanced settings → user scripts** and reads it
  again each time the menu opens: the installation is started with the
  controller, without a restart. The script starts the usual permanent script,
  detached (installation, service, agent); the Recalbox restarts only once, on
  its own, to enable the reader. Checked on Recalbox 10.1.1.
* **Uninstall from the menu**: `Uninstall-RFID-reader` removes the program, the
  startup scripts and the SPI line, stops the service and the agent, and keeps
  the badges, the settings and "Install-RFID-reader" (one-click reinstall).
  Checked on Recalbox 10.1.1.
* `install.sh` installs both scripts (and removes the old name
  `Installer-lecteur-RFID.sh`); `uninstall.sh` removes them (`--from-menu` keeps
  the install one).
* The `.cmd` installer copies them too and reopens the page directly at the
  "Run" step (`#etape=3`).
* On "Choose the Recalbox folder", the page copies `\\RECALBOX\share` to the
  clipboard and remembers the chosen folder: next time, the copy runs without a
  window.

### Added — publishing on GitHub

* `.github/workflows/pages.yml`: tests, build of the page and of the update
  archive (`tools/build_installer.py --zip`), publication on GitHub Pages and
  release assets for `v*` tags. See `docs/PUBLISHING.md`.
* The page served over `https://` detects it: the browser blocks the connection
  to the Recalbox there, so it offers to download itself.
* One README per language (English by default, French, German, Spanish,
  Italian, Portuguese).

### Changed — new interface

* **4-step installation wizard** (Wire, Copy, Run, Authorize): the page waits for
  the Recalbox on its own, then asks for the 3 s press. No more technical choices.
* **A single "Authorize this computer" screen** everywhere (installation,
  connection, reconnection after a restart), with a visual countdown.
* **Badges**: the game selected on the Recalbox in large, a "Pair a badge with
  this game" button, the countdown, and a clear message at the end (paired, or
  time out). Readable list (game name, console name, number of launches),
  search from 6 badges on.
* **Hardware**: a list of checks in plain words, with the action to take; a
  problem also shows at the top of the dashboard.
* **Updates**: "Update to X" sends the program held by the page itself; no ZIP
  file needed any more.
* Messages and confirmations built into the page (no more `alert` windows).
* Every displayed string is translated (6 languages); mobile layout reviewed
  (header, tabs).
* **Settings**: plain labels and help, units in the title; technical settings
  folded into "Advanced settings".
* Help for Windows offering to "Diagnose" `\\RECALBOX`: *Public* network profile
  (switch to *Private*), or IP address.
* Files renamed in English (`docs/WIRING.md`, `TROUBLESHOOTING.md`,
  `UPDATING.md`, `USAGE.md`, `docs/wiring.svg`, `tools/build_wiring.py`) and all
  code comments translated into English.

### Fixed

* `uninstall.sh --remove-spi` failed on a read-only `/boot` (and stopped before
  removing the program); it did not remove the line added to `/boot/config.txt`
  either. It now remounts `/boot` for the change and only removes the lines
  added by the installation.
* `uninstall.sh` only stopped the service when `rfidctl` was executable (never
  the case on the exFAT share) and left the agent running.
* Documentation: `rfidctl` is called with `sh` (the exFAT share does not keep
  the execute permission).
* **Sending a ZIP from the page never got an answer**: Chromium splits
  WebSocket messages above 64 KB and the agent did not reassemble continuation
  frames. The agent reassembles them, and the page sends 32 KB chunks
  (compatible with agents already installed).
* `install.sh` did not write the SPI line when the bus was already live: after an
  uninstall followed by a reinstall without a restart, the reader was disabled
  at the next boot. The line is always written; a restart is only asked when the
  bus is not live yet.

## [2.8.2]

### Fixed

* **The badge left at the end of the automatic tuning no longer starts the
  game.** The measurement queries the reader itself: the badge left in place had
  never been "seen" by the service loop and, once the measurement was over, it
  looked like a new badge — hence a game starting right after the calibration.
  The present badge is now **adopted without acting** (remove it and put it back
  to start something).
* Same fix after the **reader test** and after a **reset** of the settings,
  which also reopen the reader.
* An armed mode (pairing, erasing) keeps priority: the badge already in place
  can still be presented for the requested action.

## [2.8.1]

### Fixed

* **The knob of the switches of the Options tab is now centred** in its track.
  It stuck to the bottom of the button (2 px at the top, 0 at the bottom); it is
  now 2 px from both edges, on and off, on computer and phone.

## [2.8.0]

### Added — "Tune the reader automatically"

**Hardware** tab: the service measures the reader, then sets three values on
its own. No more trial and error: the hardware gives the numbers.

* `rfid.spi_speed_hz` — the fastest bus speed that reads the version register
  **40 times in a row without an error** (8, 4, 2, 1 MHz, then 500 kHz);
* `rfid.poll_interval_ms` — the read rate, based on the **real duration of a
  read** (duration + 30 ms, within 60–500 ms);
* `rfid.rearm_absent_ms` — the absence delay, based on the **latency measured
  on removal** (× 1.5, within 1–4 s).

Guided sequence (≈ 30 seconds): *place a badge* → *leave it* → *remove it* →
*put it back*, with a progress bar, a step number and a **Stop** button. The
measurement runs **in the service** (sole owner of the SPI bus): the page only
displays, and can be closed without interrupting it.

Plain report: bus speed, read interval, absence delay, duration of a read,
**REQA / WUPA presence**, removal latency, re-placing latency and identifier
read.

### Security

* **Nothing is written when a step fails** (no badge, unreadable badge, missing
  removal or re-placing, silent reader): a message says why and the settings
  stay untouched.
* The values from before the measurement are kept in `calibration-backup.json`,
  and the **Reset** button restores the three default values (1 MHz, 150 ms,
  1.2 s).
* If the measured speed does not hold when the reader is reopened, the service
  **goes back to 1 MHz on its own** and logs it.
* The agent refuses the measurement when the service is not started or still
  runs a version older than the page.

## [2.7.6]

### Fixed — a placed badge is never mistaken for a removed one again

Two symptoms, one cause: **the presence of a badge was tested by a call that
always failed**. The service believed the badge removed one second after each
read, which restarted the game on its own and declared "badge removed" right
after a launch (so without stopping anything).

* `tag_present()` is now exposed by the reader and works:
  * **REQA, then WUPA.** A badge that has just been selected no longer answers
    REQA: asking REQA alone made a perfectly placed badge look removed. This was
    the cause of the game restarting on its own.
  * **field cycle as a last resort** for stuck clones;
  * **`None` when the reader does not answer**: a silent bus does not prove a
    badge was removed, so nothing is concluded (before, an error meant
    "absent").
* The service no longer infers an absence from a failed read or one filtered by
  the debounce: only an **absence confirmed by the reader** (REQA and WUPA
  without answer, three times, at least 2 seconds in a row) releases the lock.
* **3 seconds of grace** after an action: a hiccup while the emulator starts can
  no longer undo the launch.

### Fixed — "quit the game when the badge is removed"

* Stopping the game waits until **the emulator really runs** (up to 6 s): at the
  time of removal, the game may still be starting. No more misleading "game
  stopped" while nothing was stopped.
* Stopping never blocks the badge reading or the button: the request is
  remembered and handled by the service loop.
* `EmulationStation` is still never targeted: only the emulator gets `SIGTERM`,
  then `SIGKILL` if it resists.

## [2.7.5]

### Added

* **An "Options" tab**, to set everything from the page, without opening a
  file: action on a paired badge, launch during a game, stopping the game on
  removal, time to place the badge, press that authorizes a browser, read
  interval, debounce of the same badge, absence before a new scan, SPI bus
  speed, beeps and log level.
  * the page holds **no hard-coded list of settings**: the agent describes them
    (`config.get`) and saves them (`config.set`); adding an option to the
    service shows it in the interface;
  * saving **keeps the comments** of `config.ini` and the service **reads its
    configuration again at once** (SIGHUP): no restart, no interruption of the
    badge reading;
  * unsaved changes are announced and **survive a tab change**; "Cancel" goes
    back to the values of the Recalbox;
  * every value is **validated by the service** (bounds, choices, yes/no): a
    refused value writes nothing.

### Added — start with a badge, quit by removing it

* New option `[launch] stop_on_remove` (off by default): when the badge that
  started the game leaves the reader, the game is stopped and the Recalbox goes
  back to its menu. The emulator first gets a clean stop (`SIGTERM`), then a
  forced one if it resists (`SIGKILL`); **EmulationStation is never targeted**,
  which gives exactly the return to the menu of a normal game exit.
* Emulators are detected by **program name**, no longer by the whole command
  line: no unrelated system process can be stopped (the word "service" contains
  "vice", for example).

### Fixed

* **The game no longer restarts while the badge stays on the reader.** A placed
  badge can no longer be taken for a removed one: the absence must be seen
  **three times in a row** and last longer than the re-arm delay, any positive
  read resetting the counter.
* `hold_press_s` (press that authorizes a browser) finally appears in the
  delivered `config.ini`: it could be set but was missing from the file, so it
  was invisible.

## [2.7.4]

### Added

* **Quiet reconnection on load.** When an authorization was already given
  (session secret remembered by the browser), the page **tests the connection in
  the background** as soon as it opens, without waiting for a click:
  * success (the normal case, including after an update or a service restart,
    since the secret survives) → **straight to the dashboard**, in ~0.2 s on
    the local network;
  * failure (Recalbox fully restarted, authorization lost) → **nothing shows**:
    the page stays on its screen, without a sticky banner.
* The attempt is abandoned after 2.5 s and never blocks the display.

## [2.7.3]

### Changed

* **Without an explicit choice, the system language decides.** The page reads the
  preference list of the browser (`navigator.languages`, which follows the OS
  language) and keeps the **first available language**: a German Windows opens
  the page in German. When no language of the list is available, English is
  used; as a last resort, French (source language).
* The page also follows a **change of the system language** live
  (`languagechange`) as long as no choice was made.
* **Long press on the language button**: forgets the choice and goes back to the
  system language (like the long press of the theme button).

## [2.7.2]

### Changed

* **No more beep when a game starts.** The game starts on screen, that is the
  confirmation: the beep added nothing to the frontend sound. Beeps remain for
  what cannot be seen — pairing, unknown badge, time out, erasing.

## [2.7.1]

### Added

* **The six Recalbox languages we can translate properly**: French, English,
  **German, Spanish, Italian and Portuguese** — one file per language
  (`i18n/de.json`, `es.json`, `it.json`, `pt.json`). The header button cycles
  through the six; its tooltip gives the language name.
* Basque, Turkish and Chinese are **not** shipped: an approximate translation
  would be worse than French. The mechanism is ready: dropping `i18n/eu.json`
  (or `tr`, `zh`) is enough, the page offers it automatically.

## [2.7.0]

### Added

* **Multilingual interface.** A header button shows the current language in two
  letters (`FR`, `EN`) and switches to the next one with a click. The language
  first follows the browser, then the choice is remembered.
  * each language is an `i18n/<code>.json` file (key = French text, value =
    translation), compiled into the page by `tools/build_installer.py` — the page
    stays a single file, without network;
  * a text without translation stays in French: a language can be added
    progressively.

### Changed

* **The delivered file no longer carries the version number**:
  `dist/recalbox-rfid-installer.html`. The version is still shown in the page and
  in `VERSION`.

## [2.6.9]

### Fixed

* **Pairing a badge no longer starts the game.** Pairing started the game at once
  (`[launch] launch_after_bind = 1`), which surprises when you only meant to
  assign a game. Saving now does only that — two beeps and the badge is paired;
  the game starts at the **next scan**.
* The `launch_after_bind` setting is removed: a value left at `1` by an earlier
  version is simply ignored.

## [2.6.8]

### Changed

* **The 3-second press validates at the 3rd second**, without releasing the
  button. The gesture fires the moment the duration is reached (confirmation
  beep), and the following release triggers nothing else.
* The short press is still read on release (so the two gestures never both
  fire), and the log notes the duration.

## [2.6.7]

### Changed

* **Two gestures only, and the action on release.** Acting on contact was a
  mistake: a held press triggered both the short and the long press. Gestures
  are read **on release** again:
  * **short press** → pair the selected game (10 s window);
  * **3-second press** → authorize a browser.
* **The "long" gesture (2 s) that armed erasing is removed**: pairing a known
  badge again overwrites its game, and erasing stays in the interface.
* **The interface follows events within one second** (refresh from 2 s to 1 s)
  and shows "Ready: place the badge on the reader (N s)" during the window.
* The beeps are documented: one high beep when armed, two rising beeps after
  pairing, two low ones when refused, three falling ones on time out.

## [2.6.6]

### Fixed

* **A badge left on the reader became invisible.** The driver ended each read
  with a `HALT`; some clone badges do not wake up after a `HALT` (they ignore
  `WUPA`) and stay silent until they leave the field. The driver now **turns the
  field off and on** (4 ms): every card goes back to `IDLE`.

### Changed

* **Arming a mode forgets the badge already in place**: after an erase, the
  same badge can be paired again without moving it away from the reader.
* **The displayed game is always shown in the interface.** After a game, the
  frontend keeps `State=playing` on the game page: the page showed "none". The
  display now tolerates this state (badge launches still start nothing during a
  game).

## [2.6.5]

### Fixed (the game did not start: "Couldn't find game")

* **The launch now sends the full path of the game**, no longer its file name.
  Checked on the machine: the Recalbox 10 frontend answers `Couldn't find game`
  to the name alone, and `Starting game` to the full path — the one the frontend
  itself publishes in `/tmp/es_state.inf`. The frame becomes
  `START|<system>|<full path>`.
  * badges already paired work: their `path` was saved when pairing;
  * an old entry without a path falls back to the file name;
  * manual add and CSV import rebuild the path (`/recalbox/share/roms/...` then
    `/recalbox/share_init/roms/...`).
* **Games of the read-only base no longer trigger a warning**: a path under
  `/recalbox/share_init/roms/` is perfectly normal.

## [2.6.4]

### Fixed (the displayed game was not recognized when pairing)

* **Pairing works when the frontend shows a game page.** The frontend sometimes
  leaves `State=playing` while no game runs; the "game running" filter also
  applied to pairing. It now only applies to **badge launches**.
* **Frontend keys tolerated**: `SystemId` / `System` / `SystemName` and
  `GamePath` / `Path` / `File` / `RomPath`; folders are also recognized by
  `Type=folder`.
* **The log says why**: "No game selected in Recalbox (State='playing',
  SystemId='snes', GamePath='…')".
* `status.json` now holds a snapshot of `/tmp/es_state.inf`.

## [2.6.3]

### Added (badges that never answer the selection)

* **"Stable anticollision" fallback**: some clone badges answer `REQA` and the
  anticollision but stay silent at selection. As only the **identifier** is
  needed, the driver now accepts the anticollision frame as identifier **after
  three identical reads**.
* The reader test announces this case.

## [2.6.2]

### Fixed

* **The third selection strategy was wired wrong**: `TxCRCEn` is bit **7** (0x80)
  of `TxModeReg`, not bit 4. Fixed, and the simulator now adds the CRC itself
  when this bit is set, so the test really covers this variant.

## [2.6.1]

### Fixed (badges that answer but stay silent at selection)

* The driver now tries **several selection strategies**:
  1. BCC **sent back by the card** (clones often compare that one);
  2. BCC **recomputed** from the identifier (real cards recompute);
  3. the same with the **CRC added by the coprocessor** (`TxCRCEn`).
  Each attempt is replayed after a `REQA` then a `WUPA`.
* The test trace names each step and gives the **winning strategy**.
* Simulator: it now checks the BCC of the selection like a real card.

## [2.6.0]

### Added

* **Light and dark themes.** The page follows the system theme until a choice is
  made; a **sun / moon** button keeps the choice. The switch is animated by a
  circle starting from the button (View Transitions API). **Long press**: back
  to the system theme.

### Changed

* **The wiring diagram follows the theme** (CSS variables). `docs/wiring.svg`
  carries its own style sheet and follows `prefers-color-scheme`.

## [2.5.6]

### Fixed (real cause of unreadable badges)

* **The CRC_A of the selection frame is now computed in software**
  (`crc_a_software`, polynomial 0x8408, init 0x6363) instead of depending on the
  MFRC522 coprocessor.
* The trace now records frames **without answer** too.

### Changed

* **Warning banner when the page and the Recalbox do not have the same version.**

## [2.5.5]

### Fixed (badges seen by the reader but without identifier)

* **BCC recomputed for the selection**; **WUPA as a fallback of REQA**; **a
  non-empty answer is no longer dropped** because of an error flag.
* **The reader test now shows the exchanged frames**.

## [2.5.4]

### Fixed

* **After "Install / update", the service kept running the old code.** The
  service is now restarted right after the installation.

## [2.5.3]

### Added

* **Wiring diagram, as a picture**, generated by `python tools/build_wiring.py`:
  in the Hardware tab, in the README and in `docs/WIRING.md`.

### Fixed

* The displayed version was the one of the Recalbox, not of the page: both are
  now shown separately.
* The "connection lost" banner offers **"Authorize this computer"** when the
  session secret is gone (full restart).
* "The reader did not answer the test" is replaced by the real cause when the
  service runs an older version than the agent.

## [2.5.2]

### Fixed

* **No more useless installation.** The agent compares the three versions (disk,
  share folder, running service): same versions → "already up to date", nothing
  is touched; **"Reinstall anyway"** forces it.

### Changed

* **A service restart or an update no longer asks for the 3-second press.** The
  session secret is kept in the private folder (`0600`, off the share, cleared
  with `/tmp` at boot). Only a **full restart of the Recalbox** renews it.

## [2.5.1]

### Added

* **"Test with a badge"** in the Hardware tab: 5 seconds of reading and a clear
  answer (badge read, badge answers but the read fails, no card seen — try a
  contactless bank card).
* Agent command **`reader.test`**.

## [2.5.0]

### Security

* **No token on disk any more.** The agent draws a **session secret in memory**;
  nothing is written in `system/rfid/`. The `token.txt` and `paired.ok` files of
  earlier versions are removed at agent start.
* **Authorization by a physical 3-second press only.**
* **The agent `pair` command and the `pair-request` file are removed.**

### Changed

* The browser remembers the authorization (localStorage).
* The agent only listens to the local network (port 8765) and refuses web
  origins other than a local page opened as `file://`.

## [2.4.0]

### Changed

* **Pairing window reduced to 10 seconds** (`[button] arm_timeout_s`).
* **3-second press**: only confirms a pairing request of the interface.
* **More beeps**: a distinct signal for a badge recognized without action, and
  for an erase.

### Added

* **"Cartridge" mode**: a badge left on the reader acts **only once**; remove it
  for `[rfid] rearm_absent_ms` to scan it again.
* **`[launch] action`**: `launch` (default) or `none` (confirmation beep only).

## [2.3.1]

### Fixed

* **No more ghost disconnection messages** after a page refresh or a successful
  connection.

## [2.3.0]

### Fixed (Recalbox 10.1.1 on Raspberry Pi 3, checked on the machine)

* **The SPI bus was never enabled.** The line is now written **directly into
  `/boot/config.txt`**, in the global section, with a `.bak-rfid-launcher` backup
  and a temporary read-write remount of `/boot`.
* **The push button was not recognized** ("cannot export pin 17: Invalid
  argument"). The GPIO backend now changes its working directory to a writable
  folder during initialization: `RPi.GPIO` works and the internal pull-up is
  available.

### Added

* Agent command **`diag`** (authenticated, read-only): Recalbox version, model,
  `/boot/config.txt`, `/dev/spidev*`, GPIO, `dmesg`, mount points.

## [2.2.0]

### Fixed

* **"Install / update" updated nothing**: the agent now picks the project folder
  **on the share** when its version is greater or equal, and never downgrades.

### Added

* Agent command **`diag`** (first version).

## [2.1.0]

### Added

* **Connection losses and returns handled**, especially during a Recalbox
  restart: the dashboard stays, greyed out, with a status banner, automatic
  reconnection, and an announced return.

## [2.0.2]

### Changed

* The "Connect" button spans the full width of the card.

## [2.0.1]

### Changed

* The "Last saved connection" line is removed from the connection screen.

## [2.0.0]

### Added

* **Pairing confirmed physically with the button**: the page drops a request
  (one at a time, 30 seconds), the Recalbox waits for a **3-second press**, and
  the page exchanges the grant for the token, **once**.
* **Protection against request races**, and a press started **before** the
  request is refused.
* Agent commands `pair.request` / `pair.check` / `pair.cancel`, local network
  only.

## [1.9.2]

### Changed

* Connection screen: the "Connect" button is right-aligned; the token file import
  becomes an icon in the token field.

## [1.9.1]

### Changed

* **Neutral buttons, hierarchy by size and not by colour**; action bars in the
  tabs.

## [1.9.0]

### Changed

* **Interface redesign: a choice, then screens, without scrolling**: two tiles
  (*Install on the Recalbox* or *Manage my badges*), one screen per path, a
  tabbed dashboard (Badges, Hardware, Maintenance), a one-sentence verdict with
  the action to take.

## [1.8.3]

### Fixed (Recalbox 10: failed installation and stopped service)

* **`/boot` is read-only on Recalbox 9/10**: `install.sh` now remounts it
  read-write for the SPI line, and warns and goes on instead of aborting.
* **The startup script starts the service even when the installation returns
  an error.**

## [1.8.2]

### Fixed

* **`robocopy` failed silently on the Recalbox share** (Samba refuses to change
  folder attributes, robocopy gave up… with code 0). Copies now use
  `/DCOPY:D /COPY:D`, success is checked by the presence of the files, and
  `xcopy` is tried as a fallback.

## [1.8.1]

### Fixed

* **The failure message tells the two causes apart** (agent not started /
  pairing window closed).

### Added

* **Pairing request by file**, the `.cmd` waits for the agent up to 30 s, and the
  diagnostic reads the Recalbox logs from the share.

## [1.8.0]

### Added

* **Automatic pairing: no more token to copy.** At first boot after the
  installation, the agent opens a 15-minute pairing window; local network only.

## [1.7.3]

### Added

* The token is checked before connecting; three automatic attempts; actionable
  failure messages.

## [1.7.2]

### Fixed

* **Step 1 of the `.cmd` can no longer hang**: one PowerShell call resolves the
  IPv4 address and tests port 445 within 1.5 s; attempts use the IP address.

## [1.7.1]

### Added

* **"Run a diagnostic"**: the page generates `diagnostic-recalbox.cmd`, a
  readable report (name and IP, ports 445 and 8765, share access, files in
  place). It changes nothing.

## [1.7.0]

### Changed

* **Complete redesign of `installer.html`** for people who know little about
  computers: three numbered steps, plain vocabulary, rare actions folded away,
  new visual style.

## [1.6.3]

### Fixed

* **Copy of the startup script: four methods in cascade**, each followed by a
  presence check.

## [1.6.2]

### Fixed

* The copy of the startup script uses `robocopy` and checks the result.

### Changed

* The "`root` without password" attempt comes 2nd.

## [1.6.1]

### Fixed

* **The `.cmd` no longer hangs at "1/4 Connecting to the share"**: `net use` runs
  with `<nul`, so a hidden Windows question fails instead of waiting.

## [1.6.0]

### Added

* **Stand-alone `.cmd` installer, without any dialog box**: connects to the
  share, unpacks the embedded files and copies them.
* **Automatic installation at boot** and **automatic update** (newer folder on
  the share + restart).

## [1.5.1]

### Added

* `acces-recalbox.cmd` becomes a diagnostic (`net use` error codes explained).

### Documented

* "Wrong password" with `root` / `recalboxroot`: `smbpasswd -a root`.

## [1.5.0]

### Added

* **"Connect" reads the token from the share by itself**; a button generates an
  `acces-recalbox.cmd` to give Windows access to the share.

## [1.4.1]

### Fixed / documented

* **`\\RECALBOX\share` asks for a user name**: Windows 11 24H2+ refuses guest
  sessions; use `root` / `recalboxroot`, or allow insecure guest logons.

## [1.4.0]

### Added

* **Single self-contained installer**: the page holds the content of every file
  to copy; **direct copy to `\\RECALBOX\share`** from the page (File System Access
  API, Edge and Chrome); generator `tools/build_installer.py`.

## [1.3.0]

### Changed

* **No more interface hosted on the Recalbox**: management goes through a
  token-protected **WebSocket agent** and a stand-alone `installer.html` opened on
  the PC.

### Removed

* `app/rfid/webui.py`, `app/web/index.html`, the `rfidctl web` command.

## [1.2.0]

### Added

* **Automatic installation and update at boot**: copy the folder to the share
  and restart.

## [1.1.0]

### Added

* **Web interface** (`http://recalbox.local:8080`): install, update, restart,
  hardware state, badges, CSV, logs. Installation without SSH.

## [1.0.0]

First publishable version.

### Added

* Reading of MFRC522 RFID badges (RC522 / nf-SL001) on the SPI bus of the
  Raspberry Pi, in pure Python (no package to install).
* Launch of the paired game through the official UDP command of the Recalbox
  frontend (`START|system|game`, port 1337), without changing the OS.
* Badge ↔ game database in `tags.json` (atomic writes, automatic backup,
  CSV import/export).
* Push button with internal pull-up (no resistor).
* Beeps (generated locally, played by `paplay` or `aplay`).
* Service started by Recalbox at boot (permanent user script), with a lock
  against duplicates and configuration reload (SIGHUP).
* Idempotent installer, update by copied folder or online ZIP, uninstall.
* `rfidctl test` diagnostic, PC simulation mode and unit tests with an MFRC522
  simulator at the SPI level.
* Documentation: wiring, installation, usage, update, troubleshooting.

### Notes

* Recalbox **9** minimum to start games (the "UDPCommand" thread of the frontend
  does not exist before).
