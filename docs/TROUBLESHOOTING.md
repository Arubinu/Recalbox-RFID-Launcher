# Troubleshooting

Start with the page: the **Hardware** tab says in plain words what is wrong,
and **Test with a badge** checks the reader. Over SSH:

```sh
RFID="sh /recalbox/share/system/rfid/rfidctl"
$RFID status
$RFID logs
$RFID test
tail -f /recalbox/share/system/rfid/logs/rfid.log    # live, while placing a badge
```

---

## 1. The service does not start

| Check | Command / file |
| --- | --- |
| Is the startup script installed? | `ls -l /recalbox/share/userscripts/` |
| Does Python answer? | `python3 -c "print('ok')"` |
| Is the service already running? | `ps aux \| grep rfid` |
| Error at start? | `cat /recalbox/share/system/rfid/logs/service.out` |

The service is started by Recalbox **when the interface starts** (permanent
script `recalbox-rfid(permanent).py3`). After an installation, restart the
Recalbox, or use Updates › Service › Start in the page.

## 2. `/dev/spidev0.0` is missing

The SPI bus is not enabled.

**Recalbox 10** reads the line from `/boot/config.txt` (the file
`/boot/recalbox-user-config.txt` is not applied by this version). The installer
writes both, with a backup `.bak-rfid-launcher`. By hand:

```sh
grep -n "dtparam=spi" /boot/config.txt
mount -o remount,rw /boot
# add the line in the global section (before [pi3], [pi4]…)
grep -q '^dtparam=spi=on' /boot/config.txt || \
  sed -i 's/^dtparam=audio=on$/dtparam=audio=on\ndtparam=spi=on/' /boot/config.txt
mount -o remount,ro /boot
reboot
```

Or run the installer again (`sh /recalbox/share/system/rfid/install.sh`). After
the restart, `ls -l /dev/spidev0.0` must list `spidev0.0` **and** `spidev0.1`.

## 3. The reader is not detected

Symptoms: "Badge reader not found" in the page; `Version du MFRC522 : 0x00` or
`0xFF` in `rfidctl test`; `Lecteur RFID indisponible` in the log.

Check, in this order:

1. **3.3 V power** (pin 1 or 17), **never 5 V**.
2. **Common GND** between the module and the Pi.
3. **MISO / MOSI** not crossed (MISO pin 21, MOSI pin 19).
4. **SCK** pin 23, **SDA/SS** pin 24 (CE0).
5. **RST** pin 22 (GPIO25). Not wired: `reset_pin = -1` in `config.ini`.
6. The Dupont wires: a loose contact is the most frequent cause.
7. Hardware › **Automatic tuning** picks a bus speed the reader holds; or set
   `spi_speed_hz = 500000` by hand.

## 4. A badge is not read

**Hardware › Test with a badge** reads the reader for 5 seconds and tells the
three possible causes apart:

| What the test says | Meaning | What to do |
| --- | --- | --- |
| identifier shown | the badge is read, it was simply not paired | pair it (Badges tab) |
| "the badge answers but the full read fails" (ATQA code) | a 13.56 MHz badge, but an unusual one | note the ATQA code; the partial identifier is in the log |
| "no 13.56 MHz card seen", with a badge | the badge is not 13.56 MHz, or the reader sees nothing | test again **with a contactless bank card** |
| no card either with a bank card | the reader sees no card | antenna or wiring: section 3 |

* The badge must be **13.56 MHz ISO 14443-A** (MIFARE Classic, Ultralight,
  NTAG…). 125 kHz badges do not work.
* Hold it **within 3 cm**, flat, centred on the antenna. Metal nearby (or a
  badge glued on metal) reduces the range a lot. In a slot, keep the reader
  right behind the card.

## 5. The button does nothing

1. Wiring: button between **GPIO17 (pin 11)** and **GND (pin 9)**.
2. The Hardware tab shows whether the button is recognized.
3. The GPIO controllers of Recalbox must be off:
   `grep controllers.gpio.enabled /recalbox/share/system/recalbox.conf` → `0`
   (menu: Controllers › GPIO controllers › Off, then restart).
4. The button must be **momentary** (contacts close while pressed).
5. Another pin: `pin = 27` in `[button]`, wire to pin 13, restart the service.
6. The log must show `GPIO : backend RPi.GPIO`. A `/sys/class/gpio` backend with
   "Invalid argument" means an old version: update.

## 6. The game does not start

1. `$RFID frontend` must answer "disponible" (Recalbox 9 or later).
2. The game must have been *selected* when pairing, not a folder.
3. The log after placing the badge: `Commande envoyee : START|snes|...` means
   the command left. If the game still does not start, the frontend did not
   find it (game moved or renamed): pair the badge again.
4. A running game blocks the badges ("Do not interrupt a game in progress").
5. `Le frontend n'a pas pu etre contacte`: the service started before the
   interface; restart the service.

## 7. Play time, bonus cards, special cards

| Symptom | Cause / what to do |
| --- | --- |
| the game is not limited | the badge has `0` (never limited) or no limit with a general setting at 0: pencil of the badge, or Settings › Play time per game |
| no warning before the end | a 1-minute game only gets the end message; warnings come 5 and 1 minutes before |
| "Bonus card already used" | the uses of the period are spent; the counter starts again after the chosen period |
| the bonus card does nothing | no limited game running, and none ended in the last 15 minutes |
| the quota reset after a restart | without network, the Recalbox clock restarts in 1980: the uses are forgotten (the quota needs the network time) |
| the game was quit but the time was not counted as over | quitting from the emulator menu ends the limited session too (the bonus card can resume it) |
| random game: "no game found" | the console of the card has no game, or "only favourites" with no favourite |
| "Write the game into the badge" fails | "badge which cannot keep data": a clone that only gives its identifier; "protected": a MIFARE Classic with a custom key; "too small": an Ultralight and a very long file name |
| a portable card does nothing on another Recalbox | the game must be installed there with the same console folder and file name; the reader must be installed on the other Recalbox too |

## 8. No message on the TV

Messages are shown by **RetroArch**, during a game only:

* the Recalbox **menu** cannot show a message sent by another program (no
  such command in the frontend, checked on Recalbox 10.1): there, the beeps and
  the status light do the job;
* stand-alone emulators (Dolphin, PPSSPP, DOSBox…) ignore the command;
* Settings › On-screen messages during games must be on;
* RetroArch must keep its network commands (`network_cmd_enable = true`, set by
  Recalbox; port `[screen] retroarch_port`, 55355 by default);
* the language of the messages follows the Recalbox language.

## 9. The status light stays off

| Check | Detail |
| --- | --- |
| Settings › Status light | not "no light" |
| "Light on at rest" | off: the light only turns on to signal something |
| RGB LED | wiring and common leg (cathode to GND, anode to 3.3 V) match the setting; a resistor per colour (see [WIRING.md](WIRING.md)) |
| RGB LED, wrong colours | swap the pins in the advanced settings, or the common leg setting |
| Programmable LEDs | the Recalbox was **restarted** after choosing them (the second SPI bus is enabled at boot): `ls /dev/spidev1.0` must exist |
| Programmable LEDs flicker | shorter data wire, 330 Ω on DIN, or a level shifter |
| Log | `Voyant ... indisponible : ...` says why |

## 10. Pages and cards

| Symptom | Cause / what to do |
| --- | --- |
| "Find a game" finds nothing | the Recalbox 10 web API (port 81) answers the search; on Recalbox 9, the `gamelist.xml` files are read: games never scraped or without a `gamelist.xml` are not listed |
| no picture for a game | the game was not scraped (Recalbox menu › Scraper), or choose "My image" |
| no logo or console drawing | the Recalbox theme has none for this console (the default theme covers most) |
| the printed cards are too small / too big | print at **100 %** ("actual size"), never "fit to page"; check with a ruler: 85.6 mm wide |
| a template disappeared | templates saved while the page was offline stay on that device ("Saved on this device") |

## 11. The page does not connect

| Symptom | Likely cause |
| --- | --- |
| "The Recalbox does not answer" | the agent is not running (Recalbox not restarted since the copy, wrong address, missing agent userscript); try the IP address instead of `recalbox.local` |
| "The reader does not watch the button" | the service is stopped: Updates › Service › Start, or restart the Recalbox |
| "Another request is already in progress" | one request at a time (30 s): wait, then try again |
| "The button was not held in time" | **3 seconds** of continuous press, during the countdown |
| the page asks for an authorization again | the Recalbox restarted: hold the button 3 s |
| nothing happens from the online version | a browser forbids an `https://` page to open `ws://`: download the page, or use `http://recalbox.local:8765/` |

On the phone page (`http://<IP>:8765/`), use the IP address if `recalbox.local` does not resolve on the phone
(Android often lacks `.local` names).

**Never expose port 8765 on the Internet**: the agent can install code and
restart the Recalbox. For remote access, use a VPN.

### The agent does not start

1. `ls -l /recalbox/share/userscripts/` must list `recalbox-rfid(permanent).py3`
   **and** `recalbox-rfid-agent(permanent).py3`.
2. `cat /recalbox/share/system/rfid/logs/agent.log` must show "Agent WebSocket
   pret sur ws://…:8765".
3. Port taken? `netstat -ltn | grep 8765`; change `port` in `[agent]`.
4. `[agent] enabled = 1`.
5. Manual test: `python3 /recalbox/share/system/rfid/app/main.py agent --home
   /recalbox/share/system/rfid` (Ctrl+C to stop).

## 12. Copying from the page fails (Windows)

| Symptom | Cause / what to do |
| --- | --- |
| Windows offers to "Diagnose" on `\\RECALBOX` | *Public* network profile: switch it to *Private*, or use the IP address |
| `\\RECALBOX\share` asks for a user name | Windows 11 24H2+ blocks guest access: `root` / `recalboxroot`, or `Set-SmbClientConfiguration -EnableInsecureGuestLogons $true` (admin PowerShell) |
| "Wrong password" with `root` / `recalboxroot` | set a Samba password over SSH: `smbpasswd -a root` |
| the button does nothing | Firefox and Safari cannot write files: Edge or Chrome, or the `.cmd` installer |
| "no roms folder here" | choose `\\RECALBOX\share` (the folder holding `roms`, `system`, `bios`…) |
| "Windows protected your PC" on the `.cmd` | More info › Run anyway |

`net use` codes: 1326 credentials refused, 53 name not found (try the IP), 67
share not found (`system.samba.enabled=1`), 1272 guest access blocked, 1219 a
session already exists with other credentials (`net use \\RECALBOX\share
/delete` then `cmdkey /delete:RECALBOX`).

The **Windows diagnostic** (Connect › Advanced options) downloads a `.cmd` that
writes nothing and shows the resolved address, ports 445 and 8765, the share
access with each set of credentials, and the files in place: it is the report
to share when asking for help.

## 13. Two instances / erratic behaviour

The service takes a lock: a second instance stops at once ("Une autre instance
du service tourne deja"). `$RFID restart` cleans up.

## 14. Full reset

```sh
$RFID stop
cp /recalbox/share/system/rfid/tags.json /recalbox/share/tags-backup.json
sh /recalbox/share/system/rfid/uninstall.sh --keep-data
sh /recalbox/share/recalbox-rfid/install.sh --start
```

## 15. Where are the logs

| Log | Path |
| --- | --- |
| Reader service | `/recalbox/share/system/rfid/logs/rfid.log` |
| Management agent | `/recalbox/share/system/rfid/logs/agent.log` |
| Installations | `/recalbox/share/system/rfid/logs/install.log`, `auto-install.log` |
| Menu uninstall | `/recalbox/share/system/rfid/logs/uninstall.log` |
| Output of `rfidctl start` | `/recalbox/share/system/rfid/logs/service.out` |
| Recalbox frontend | `/recalbox/share/system/logs/frontend.log` |

The logs of the service are written in French.
