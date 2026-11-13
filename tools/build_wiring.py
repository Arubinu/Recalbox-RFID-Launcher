"""Generates the wiring diagram (SVG): installer.html page + docs/wiring.svg.

The same drawing is used in both places:
* in the page, as inline SVG: the colours come from the page CSS variables,
  so it follows the chosen light or dark theme;
* as a ``docs/wiring.svg`` file: it carries its own style sheet and follows
  ``prefers-color-scheme`` (works in an ``<img>`` of the README).

Running this script again updates both; it also injects the diagram again
between the markers of ``installer.html``.
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wire colours: they do not depend on the theme (one wire = one colour).
FILS = {
    "3V3": "#e03131",
    "GND": "#6c757d",
    "SDA": "#f08c00",
    "SCK": "#2f9e44",
    "MOSI": "#1971c2",
    "MISO": "#7048e8",
    "RST": "#0c8599",
    "BTN": "#d6336c",
}

#: Diagram palette, per variable: overridden by the page and by the file.
PALETTE_CLAIR = {
    "c-bg": "#f8f9fa",
    "c-card": "#ffffff",
    "c-ink": "#212529",
    "c-sub": "#495057",
    "c-faint": "#868e96",
    "c-line": "#dee2e6",
    "c-row": "#f1f3f5",
    "c-alert-bg": "#fff5f5",
    "c-alert-line": "#ffc9c9",
    "c-alert-ink": "#c92a2a",
    "c-good": "#2f9e44",
}

PALETTE_SOMBRE = {
    "c-bg": "#0f131b",
    "c-card": "#161b25",
    "c-ink": "#eaeef7",
    "c-sub": "#a8b3c7",
    "c-faint": "#7f8a9e",
    "c-line": "rgba(255, 255, 255, .14)",
    "c-row": "rgba(255, 255, 255, .05)",
    "c-alert-bg": "rgba(224, 49, 49, .12)",
    "c-alert-line": "rgba(224, 49, 49, .38)",
    "c-alert-ink": "#ff9b98",
    "c-good": "#37b26c",
}

# (key, physical pin, GPIO name, name on the RC522 module)
BROCHES_PI = [
    ("3V3", 1, "3V3", "3.3V"),
    ("GND", 6, "GND", "GND"),
    ("SDA", 24, "GPIO8 · CE0", "SDA"),
    ("SCK", 23, "GPIO11 · SCLK", "SCK"),
    ("MOSI", 19, "GPIO10 · MOSI", "MOSI"),
    ("MISO", 21, "GPIO9 · MISO", "MISO"),
    ("RST", 22, "GPIO25", "RST"),
    ("GND", 9, "GND", "—"),
    ("BTN", 11, "GPIO17", "—"),
]

MODULE_PINS = [
    ("SDA", "SDA", 24),
    ("SCK", "SCK", 23),
    ("MOSI", "MOSI", 19),
    ("MISO", "MISO", 21),
    ("IRQ", "IRQ", None),
    ("GND", "GND", 6),
    ("RST", "RST", 22),
    ("3V3", "3.3V", 1),
]

NOTES = [
    "• Le module doit être alimenté en 3,3 V (broche 1) et partager la masse (broche 6 ou 9).",
    "• MISO (broche 21) et MOSI (broche 19) ne se croisent pas : MISO vers MISO, MOSI vers MOSI.",
    "• Si vos badges ne sont pas lus, lancez « Tester avec un badge » : le test dit si une carte répond.",
]


def esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def c(nom: str) -> str:
    """Reference to a colour variable of the diagram."""
    return "var(--%s)" % nom


def dessin() -> list:
    """Diagram body, with CSS variables (so it can be themed)."""
    largeur, hauteur = 940, 588
    out = []
    add = out.append

    add('<rect x="0" y="0" width="%d" height="%d" rx="14" fill="%s"/>'
        % (largeur, hauteur, c("c-bg")))

    add('<text x="30" y="42" font-size="21" font-weight="700" fill="%s">'
        'Branchement du lecteur RC522 et du bouton</text>' % c("c-ink"))
    add('<text x="30" y="66" font-size="13.5" fill="%s">'
        'Le lecteur se branche sur le bus SPI, le bouton entre une broche GPIO et la masse. '
        'Aucune résistance.</text>' % c("c-sub"))
    add('<rect x="30" y="78" width="470" height="26" rx="7" fill="%s" stroke="%s"/>'
        % (c("c-alert-bg"), c("c-alert-line")))
    add('<text x="42" y="96" font-size="13" font-weight="600" fill="%s">'
        '⚠ 3,3 V uniquement : le 5 V détruit le module et la carte.</text>' % c("c-alert-ink"))

    # --------------------------------------------------------- Pi panel
    x_pi, y_pi, w_pi, h_pi = 30, 120, 400, 356
    add('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>'
        % (x_pi, y_pi, w_pi, h_pi, c("c-card"), c("c-line")))
    add('<text x="%d" y="%d" font-size="15" font-weight="700" fill="%s">'
        'Raspberry Pi — broches à utiliser</text>' % (x_pi + 16, y_pi + 26, c("c-ink")))
    add('<text x="%d" y="%d" font-size="11.5" fill="%s">'
        'numéros du connecteur 40 broches, vue de dessus</text>'
        % (x_pi + 16, y_pi + 44, c("c-faint")))

    y = y_pi + 68
    for cle, numero, fonction, module in BROCHES_PI:
        couleur = FILS[cle]
        if cle == "BTN":
            etiquette = "bouton · signal"
        elif module == "—":
            etiquette = "bouton · masse"
        else:
            etiquette = module
        add('<rect x="%d" y="%d" width="368" height="30" rx="8" fill="%s"/>'
            % (x_pi + 16, y - 20, c("c-row")))
        add('<circle cx="%d" cy="%d" r="6" fill="%s"/>' % (x_pi + 34, y - 5, couleur))
        add('<text x="%d" y="%d" font-size="13" font-weight="700" fill="%s">'
            'broche %d</text>' % (x_pi + 50, y, c("c-ink"), numero))
        add('<text x="%d" y="%d" font-size="12.5" fill="%s">%s</text>'
            % (x_pi + 132, y, c("c-sub"), esc(fonction)))
        add('<text x="%d" y="%d" font-size="12.5" font-weight="600" fill="%s" '
            'text-anchor="end">%s</text>' % (x_pi + 368, y, couleur, esc(etiquette)))
        y += 32

    # ----------------------------------------------------- module panel
    x_rc, y_rc, w_rc, h_rc = 462, 120, 448, 212
    add('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>'
        % (x_rc, y_rc, w_rc, h_rc, c("c-card"), c("c-line")))
    add('<text x="%d" y="%d" font-size="15" font-weight="700" fill="%s">'
        'Lecteur RC522 (13,56 MHz)</text>' % (x_rc + 16, y_rc + 26, c("c-ink")))
    add('<text x="%d" y="%d" font-size="11.5" fill="%s">'
        'les 8 broches du module, dans l’ordre du connecteur</text>'
        % (x_rc + 16, y_rc + 44, c("c-faint")))

    y = y_rc + 68
    for cle, nom_module, broche in MODULE_PINS:
        couleur = FILS.get(cle, c("c-faint"))
        add('<rect x="%d" y="%d" width="416" height="17" rx="5" fill="%s"/>'
            % (x_rc + 16, y - 12, c("c-row")))
        add('<circle cx="%d" cy="%d" r="5" fill="%s"/>' % (x_rc + 32, y - 4, couleur))
        add('<text x="%d" y="%d" font-size="12.5" font-weight="700" fill="%s">%s</text>'
            % (x_rc + 46, y, c("c-ink"), esc(nom_module)))
        if broche:
            add('<text x="%d" y="%d" font-size="12.5" fill="%s">→ broche %d du Pi</text>'
                % (x_rc + 110, y, c("c-sub"), broche))
        else:
            add('<text x="%d" y="%d" font-size="12.5" fill="%s">'
                '→ non connectée</text>' % (x_rc + 110, y, c("c-faint")))
        y += 18

    # -------------------------------------------------------- button panel
    x_bt, y_bt, w_bt, h_bt = 462, 348, 448, 168
    add('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>'
        % (x_bt, y_bt, w_bt, h_bt, c("c-card"), c("c-line")))
    add('<text x="%d" y="%d" font-size="15" font-weight="700" fill="%s">'
        'Bouton poussoir</text>' % (x_bt + 16, y_bt + 26, c("c-ink")))
    add('<text x="%d" y="%d" font-size="11.5" fill="%s">'
        'appui court = associer · 3 s = autoriser un navigateur (effacement : dans l’interface)</text>'
        % (x_bt + 16, y_bt + 44, c("c-faint")))

    x0 = x_bt + 46
    y_fil = y_bt + 100
    add('<text x="%d" y="%d" font-size="12" fill="%s">borne 1 → broche 11 (GPIO17)</text>'
        % (x0, y_fil - 16, c("c-sub")))
    add('<path d="M%d %d h34" stroke="%s" stroke-width="3" fill="none"/>'
        % (x0, y_fil, FILS["BTN"]))
    add('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (x0, y_fil, FILS["BTN"]))
    add('<path d="M%d %d q13 -20 28 -2" stroke="%s" stroke-width="2.5" fill="none"/>'
        % (x0 + 34, y_fil, c("c-ink")))
    add('<path d="M%d %d h34" stroke="%s" stroke-width="3" fill="none"/>'
        % (x0 + 64, y_fil, FILS["GND"]))
    add('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (x0 + 98, y_fil, FILS["GND"]))
    add('<text x="%d" y="%d" font-size="12" fill="%s">borne 2 → broche 9 (GND)</text>'
        % (x0 + 118, y_fil + 16, c("c-sub")))
    add('<text x="%d" y="%d" font-size="12" font-weight="600" fill="%s">'
        'aucune résistance : le pull-up interne du Pi suffit</text>'
        % (x_bt + 16, y_bt + h_bt - 14, c("c-good")))

    # ---------------------------------------------------------------- notes
    for index, note in enumerate(NOTES):
        add('<text x="30" y="%d" font-size="12.5" fill="%s">%s</text>'
            % (536 + index * 20, c("c-sub"), esc(note)))
    return out


def feuille_de_style() -> str:
    """Embedded style of the standalone file (follows prefers-color-scheme)."""
    clair = "".join("--%s:%s;" % (nom, valeur) for nom, valeur in PALETTE_CLAIR.items())
    sombre = "".join("--%s:%s;" % (nom, valeur) for nom, valeur in PALETTE_SOMBRE.items())
    return ('<style>'
            ':root{%s}'
            '@media (prefers-color-scheme: dark){:root{%s}}'
            '</style>') % (clair, sombre)


def build(standalone: bool = False) -> str:
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 588" width="100%" '
           'role="img" aria-labelledby="wiring-title" '
           'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">']
    out.append('<title id="wiring-title">Branchement du lecteur RC522 et du bouton '
               'poussoir sur le Raspberry Pi</title>')
    if standalone:
        out.append(feuille_de_style())
    out.extend(dessin())
    out.append("</svg>")
    return "\n".join(out)


DEBUT = "<!-- wiring:start (generated by tools/build_wiring.py) -->"
FIN = "<!-- wiring:end -->"


def injecter(svg: str) -> str:
    """Injects the diagram into installer.html between the two markers."""
    page = os.path.join(ROOT, "installer.html")
    with io.open(page, "r", encoding="utf-8") as handle:
        texte = handle.read()
    if DEBUT not in texte or FIN not in texte:
        raise SystemExit("marqueurs %r / %r absents de installer.html" % (DEBUT, FIN))
    avant, reste = texte.split(DEBUT, 1)
    _milieu, apres = reste.split(FIN, 1)
    indent = " " * 20
    corps = svg.replace("\n", "\n" + indent)
    return avant + DEBUT + "\n" + indent + corps + "\n" + " " * 16 + FIN + apres


def main() -> int:
    cible = os.path.join(ROOT, "docs", "wiring.svg")
    autonome = build(standalone=True)
    with io.open(cible, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(autonome + "\n")
    page = os.path.join(ROOT, "installer.html")
    contenu = injecter(build(standalone=False))   # reads the page before writing it
    with io.open(page, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(contenu)
    print("%s : %d octets (themes clair et sombre)" % (cible, len(autonome)))
    print("installer.html : schema reinjecte (couleurs du theme de la page)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
