#!/usr/bin/env python3
"""Génère un installateur HTML autonome (fichiers embarqués).

Le fichier produit (`dist/recalbox-rfid-installer.html`) contient tout
le nécessaire : la page de gestion **et** le contenu des fichiers à copier sur la
Recalbox. Il ne dépend donc plus d'aucun autre fichier du projet.

Fonctionnement dans le navigateur (Edge ou Chrome) :

1. la page propose de choisir ``\\\\RECALBOX\\share`` (API File System Access) ;
2. elle crée ``recalbox-rfid\\`` et le script de démarrage dans ``userscripts\\`` ;
3. elle depose aussi ``userscripts/manual/Installer-lecteur-RFID.sh`` :
   sur Recalbox 10, on le lance depuis le menu (START > Reglages avances >
   Scripts utilisateur), sans redemarrer ; sur Recalbox 9, on redemarre ;
4. la meme page attend l'agent WebSocket puis demande l'appui de 3 s.

Relancez ce script après chaque modification d'un fichier du projet :

    python tools/build_installer.py
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Nom du dossier créé sur le partage.
PROJECT_NAME = "recalbox-rfid"

#: Script permanent à copier dans ``userscripts/``.
USERSCRIPT = "bootstrap/recalbox-rfid-agent(permanent).py3"

#: Script a lancer depuis le menu de Recalbox 10 (``userscripts/manual/``) :
#: il demarre l'installation sans redemarrage.
MANUALSCRIPT = "bootstrap/manual/Installer-lecteur-RFID.sh"

#: Fichiers de la racine utiles sur la Recalbox.
ROOT_FILES = (
    "install.sh",
    "uninstall.sh",
    "VERSION",
    "README.md",
    "CHANGELOG.md",
    "installer.html",  # page « dossier » copiée sur la Recalbox et dans l'installateur .cmd
)

#: Dossiers embarqués (les tests ne servent pas sur la Recalbox).
DIRECTORIES = ("app", "userscript", "bootstrap", "docs")

#: Page source (le fichier généré est cette page + le contenu embarqué).
HTML_SOURCE = "installer.html"

#: Dossier des traductions : un fichier JSON par langue (code a 2 lettres).
I18N_DIR = "i18n"

#: Langue de reference : les textes de la page sont ecrits en francais.
LANGUE_SOURCE = "fr"

#: Nom du fichier livre (sans numero de version).
DIST_NAME = "recalbox-rfid-installer.html"

#: Point d'insertion du contenu embarqué.
MARKER = "<body>"

EXCLUDED_SUFFIXES = (".pyc", ".pyo")


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def collect_files() -> dict:
    """Retourne {chemin relatif posix: contenu binaire} trié."""
    files = {}
    for name in ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            files[name] = path.read_bytes()
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
    return dict(sorted(files.items()))


def build_payload(files: dict = None) -> dict:
    files = files if files is not None else collect_files()
    return {
        "project": PROJECT_NAME,
        "version": version(),
        "userscript": USERSCRIPT,
        "manualscript": MANUALSCRIPT,
        "files": {
            path: base64.b64encode(content).decode("ascii") for path, content in files.items()
        },
    }


def collect_languages() -> dict:
    """Charge ``i18n/<code>.json`` : {code: {texte source: traduction}}."""
    dossier = ROOT / I18N_DIR
    langues = {}
    if not dossier.is_dir():
        return langues
    for chemin in sorted(dossier.glob("*.json")):
        code = chemin.stem.lower()
        if len(code) != 2:
            continue
        try:
            contenu = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit("%s illisible : %s" % (chemin, exc))
        if not isinstance(contenu, dict):
            raise SystemExit("%s doit contenir un objet JSON" % chemin)
        langues[code] = contenu
    return langues


def build_html(payload: dict = None) -> str:
    payload = payload if payload is not None else build_payload()
    source_path = ROOT / HTML_SOURCE
    if not source_path.is_file():
        raise SystemExit("%s introuvable" % source_path)
    source = source_path.read_text(encoding="utf-8")
    if MARKER not in source:
        raise SystemExit("balise %s introuvable dans %s" % (MARKER, HTML_SOURCE))
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    # Le contenu est du base64 : il ne peut pas contenir "</script>".
    tag = '<script id="rfid-payload" type="application/json">%s</script>' % encoded
    html = source.replace(MARKER, MARKER + "\n" + tag, 1)

    langues = collect_languages()
    if langues:
        traductions = json.dumps(
            {"source": LANGUE_SOURCE, "langues": langues},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        bloc = '<script id="rfid-i18n" type="application/json">%s</script>' % traductions
        html = html.replace(MARKER, MARKER + "\n" + bloc, 1)
    return html


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", "-o", help="fichier de sortie")
    args = parser.parse_args(argv)

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
    langues = collect_languages()
    print("  langues  : %s" % (", ".join(sorted(langues)) or "aucune"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
