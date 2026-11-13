#!/usr/bin/env python3
"""Builds a self-contained HTML installer (embedded files).

The output file (`dist/recalbox-rfid-installer.html`) holds everything: the
management page **and** the content of the files to copy to the Recalbox. It
no longer depends on any other file of the project.

How it works in the browser (Edge or Chrome):

1. the page asks the user to pick ``\\\\RECALBOX\\share`` (File System Access API);
2. it creates ``recalbox-rfid/`` and the startup script in ``userscripts/``;
3. it also drops the menu scripts in ``userscripts/manual/``: on Recalbox 10,
   "Install-RFID-reader" is run from the menu (START > Advanced settings >
   User scripts), without a reboot; on Recalbox 9, the box is rebooted;
4. the same page waits for the WebSocket agent, then asks for the 3 s press.

Run this script again after any change to a project file:

    python tools/build_installer.py
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Folder created on the share.
PROJECT_NAME = "recalbox-rfid"

#: Permanent script copied into ``userscripts/``.
USERSCRIPT = "bootstrap/recalbox-rfid-agent(permanent).py3"

#: Scripts run from the Recalbox 10 menu (``userscripts/manual/``): install
#: without a reboot, and uninstall (badges and settings are kept).
MENUSCRIPTS = (
    "bootstrap/manual/Install-RFID-reader.sh",
    "bootstrap/manual/Uninstall-RFID-reader.sh",
)

#: Root files needed on the Recalbox (README.md and README.<code>.md are added
#: by collect_files).
ROOT_FILES = (
    "install.sh",
    "uninstall.sh",
    "VERSION",
    "CHANGELOG.md",
    "installer.html",  # "folder" page copied to the Recalbox and into the .cmd installer
)

#: Embedded folders (tests are useless on the Recalbox).
DIRECTORIES = ("app", "userscript", "bootstrap", "docs")

#: Source page (the generated file is this page + the embedded content).
HTML_SOURCE = "installer.html"

#: Translations folder: one JSON file per language (2-letter code).
I18N_DIR = "i18n"

#: Reference language: the page texts are written in French.
LANGUE_SOURCE = "fr"

#: Name of the delivered file (no version number).
DIST_NAME = "recalbox-rfid-installer.html"

#: Page served by the agent (http://recalbox.local:8765/): translations, no payload.
WEB_PAGE = "web/index.html"

#: Insertion point of the embedded content.
MARKER = "<body>"

EXCLUDED_SUFFIXES = (".pyc", ".pyo")


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def collect_files() -> dict:
    """Returns {relative posix path: binary content}, sorted."""
    files = {}
    for name in ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            files[name] = path.read_bytes()
    for path in sorted(ROOT.glob("README*.md")):
        files[path.name] = path.read_bytes()
    for directory in DIRECTORIES:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix in EXCLUDED_SUFFIXES:
                continue
            relative = path.relative_to(ROOT).as_posix()
            files[relative] = path.read_bytes()
    # Management page served by the agent to phones (no embedded files).
    files[WEB_PAGE] = build_html(with_payload=False).encode("utf-8")
    return dict(sorted(files.items()))


def build_payload(files: dict = None) -> dict:
    files = files if files is not None else collect_files()
    return {
        "project": PROJECT_NAME,
        "version": version(),
        "userscript": USERSCRIPT,
        "menuscripts": list(MENUSCRIPTS),
        "files": {
            path: base64.b64encode(content).decode("ascii") for path, content in files.items()
        },
    }


def collect_languages() -> dict:
    """Loads ``i18n/<code>.json``: {code: {source text: translation}}."""
    folder = ROOT / I18N_DIR
    languages = {}
    if not folder.is_dir():
        return languages
    for path in sorted(folder.glob("*.json")):
        code = path.stem.lower()
        if len(code) != 2:
            continue
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit("%s illisible : %s" % (path, exc))
        if not isinstance(content, dict):
            raise SystemExit("%s doit contenir un objet JSON" % path)
        languages[code] = content
    return languages


def build_html(payload: dict = None, with_payload: bool = True) -> str:
    if with_payload:
        payload = payload if payload is not None else build_payload()
    source_path = ROOT / HTML_SOURCE
    if not source_path.is_file():
        raise SystemExit("%s introuvable" % source_path)
    source = source_path.read_text(encoding="utf-8")
    if MARKER not in source:
        raise SystemExit("balise %s introuvable dans %s" % (MARKER, HTML_SOURCE))
    html = source
    if with_payload:
        encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        # The content is base64: it cannot contain "</script>".
        tag = '<script id="rfid-payload" type="application/json">%s</script>' % encoded
        html = source.replace(MARKER, MARKER + "\n" + tag, 1)

    languages = collect_languages()
    if languages:
        translations = json.dumps(
            {"source": LANGUE_SOURCE, "langues": languages},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        block = '<script id="rfid-i18n" type="application/json">%s</script>' % translations
        html = html.replace(MARKER, MARKER + "\n" + block, 1)
    return html


def build_zip(path: Path, files: dict = None) -> int:
    """Writes the update archive (``recalbox-rfid/...``) used by the agent's
    "install from a URL" and attached to each GitHub release."""
    files = files if files is not None else collect_files()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for relative, content in files.items():
            # Fixed date: the archive only changes when the files change.
            info = zipfile.ZipInfo(PROJECT_NAME + "/" + relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, content)
    return len(files)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", "-o", help="fichier de sortie")
    parser.add_argument("--zip", help="ecrit aussi l'archive de mise a jour (ZIP)")
    args = parser.parse_args(argv)

    if args.zip:
        count = build_zip(Path(args.zip))
        print("Archive generee : %s (%d fichiers)" % (args.zip, count))

    payload = build_payload()
    html = build_html(payload)
    output = (
        Path(args.output)
        if args.output
        else ROOT / "dist" / DIST_NAME
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(html)

    payload_bytes = sum(len(base64.b64decode(value)) for value in payload["files"].values())
    print("Installateur genere : %s" % output)
    print("  version  : %s" % payload["version"])
    print("  fichiers : %d" % len(payload["files"]))
    print(
        "  contenu  : %.1f Ko  (HTML : %.1f Ko)"
        % (payload_bytes / 1024.0, len(html.encode("utf-8")) / 1024.0)
    )
    print("  script   : %s" % payload["userscript"])
    languages = collect_languages()
    print("  langues  : %s" % (", ".join(sorted(languages)) or "aucune"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
