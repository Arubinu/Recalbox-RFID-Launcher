"""Recalbox RFID Launcher.

Scan an RFID badge (MFRC522 / RC522 reader on the Raspberry Pi SPI bus) and
the matching Recalbox game starts. A push button pairs a badge with the game
currently selected in the Recalbox interface.

The project only uses the Python 3 standard library: no package needs to be
installed on Recalbox.
"""

__version__ = "2.10.0"
