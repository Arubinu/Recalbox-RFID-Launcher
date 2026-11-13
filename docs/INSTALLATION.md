# Installation

The program is copied to the network share of the Recalbox, then installed by
the Recalbox itself. Allow 5 minutes.

## Requirements

* Recalbox **9 or later** (menu › System › Information shows the version);
  Recalbox 10 is recommended: the installation then runs from its menu, without
  a restart. Starting a game from a script does not exist before Recalbox 9.
* The **network share** enabled (Network › SMB share, on by default): this is
  how the program reaches the Recalbox.
* The reader and the button wired: see [WIRING.md](WIRING.md).
* For the SSH methods only: Network › SSH server › On. Default `root` password:
  `recalboxroot`.

---

## Method 1 — the page (recommended)

1. Open **`recalbox-rfid-installer.html`** (from the latest release, or
   `dist/recalbox-rfid-installer.html` in the repository) with **Edge or
   Chrome**, then choose **"Install for the first time"**.
2. **Wire**: the diagram is on screen.
3. **Copy**: click "Choose the Recalbox folder". The page copies the address
   `\\RECALBOX\share` to the clipboard: paste it in the window (Ctrl+V,
   Enter), then "Select folder" and accept the changes. The page writes:
   * `\\RECALBOX\share\recalbox-rfid\` (the whole program);
   * `\\RECALBOX\share\userscripts\recalbox-rfid-agent(permanent).py3` (starts
     the installation and the management agent at boot);
   * `\\RECALBOX\share\userscripts\manual\Install-RFID-reader.sh` and
     `Uninstall-RFID-reader.sh` (Recalbox 10 menu).

   The page remembers the folder: next time, no window opens.
4. **Run**:
   * **Recalbox 10**: with the controller, START › Advanced settings › User
     scripts › **Install-RFID-reader**. No restart needed.
   * **Recalbox 9**: restart the Recalbox; the installation runs during the
     boot.

   The page waits and moves on by itself. The Recalbox may restart once on
   its own: that is what enables the reader (SPI bus). The log is in
   `\\RECALBOX\share\system\rfid\logs\auto-install.log`.
5. **Authorize**: hold the case button for 3 seconds during the countdown. The
   badge management opens.

> The online version (GitHub Pages) can do steps 2 and 3, but a browser forbids
> an `https://` page to talk to a device of your network: it offers to download
> itself for the rest. See [PUBLISHING.md](PUBLISHING.md).

### If Windows does not open `\\RECALBOX\share`

* **Windows offers to "Diagnose"**: the connection is on a *Public* network,
  which hides the devices of your network. Settings › Network & Internet ›
  Wi-Fi or Ethernet › your network › Network profile type › **Private**. Or
  type the IP address of the Recalbox, e.g. `\\192.168.1.20\share` (START ›
  Network settings shows it).
* **Windows asks for a user name**: recent Windows versions (11 24H2 and later)
  block guest access to shares. Either sign in with `root` / `recalboxroot`
  ("Remember my credentials"), or allow guest access in an **administrator
  PowerShell**:

  ```powershell
  Set-SmbClientConfiguration -EnableInsecureGuestLogons $true
  ```

  If Windows remembered wrong credentials, remove them first:

  ```cmd
  net use \\RECALBOX\share /delete
  cmdkey /delete:RECALBOX
  ```

* `\\RECALBOX` alone (without `\share`) cannot be browsed: only the named
  share is exposed.
* **Nothing works**: use method 2.

## Method 2 — the Windows installer (`.cmd`)

In the page, step 2 › "It doesn't work? Use the Windows installer":

1. **Download the installer** (a small `.cmd` file holding the whole program).
2. **Double-click it**. If Windows shows "Windows protected your PC": More info
   › Run anyway. The script:
   * finds the Recalbox and connects to the share (`net use`: `root` /
     `recalboxroot`, then guest);
   * unpacks the embedded files and copies them (same files as method 1);
   * reopens the page at the "Run" step.
3. Go on with step 4 of method 1.

On `FAILED: share not reachable`, the script shows the error code and what to
check (IP address, password, guest access).

## Method 3 — by hand

1. Copy the `recalbox-rfid` folder (the one holding `install.sh`) into
   `\\RECALBOX\share`.
2. Copy `recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3` into
   `\\RECALBOX\share\userscripts\`.
3. Recalbox 10: copy the content of `recalbox-rfid\bootstrap\manual` into
   `\\RECALBOX\share\userscripts\manual\`, then run *Install-RFID-reader* from
   the menu. Recalbox 9: restart.
4. Open the page, "Manage my badges", and authorize with the button.

## Method 4 — SSH (Windows, macOS, Linux)

```sh
# 1. copy the folder (Windows: drop it into \\RECALBOX\share instead)
scp -r recalbox-rfid root@recalbox.local:/recalbox/share/
# 2. install and start
ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"
# 3. if asked (SPI just enabled), restart, then check
ssh root@recalbox.local "sh /recalbox/share/system/rfid/rfidctl test"
```

---

## After the installation: phones and tablets

The Recalbox now serves the management page itself:
`http://recalbox.local:8765/` (or `http://<IP>:8765/`). On a connected
computer, the phone button of the header shows a QR code. A phone is
authorized once with the 3 s press, like a computer.

## What the installer does

| Item | Detail |
| --- | --- |
| Program | `/recalbox/share/system/rfid/app` |
| Page for phones | `/recalbox/share/system/rfid/web/index.html` |
| Configuration | `/recalbox/share/system/rfid/config.ini` (created if missing, **never overwritten**) |
| Badges | `/recalbox/share/system/rfid/tags.json` (**never overwritten**) |
| Card templates, play time | `card-templates.json`, `playtime.json` (same folder) |
| Command | `sh /recalbox/share/system/rfid/rfidctl` |
| Startup | `/recalbox/share/userscripts/recalbox-rfid(permanent).py3` (reader service) and `recalbox-rfid-agent(permanent).py3` (management agent) |
| Recalbox 10 menu | `userscripts/manual/Install-RFID-reader.sh`, `Uninstall-RFID-reader.sh` |
| Logs | `/recalbox/share/system/rfid/logs/` (`rfid.log`, `agent.log`, `install.log`) |
| SPI bus | `dtparam=spi=on` in `/boot/recalbox-user-config.txt` and in the global section of `/boot/config.txt` (backup `.bak-rfid-launcher`) |
| Authorization | 3 s press on the case button; session secret in a private folder, never on the share |

Everything lives on the share: **nothing is written into the Recalbox system**
(except the SPI line of the boot configuration), so a Recalbox update keeps
the installation. After a major Recalbox upgrade, check that SPI is still
enabled (Hardware tab).

The installer is **idempotent**: running it again reinstalls cleanly and keeps
the configuration and the badges. It is also the update procedure.

## Installer options

```sh
sh install.sh                 # install / update
sh install.sh --start         # ... and start the service right away
sh install.sh --upgrade       # update (keeps everything)
sh install.sh --no-restart    # do not restart the service (used by the agent)
sh install.sh --no-spi        # do not touch the SPI configuration
sh install.sh --from-url URL  # install a ZIP hosted online
sh install.sh --uninstall     # uninstall
```

## Odd errors (`: not found`, `illegal option`)

The file has **Windows line endings (CRLF)**: Recalbox runs the scripts with
`/bin/sh`, which only accepts Unix line endings (LF). The page and the `.cmd`
installer write LF files. When copying by hand from a Git checkout, the
`.gitattributes` of the project already keeps `*.sh`, `*.py` and `*.py3` in LF.
To fix a file on the Recalbox:

```sh
sed -i 's/\r$//' /recalbox/share/recalbox-rfid/install.sh
```

## Enabling SPI by hand

If the installation could not write into `/boot`:

```sh
mount -o remount,rw /boot
echo "dtparam=spi=on" >> /boot/recalbox-user-config.txt
mount -o remount,ro /boot
reboot
```

Check: `ls -l /dev/spidev0.0` must exist.

## First full test

1. Hardware tab › "Test with a badge": the identifier of the badge shows up.
2. On the Recalbox, select a game.
3. Short press on the button (one high beep).
4. Place the badge (two rising beeps).
5. Place it again: the game starts.

## Uninstalling

* **Recalbox 10**: START › Advanced settings › User scripts ›
  **Uninstall-RFID-reader**. The badges and settings are kept, and
  *Install-RFID-reader* stays in the menu to reinstall in one click.
* **SSH**:

  ```sh
  ssh root@recalbox.local "sh /recalbox/share/system/rfid/uninstall.sh"
  ```

  Options: `--keep-data` keeps `config.ini`, `tags.json` and the templates;
  `--remove-spi` also removes the SPI lines (reader and status LEDs) from the
  boot configuration.
