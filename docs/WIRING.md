# Wiring

![Wiring of the RC522 reader and the push button](wiring.svg)

## The RC522 reader (nf-SL001)

The module uses the **SPI0** bus of the Raspberry Pi and must be powered with
**3.3 V**.

| RC522 | Raspberry Pi (name) | GPIO (BCM) | Physical pin |
| --- | --- | --- | --- |
| SDA (SS) | CE0 | GPIO8 | 24 |
| SCK | SCLK | GPIO11 | 23 |
| MOSI | MOSI | GPIO10 | 19 |
| MISO | MISO | GPIO9 | 21 |
| RST | free pin | GPIO25 | 22 |
| GND | GND | — | 6, 9, 14, 20, 25, 30, 34, 39 |
| 3.3V | 3V3 | — | 1 or 17 |
| IRQ | not connected | — | — |

Pin 1 is the pin closest to the corner, on the "3V3" side (marked with a square
on many boards). Seen from above, header at the top, the 40-pin GPIO connector
reads like this:

```
                 3V3  (1)  (2)  5V      <- WS2812 LEDs (+5 V)
               GPIO2  (3)  (4)  5V
               GPIO3  (5)  (6)  GND     <- RC522 GND
               GPIO4  (7)  (8)  GPIO14
   button  ->    GND  (9)  (10) GPIO15
   button  ->  GPIO17 (11) (12) GPIO18
              GPIO27 (13) (14) GND      <- RGB LED (common cathode)
   RGB red -> GPIO22 (15) (16) GPIO23  <- RGB green
                 3V3 (17) (18) GPIO24  <- RGB blue
   RC522 MOSI GPIO10 (19) (20) GND
   RC522 MISO GPIO9  (21) (22) GPIO25  <- RC522 RST
   RC522 SCK  GPIO11 (23) (24) GPIO8   <- RC522 SDA (CE0)
                 GND (25) (26) GPIO7
                        ...
                 GND (39) (40) GPIO21
   WS2812 data on GPIO20 = pin 38
```

> If your reader is wired to the other chip select (CE1 = GPIO7, pin 26), set
> `spi_device = /dev/spidev0.1` in `config.ini`.

## The push button

The button goes **between GPIO17 (pin 11) and GND (pin 9)**.

* No resistor: the program enables the **internal pull-up** of the processor
  (`PUD_UP`); the pin reads 1 at rest and 0 when pressed.
* A 4-leg button is wired in pairs: the two legs on the same side are connected
  together. Check with a multimeter in continuity mode.
* One side of the button on GPIO17, the other on GND. The direction does not
  matter.

To use another pin, change `pin = 17` in the `[button]` section of
`config.ini`, then `sh rfidctl restart`.

## The status light (optional)

A light next to the slot shows what the reader is doing, which matters when
the reader is hidden in the case:

| Colour | Meaning |
| --- | --- |
| steady green | ready (can be turned off at rest in the settings) |
| short white flash | a game starts |
| blinking blue | waiting for a badge to pair |
| blinking orange | waiting for a badge to erase |
| blinking white | a computer or a phone asks for access: hold the button 3 s |
| blinking yellow | less than one minute of play time left |
| red flash | unknown badge, or refused action |
| slow red blink | the reader does not answer |
| magenta flash | bonus time added |
| steady purple | bedtime (option "Light for bedtime and time up") |
| steady orange | the active player (or the guest) has no time left today (same option) |

Choose the kind of light in the page: **Settings › Status light**.

### Choice 1: an RGB LED (4 legs)

| LED leg | Raspberry Pi |
| --- | --- |
| red | GPIO22, pin 15 |
| green | GPIO23, pin 16 |
| blue | GPIO24, pin 18 |
| common (the longest leg) | GND pin 14 (common cathode) **or** 3V3 pin 17 (common anode) |

The pins can be changed in the advanced settings. Colours are on/off: red,
green, blue, yellow, cyan, magenta and white (orange shows as yellow).

**What about the resistors?** A bare LED needs one resistor per colour leg: a
GPIO pin does not limit its current, and without a resistor the LED draws too
much and can damage the pin of the Raspberry Pi. On 3.3 V, 100 to 220 Ω is
right (220 Ω is the usual value; 100 Ω gives a brighter green and blue). To
avoid soldering any resistor:

* buy the LED **already soldered on a small board** ("RGB LED module",
  KY-016 and the like): the resistors are on the board, the four pins plug
  straight into Dupont wires;
* or use **programmable LEDs** (choice 2): they have their own controller and
  need no resistor.

### Choice 2: programmable LEDs (WS2812, WS2812B, SK6812, "NeoPixel")

A single LED, a ring or a piece of strip: all the LEDs take the same colour,
with an adjustable brightness.

| LED pad | Raspberry Pi |
| --- | --- |
| DIN (data in) | GPIO20, pin 38 |
| 5V / VCC | 5V, pin 2 or 4 |
| GND | GND, pin 39 |

* The LEDs are driven by the **second SPI bus** of the Raspberry Pi (the first
  one belongs to the RC522). When you choose "programmable LEDs" in the page,
  the line `dtoverlay=spi1-1cs` is added to the boot configuration; **restart
  the Recalbox** once to enable it.
* This bus also reserves GPIO18, GPIO19 and GPIO21 (pins 12, 35 and 40): do not
  use them for anything else (an I2S audio board uses them, for example).
* Keep the data wire short (under 30 cm). Most LEDs accept the 3.3 V data
  signal of the Raspberry Pi; if the colours flicker, add a 330 Ω resistor on
  the data wire, or a level shifter (74AHCT125).
* Up to 150 LEDs. Beyond a few LEDs at full brightness, power them from a
  separate 5 V supply (common GND with the Raspberry Pi).

## Points to check

1. **3.3 V** for the RC522, never 5 V (it does not tolerate 5 V).
2. The MISO/MOSI wires are not crossed: MISO→MISO, MOSI→MOSI.
3. The grounds (GND) are shared between the reader, the button, the light and
   the Pi.
4. The Dupont wires are fully pushed in: a loose contact on SCK gives exactly
   the "no badge detected" symptom.
5. Watch out for the **GPIO controllers** of Recalbox: with
   `controllers.gpio.enabled=1` in `recalbox.conf`, pins are reserved. Leave
   this option at `0`.

## Checking

Once the Recalbox has restarted (SPI enabled), the page has a **Hardware ›
Test with a badge** button. Over SSH:

```sh
sh /recalbox/share/system/rfid/rfidctl test
```

Expected result:

```
--- Lecteur RC522 (/dev/spidev0.0) ---
  Version du MFRC522 : 0x92
  Posez un badge sur le lecteur (attente 8 secondes)...
  Badge detecte : A1:B2:C3:D4
```

* `0x91`, `0x92`, `0x88`, `0x12`…: the reader answers, SPI is fine.
* `0x00` or `0xFF`: SPI is enabled but the reader does not answer → wiring,
  power, or soldering of the module.
* `/dev/spidev0.0` missing: SPI is not enabled (see
  [TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

A 13.56 MHz badge (MIFARE Classic / Ultralight, NTAG) is recognized with a 4 or
7 byte identifier. A 125 kHz badge (old access control) does **not** work.
