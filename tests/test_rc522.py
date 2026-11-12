"""Tests du pilote MFRC522 (grâce à un faux bus SPI)."""

from __future__ import annotations

import ctypes
import unittest

import support  # noqa: F401  (ajoute app/ au sys.path)
from fake_rc522 import FakeRc522Spi

from rfid.drivers.rc522 import Rc522, Rc522Reader
from rfid.drivers.spi_port import (
    SPI_IOC_WR_MAX_SPEED_HZ,
    SPI_IOC_WR_MODE,
    SpiIocTransfer,
    spi_ioc_message,
)


class IoctlEncodingTest(unittest.TestCase):
    def test_struct_size(self):
        # struct spi_ioc_transfer fait 32 octets, en 32 comme en 64 bits.
        self.assertEqual(ctypes.sizeof(SpiIocTransfer), 32)

    def test_message_number(self):
        self.assertEqual(spi_ioc_message(1), 0x40206B00)
        self.assertEqual(spi_ioc_message(2), 0x40406B00)

    def test_other_ioctls(self):
        self.assertEqual(SPI_IOC_WR_MODE, 0x40016B01)
        self.assertEqual(SPI_IOC_WR_MAX_SPEED_HZ, 0x40046B04)


class Rc522UidTest(unittest.TestCase):
    def test_uid_4_octets(self):
        spi = FakeRc522Spi(b"\xDE\xAD\xBE\xEF")
        reader = Rc522(spi)
        self.assertEqual(reader.begin(), 0x92)
        self.assertEqual(reader.read_uid(), b"\xDE\xAD\xBE\xEF")

    def test_uid_7_octets(self):
        spi = FakeRc522Spi(b"\x01\x02\x03\x04\x05\x06\x07")
        reader = Rc522(spi)
        reader.begin()
        self.assertEqual(reader.read_uid(), b"\x01\x02\x03\x04\x05\x06\x07")

    def test_aucun_badge(self):
        spi = FakeRc522Spi(None)
        reader = Rc522(spi)
        reader.begin()
        self.assertIsNone(reader.read_uid())

    def test_bcc_faux_n_empeche_pas_la_lecture(self):
        """Un BCC errone (badge clone) ne doit plus faire echouer la lecture."""
        reader = Rc522(FakeRc522Spi(b"\xDE\xAD\xBE\xEF", bad_bcc=True))
        reader.begin()
        self.assertEqual(reader.read_uid(), b"\xDE\xAD\xBE\xEF")

    def test_badge_endormi_reveille_par_wupa(self):
        """Un badge qui ne repond qu'a WUPA est quand meme lu."""
        reader = Rc522(FakeRc522Spi(b"\x11\x22\x33\x44", wupa_only=True))
        reader.begin()
        self.assertEqual(reader.read_uid(), b"\x11\x22\x33\x44")

    def test_trace_des_trames(self):
        """La trace decrit la trame envoyee et la reponse, pour le diagnostic."""
        reader = Rc522(FakeRc522Spi(b"\x01\x02\x03\x04"))
        reader.begin()
        trace = {}
        self.assertEqual(reader.read_uid(trace=trace), b"\x01\x02\x03\x04")
        self.assertEqual(trace["atqa"], "0400")
        self.assertEqual(trace["sak"], "0x08")
        trames = [step["tx"] for step in trace["steps"]]
        self.assertIn("9320", trames)

    def test_lecteur_avec_anti_rebond(self):
        spi = FakeRc522Spi(b"\xDE\xAD\xBE\xEF")
        reader = Rc522Reader(spi, cooldown_s=30.0)
        self.assertEqual(reader.start(), 0x92)
        self.assertEqual(reader.read_uid(), "DEADBEEF")
        # Meme badge relu immediatement : ignore (anti-rebond)
        self.assertIsNone(reader.read_uid())

    def test_lecteur_sans_anti_rebond(self):
        spi = FakeRc522Spi(b"\x01\x02\x03\x04")
        reader = Rc522Reader(spi, cooldown_s=0.0)
        reader.start()
        self.assertEqual(reader.read_uid(), "01020304")
        self.assertEqual(reader.read_uid(), "01020304")


if __name__ == "__main__":
    unittest.main()
