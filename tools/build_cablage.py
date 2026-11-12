"""Genere le schema de cablage (SVG) : page installer.html + docs/cablage.svg.

Le meme dessin sert aux deux endroits : inline dans la page (aucune ressource
externe, la page reste autonome) et en fichier pour le README et la doc.
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COULEURS = {
    "3V3": "#e03131",
    "GND": "#6c757d",
    "SDA": "#f08c00",
    "SCK": "#2f9e44",
    "MOSI": "#1971c2",
    "MISO": "#7048e8",
    "RST": "#0c8599",
    "BTN": "#d6336c",
}

# (cle, broche physique, nom officiel, nom sur le module RC522)
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


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build() -> str:
    largeur, hauteur = 940, 588
    out = []
    add = out.append

    add('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'width="100%%" role="img" aria-labelledby="cablage-titre" '
        'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">'
        % (largeur, hauteur))
    add('<title id="cablage-titre">Branchement du lecteur RC522 et du bouton '
        'poussoir sur le Raspberry Pi</title>')
    add('<rect x="0" y="0" width="%d" height="%d" rx="14" fill="#f8f9fa"/>' % (largeur, hauteur))

    # ------------------------------------------------------------- titres
    add('<text x="30" y="42" font-size="21" font-weight="700" fill="#212529">'
        'Branchement du lecteur RC522 et du bouton</text>')
    add('<text x="30" y="66" font-size="13.5" fill="#495057">'
        'Le lecteur se branche sur le bus SPI, le bouton entre une broche GPIO et la masse. '
        'Aucune résistance.</text>')
    add('<rect x="30" y="78" width="470" height="26" rx="7" fill="#fff5f5" stroke="#ffc9c9"/>')
    add('<text x="42" y="96" font-size="13" font-weight="600" fill="#c92a2a">'
        '⚠ 3,3 V uniquement : le 5 V détruit le module et la carte.</text>')

    # -------------------------------------------------------- panneau Pi
    x_pi, y_pi, w_pi, h_pi = 30, 120, 400, 356
    add('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="#ffffff" '
        'stroke="#dee2e6"/>' % (x_pi, y_pi, w_pi, h_pi))
    add('<text x="%d" y="%d" font-size="15" font-weight="700" fill="#212529">'
        'Raspberry Pi — broches à utiliser</text>' % (x_pi + 16, y_pi + 26))
    add('<text x="%d" y="%d" font-size="11.5" fill="#868e96">'
        'numéros du connecteur 40 broches, vue de dessus</text>' % (x_pi + 16, y_pi + 44))

    y = y_pi + 68
    for cle, numero, fonction, module in BROCHES_PI:
        couleur = COULEURS[cle]
        if cle == "BTN":
            etiquette = "bouton · signal"
        elif module == "—":
            etiquette = "bouton · masse"
        else:
            etiquette = module
        add('<rect x="%d" y="%d" width="368" height="30" rx="8" fill="#f1f3f5"/>'
            % (x_pi + 16, y - 20))
        add('<circle cx="%d" cy="%d" r="6" fill="%s"/>' % (x_pi + 34, y - 5, couleur))
        add('<text x="%d" y="%d" font-size="13" font-weight="700" fill="#212529">'
            'broche %d</text>' % (x_pi + 50, y, numero))
        add('<text x="%d" y="%d" font-size="12.5" fill="#495057">%s</text>'
            % (x_pi + 132, y, esc(fonction)))
        add('<text x="%d" y="%d" font-size="12.5" font-weight="600" fill="%s" '
            'text-anchor="end">%s</text>' % (x_pi + 368, y, couleur, esc(etiquette)))
        y += 32

    # -------------------------------------------------- panneau module RC522
    x_rc, y_rc, w_rc, h_rc = 462, 120, 448, 212
    add('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="#ffffff" '
        'stroke="#dee2e6"/>' % (x_rc, y_rc, w_rc, h_rc))
    add('<text x="%d" y="%d" font-size="15" font-weight="700" fill="#212529">'
        'Lecteur RC522 (13,56 MHz)</text>' % (x_rc + 16, y_rc + 26))
    add('<text x="%d" y="%d" font-size="11.5" fill="#868e96">'
        'les 8 broches du module, dans l’ordre du connecteur</text>' % (x_rc + 16, y_rc + 44))

    module_pins = [
        ("SDA", "SDA", 24),
        ("SCK", "SCK", 23),
        ("MOSI", "MOSI", 19),
        ("MISO", "MISO", 21),
        ("IRQ", "IRQ", None),
        ("GND", "GND", 6),
        ("RST", "RST", 22),
        ("3V3", "3.3V", 1),
    ]
    y = y_rc + 68
    for cle, nom_module, broche in module_pins:
        couleur = COULEURS.get(cle, "#adb5bd")
        add('<rect x="%d" y="%d" width="416" height="17" rx="5" fill="%s"/>'
            % (x_rc + 16, y - 12, "#f1f3f5"))
        add('<circle cx="%d" cy="%d" r="5" fill="%s"/>' % (x_rc + 32, y - 4, couleur))
        add('<text x="%d" y="%d" font-size="12.5" font-weight="700" fill="#212529">%s</text>'
            % (x_rc + 46, y, esc(nom_module)))
        if broche:
            add('<text x="%d" y="%d" font-size="12.5" fill="#495057">→ broche %d du Pi</text>'
                % (x_rc + 110, y, broche))
        else:
            add('<text x="%d" y="%d" font-size="12.5" fill="#868e96">'
                '→ non connectée</text>' % (x_rc + 110, y))
        y += 18

    # --------------------------------------------------------- panneau bouton
    x_bt, y_bt, w_bt, h_bt = 462, 348, 448, 168
    add('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="#ffffff" '
        'stroke="#dee2e6"/>' % (x_bt, y_bt, w_bt, h_bt))
    add('<text x="%d" y="%d" font-size="15" font-weight="700" fill="#212529">'
        'Bouton poussoir</text>' % (x_bt + 16, y_bt + 26))
    add('<text x="%d" y="%d" font-size="11.5" fill="#868e96">'
        'appui court = associer · appui long = effacer · 3 s = autoriser</text>'
        % (x_bt + 16, y_bt + 44))

    # dessin du bouton
    x0 = x_bt + 46
    y_fil = y_bt + 100
    add('<text x="%d" y="%d" font-size="12" fill="#495057">borne 1 → broche 11 (GPIO17)</text>'
        % (x0, y_fil - 16))
    add('<path d="M%d %d h34" stroke="%s" stroke-width="3" fill="none"/>'
        % (x0, y_fil, COULEURS["BTN"]))
    add('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (x0, y_fil, COULEURS["BTN"]))
    add('<path d="M%d %d q13 -20 28 -2" stroke="#212529" stroke-width="2.5" fill="none"/>'
        % (x0 + 34, y_fil))
    add('<path d="M%d %d h34" stroke="%s" stroke-width="3" fill="none"/>'
        % (x0 + 64, y_fil, COULEURS["GND"]))
    add('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (x0 + 98, y_fil, COULEURS["GND"]))
    add('<text x="%d" y="%d" font-size="12" fill="#495057">borne 2 → broche 9 (GND)</text>'
        % (x0 + 118, y_fil + 16))
    add('<text x="%d" y="%d" font-size="12" font-weight="600" fill="#2f9e44">'
        'aucune résistance : le pull-up interne du Pi suffit</text>'
        % (x_bt + 16, y_bt + h_bt - 14))

    # ------------------------------------------------------------------ notes
    add('<text x="30" y="536" font-size="12.5" fill="#495057">'
        '• Le module doit être alimenté en 3,3 V (broche 1) et partager la masse (broche 6 ou 9).</text>')
    add('<text x="30" y="556" font-size="12.5" fill="#495057">'
        '• MISO (broche 21) et MOSI (broche 19) ne se croisent pas : MISO vers MISO, MOSI vers MOSI.</text>')
    add('<text x="30" y="576" font-size="12.5" fill="#495057">'
        '• Si vos badges ne sont pas lus, lancez « Tester avec un badge » : le test dit si une carte '
        'répond.</text>')
    add("</svg>")
    return "\n".join(out)


DEBUT = "<!-- cablage:debut (genere par tools/build_cablage.py) -->"
FIN = "<!-- cablage:fin -->"


def injecter(svg: str) -> str:
    """Insere le schema dans installer.html entre les deux marqueurs."""
    page = os.path.join(ROOT, "installer.html")
    with io.open(page, "r", encoding="utf-8") as handle:
        texte = handle.read()
    if DEBUT not in texte or FIN not in texte:
        raise SystemExit("marqueurs %r / %r absents de installer.html" % (DEBUT, FIN))
    avant, reste = texte.split(DEBUT, 1)
    _milieu, apres = reste.split(FIN, 1)
    indent = svg.replace("\n", "\n" + " " * 16)
    return avant + DEBUT + "\n" + " " * 16 + indent + "\n" + " " * 16 + FIN + apres


def main() -> int:
    svg = build()
    cible = os.path.join(ROOT, "docs", "cablage.svg")
    with io.open(cible, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg + "\n")
    page = os.path.join(ROOT, "installer.html")
    contenu = injecter(svg)          # lit la page avant de l'ouvrir en ecriture
    with io.open(page, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(contenu)
    print("%s : %d octets" % (cible, len(svg)))
    print("installer.html : schema reinjecte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
