"""Generates the wiring picture of the READMEs: ``docs/wiring.svg``.

The file carries its own style sheet and follows ``prefers-color-scheme``
(it works in an ``<img>`` of a README). The page draws its own interactive
diagram from the same pin numbers (``wiringParts`` in installer.html): keep
both in step when a pin changes.

Usage: ``python tools/build_wiring.py``
"""

from __future__ import annotations

import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Wire colours: they do not depend on the theme (one wire = one colour).
#: Same values as WIRE_COLOURS in installer.html.
WIRES = {
    "3V3": "#e03131",
    "5V": "#a61e4d",
    "GND": "#7d8590",
    "SDA": "#f08c00",
    "SCK": "#2f9e44",
    "MOSI": "#1971c2",
    "MISO": "#7048e8",
    "RST": "#0c8599",
    "BTN": "#d6336c",
    "LR": "#fa5252",
    "LG": "#40c057",
    "LB": "#4dabf7",
    "DIN": "#fab005",
}

LIGHT = {
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

DARK = {
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

# (wire, module pin, Pi pin, GPIO name)
READER = [
    ("SDA", "SDA", 24, "GPIO8 · CE0"),
    ("SCK", "SCK", 23, "GPIO11 · SCLK"),
    ("MOSI", "MOSI", 19, "GPIO10 · MOSI"),
    ("MISO", "MISO", 21, "GPIO9 · MISO"),
    ("RST", "RST", 22, "GPIO25"),
    ("GND", "GND", 6, "GND"),
    ("3V3", "3.3V", 1, "3V3"),
    (None, "IRQ", None, "not connected"),
]

BUTTON = [
    ("BTN", "one leg", 11, "GPIO17"),
    ("GND", "the other leg", 9, "GND"),
]

LED_RGB = [
    ("LR", "red", 15, "GPIO22"),
    ("LG", "green", 16, "GPIO23"),
    ("LB", "blue", 18, "GPIO24"),
    ("GND", "common (cathode)", 14, "GND"),
]

LED_WS2812 = [
    ("DIN", "DIN (data)", 38, "GPIO20"),
    ("5V", "5V / VCC", 2, "5V"),
    ("GND", "GND", 39, "GND"),
]

NOTES = [
    "• MISO goes to MISO and MOSI to MOSI: they are not crossed.",
    "• Common-anode RGB LED: the common leg goes to 3V3 (pin 17) instead of GND.",
    "• Badges not read? Run “Test with a badge” in the page: it tells whether a card answers.",
]

WIDTH, HEIGHT = 940, 770


def esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def c(name: str) -> str:
    """Reference to a colour variable of the diagram."""
    return "var(--%s)" % name


def panel(out, x, y, w, h, title, subtitle):
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>'
               % (x, y, w, h, c("c-card"), c("c-line")))
    out.append('<text x="%d" y="%d" font-size="15" font-weight="700" fill="%s">%s</text>'
               % (x + 16, y + 26, c("c-ink"), esc(title)))
    if subtitle:
        out.append('<text x="%d" y="%d" font-size="11.5" fill="%s">%s</text>'
                   % (x + 16, y + 44, c("c-faint"), esc(subtitle)))


def rows(out, x, y, w, entries):
    """One line per wire: colour, part pin, Pi pin, GPIO name."""
    for wire, name, pin, gpio in entries:
        colour = WIRES.get(wire, c("c-faint"))
        out.append('<rect x="%d" y="%d" width="%d" height="26" rx="7" fill="%s"/>'
                   % (x, y - 18, w, c("c-row")))
        out.append('<circle cx="%d" cy="%d" r="5.5" fill="%s"/>' % (x + 16, y - 5, colour))
        out.append('<text x="%d" y="%d" font-size="12.5" font-weight="650" fill="%s">%s</text>'
                   % (x + 30, y, c("c-ink"), esc(name)))
        if pin:
            out.append('<text x="%d" y="%d" font-size="12.5" font-weight="700" fill="%s">pin %d</text>'
                       % (x + w - 150, y, c("c-ink"), pin))
        out.append('<text x="%d" y="%d" font-size="12" fill="%s" text-anchor="end">%s</text>'
                   % (x + w - 12, y, c("c-sub") if pin else c("c-faint"), esc(gpio)))
        y += 29
    return y


def drawing() -> list:
    """Diagram body, with CSS variables (so it can be themed)."""
    out = []
    add = out.append
    add('<rect x="0" y="0" width="%d" height="%d" rx="14" fill="%s"/>' % (WIDTH, HEIGHT, c("c-bg")))
    add('<text x="30" y="42" font-size="21" font-weight="700" fill="%s">'
        'Wiring the RC522 reader, the button and the light</text>' % c("c-ink"))
    add('<text x="30" y="66" font-size="13.5" fill="%s">Pin numbers of the 40-pin header of the '
        'Raspberry Pi, seen from above (pin 1 is the square one). Wire with the Recalbox off.</text>'
        % c("c-sub"))
    add('<rect x="30" y="80" width="430" height="26" rx="7" fill="%s" stroke="%s"/>'
        % (c("c-alert-bg"), c("c-alert-line")))
    add('<text x="42" y="98" font-size="13" font-weight="600" fill="%s">'
        '⚠ 3.3 V only for the reader: 5 V destroys the module.</text>' % c("c-alert-ink"))

    # Reader (left) and button (right).
    panel(out, 30, 122, 430, 370, "RC522 reader (13.56 MHz)", "module pin → Raspberry Pi pin")
    rows(out, 46, 190, 398, READER)
    panel(out, 480, 122, 430, 152, "Push button", "short press: pair · 3 s: authorize a device")
    rows(out, 496, 190, 398, BUTTON)
    add('<text x="496" y="258" font-size="12" font-weight="600" fill="%s">'
        'no resistor: the internal pull-up of the Pi is enough</text>' % c("c-good"))

    # Light: two possible kinds.
    panel(out, 480, 290, 430, 202, "Status light (optional) · choice 1",
          "RGB LED: one 220 Ω resistor per colour (already on a KY-016 module)")
    rows(out, 496, 358, 398, LED_RGB)

    panel(out, 30, 508, 880, 168, "Status light (optional) · choice 2",
          "programmable LEDs (WS2812, SK6812, NeoPixel): no resistor, then restart the Recalbox once")
    rows(out, 46, 572, 420, LED_WS2812)
    add('<text x="490" y="566" font-size="12.5" fill="%s">• Choose “programmable LEDs” in Settings › Status light:</text>'
        % c("c-sub"))
    add('<text x="502" y="584" font-size="12.5" fill="%s">the second SPI bus is enabled at the next start.</text>'
        % c("c-sub"))
    add('<text x="490" y="608" font-size="12.5" fill="%s">• Pins 12, 35 and 40 are then reserved.</text>'
        % c("c-sub"))
    add('<text x="490" y="632" font-size="12.5" fill="%s">• Many LEDs at full brightness: separate 5 V supply,</text>'
        % c("c-sub"))
    add('<text x="502" y="650" font-size="12.5" fill="%s">GND shared with the Raspberry Pi.</text>'
        % c("c-sub"))

    for index, note in enumerate(NOTES):
        add('<text x="30" y="%d" font-size="12.5" fill="%s">%s</text>'
            % (712 + index * 22, c("c-sub"), esc(note)))
    return out


def style_sheet() -> str:
    """Embedded style of the file (follows prefers-color-scheme)."""
    light = "".join("--%s:%s;" % (name, value) for name, value in LIGHT.items())
    dark = "".join("--%s:%s;" % (name, value) for name, value in DARK.items())
    return '<style>:root{%s}@media (prefers-color-scheme: dark){:root{%s}}</style>' % (light, dark)


def build() -> str:
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="100%%" '
           'role="img" aria-labelledby="wiring-title" '
           'font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif">' % (WIDTH, HEIGHT)]
    out.append('<title id="wiring-title">Wiring of the RC522 reader, the push button and the '
               'status light on the Raspberry Pi</title>')
    out.append(style_sheet())
    out.extend(drawing())
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    target = os.path.join(ROOT, "docs", "wiring.svg")
    content = build()
    with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content + "\n")
    print("%s: %d bytes (light and dark themes)" % (target, len(content)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
