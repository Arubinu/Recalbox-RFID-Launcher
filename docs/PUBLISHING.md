# Publishing on GitHub

Everything is ready in `.github/workflows/pages.yml`. On every push to `main` it runs the tests, builds the
single-file installer and publishes it on GitHub Pages. On a `v*` tag it also attaches the installer and the update
archive to a GitHub release.

## One-time setup

1. Create the repository on GitHub (the README links assume `Arubinu/recalbox-games-rf-launcher`; if the name differs,
   replace `arubinu.github.io/recalbox-games-rf-launcher` in the six `README*.md` files).
2. Push the code: `git push -u origin main`.
3. **Settings › Pages › Build and deployment › Source: "GitHub Actions"**.
4. The first run of the **Build and publish** workflow publishes the page at
   `https://<account>.github.io/<repository>/`.

## Repository page

* **About › Description**: One badge, one game: place an RFID card on a reader plugged into your Recalbox
  (Raspberry Pi + RC522) and the game starts, like a cartridge. Player cards with play time limits, printable
  cards, its own TV screen, all set up from a single web page. No dependency, 6 languages.
* **About › Website**: `https://<account>.github.io/<repository>/`
* **About › Topics**: `recalbox` `retrogaming` `raspberry-pi` `rfid` `rc522` `nfc` `emulationstation` `retroarch`
  `emulation` `game-launcher` `parental-controls` `kids` `cartridge` `python` `gpio`
* **Settings › General › Social preview**: upload `docs/images/social-preview.png` (1280×640).

## First release (1.0.0)

The tag `v1.0.0` is already in the repository. Push it after `main`:
`git push -u origin main && git push origin v1.0.0`. The **Build and publish** workflow then creates the
GitHub release **v1.0.0** with the page `recalbox-rfid-installer.html` and the archive `recalbox-rfid.zip`
attached: open it in **Releases**, write the notes (the `## [1.0.0]` part of `CHANGELOG.md`) and save.

Creating the release from the GitHub page instead (**Releases › Draft a new release**, new tag `v1.0.0` on
`main`) works too: the tag starts the same workflow, which attaches both files to that release a minute later.

## Releasing a version

1. Bump the version everywhere (`VERSION`, `app/rfid/__init__.py`, `install.sh`, `README.md`, a `## [x.y.z]` entry in
   `CHANGELOG.md`); `tests/test_version.py` checks they match.
2. `python tools/build_installer.py`, then commit (the test suite fails if `dist/` is stale).
3. Tag and push: `git tag v1.1.0 && git push origin v1.1.0`.

The release then holds:

| File | Use |
| --- | --- |
| `recalbox-rfid-installer.html` | the page to download and open on the computer |
| `recalbox-rfid.zip` | update archive: "Install from this address" in the page, or `rfidctl self-update <url>` |

A stable URL for the latest archive, to put in `config.ini` (`[update] url =`) or in the page:
`https://github.com/<account>/<repository>/releases/latest/download/recalbox-rfid.zip`.

## Why the online page cannot manage the Recalbox

GitHub Pages is served over `https://`, and browsers block any `ws://` connection from an `https://` page (mixed
content), so the online page cannot reach the agent on the local network. Serving it over plain `http://` is not a
fix either: the page would lose the File System Access API and the clipboard (both need a secure context), and
browsers increasingly restrict public sites from reaching private addresses. The agent also refuses every web
origin on purpose.

The online page therefore detects `https://` and shows a notice with a **"Download the page"** button. The wiring and
copy steps work online; connecting, authorizing and managing badges happen in the downloaded page (`file://` is a
secure context, and the agent accepts its `null` origin).
