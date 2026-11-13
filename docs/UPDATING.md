# Updating

Badges, settings, card templates and play time quotas are **always kept**:
an update only replaces the program.

```
/recalbox/share/system/rfid/
├── app/                 <- program (replaced by every update)
├── web/                 <- page served to phones (replaced)
├── config.ini           <- YOUR settings (kept)
├── tags.json            <- YOUR badges (kept)
├── card-templates.json  <- YOUR card templates (kept)
├── playtime.json        <- bonus card uses (kept)
├── logs/
├── rfidctl
├── install.sh, uninstall.sh, installer.html, README*.md, CHANGELOG.md
└── VERSION              <- installed version
```

## Method 1 — one click from the page (recommended)

Open the latest `recalbox-rfid-installer.html`, tab **Updates** › **"Update to
X"**: the page sends the program it contains, the Recalbox installs it, the
service and the agent restart, and the page reconnects on its own. The
authorization survives the update (no button press needed).

The page warns when it is older than the Recalbox ("This page is older than the
Recalbox"): open the newest one.

## Method 2 — other ways, from the page

Tab **Updates** › "Other ways to update":

* **Send a ZIP file**: a release archive (`recalbox-rfid-X.Y.Z.zip`), sent from
  the computer;
* **Install from the share**: a newer `recalbox-rfid` folder copied into
  `\\RECALBOX\share`;
* **Install from this address**: the URL of a ZIP (a GitHub release, for
  example);
* **Reinstall the same version**: repairs an installation.

The ZIP must hold `install.sh` at its root or in a single sub-folder.

## Method 3 — copy a newer folder, then restart

Copy the folder of the new version into `\\RECALBOX\share` (the page's step 2
or the `.cmd` installer do it), then restart the Recalbox. At boot, the
permanent script compares the version on the share with the installed one: if
it is **newer**, it installs it. Same or older versions are ignored (no
downgrade). Log: `/recalbox/share/system/rfid/logs/auto-install.log`.

## Method 4 — SSH

```sh
# a folder copied to the share
ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --upgrade"
# a ZIP hosted online
ssh root@recalbox.local "sh /recalbox/share/system/rfid/rfidctl self-update https://example.com/recalbox-rfid.zip"
```

The ZIP is downloaded with `curl`, unpacked with `python3 -m zipfile`, then the
installer of the new version runs in `--upgrade` mode. To avoid typing the URL
again, set it in `config.ini`:

```ini
[update]
url = https://example.com/recalbox-rfid.zip
```

`rfidctl self-update` without an argument then uses it; without a configured
URL, it reinstalls the local version (repair).

## For developers: rebuild the page and the ZIP

After any change to a project file:

```sh
python tools/build_installer.py                       # dist/recalbox-rfid-installer.html
python tools/build_installer.py --zip dist/recalbox-rfid.zip
```

A test fails when the delivered page is not rebuilt. The GitHub workflow builds
both for every release (see [PUBLISHING.md](PUBLISHING.md)).

## Going back

Install the older version with method 2 or 4. The data stay compatible: the
format of `tags.json` is versioned (`"schema": 1`); entries added by newer
versions (special cards, time limits) are ignored by older ones with a line in
the log. Before a big update, keep a copy:

```sh
cp /recalbox/share/system/rfid/tags.json /recalbox/share/tags-backup.json
```

or use "Save the list" in the page.

## Checking what is installed

* Page: tab **Updates** (installed version, version of the running service).
* SSH:

  ```sh
  sh /recalbox/share/system/rfid/rfidctl version
  sh /recalbox/share/system/rfid/rfidctl status
  ```

## When it fails

* The installation log is in the page (Updates › Installation log) and in
  `logs/install.log`;
* `rfidctl logs`, or `logs/rfid.log`; when the service does not start,
  `logs/service.out` holds the output of the start attempt;
* running the installer again is safe (idempotent).
