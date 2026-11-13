"""MFRC522 driver tests (thanks to a fake SPI bus)."""

from __future__ import annotations

import ctypes
import unittest

import support  # noqa: F401  (adds app/ to sys.path)
from fake_rc522 import FakeRc522Spi

from rfid.drivers.rc522 import Rc522, Rc522Error, Rc522Reader, crc_a_software
from rfid.drivers.spi_port import (
    SPI_IOC_WR_MAX_SPEED_HZ,
    SPI_IOC_WR_MODE,
    SpiIocTransfer,
    spi_ioc_message,
)


class TagPresentTest(unittest.TestCase):
    """Badge presence: REQA, else WUPA, else silent (None)."""

    def lecteur(self, spi):
        reader = Rc522Reader(spi, cooldown_s=0.0)
        reader.start()
        return reader

    def test_badge_present(self):
        self.assertIs(self.lecteur(FakeRc522Spi(b"\xDE\xAD\xBE\xEF")).tag_present(), True)

    def test_aucun_badge(self):
        self.assertIs(self.lecteur(FakeRc522Spi(None)).tag_present(), False)

    def test_badge_qui_ne_repond_qu_a_wupa(self):
        # Regression: a selected badge no longer answers REQA. Without WUPA, a
        # badge lying on the reader looked removed (game started again by itself).
        self.assertIs(self.lecteur(FakeRc522Spi(b"\x11\x22\x33\x44", wupa_only=True)).tag_present(), True)

    def test_badge_clone_bcc_faux(self):
        self.assertIs(self.lecteur(FakeRc522Spi(b"\x36\x00\x00\x00", bad_bcc=True)).tag_present(), True)

    def test_lecteur_non_demarre_ne_conclut_pas(self):
        reader = Rc522Reader(FakeRc522Spi(b"\xDE\xAD\xBE\xEF"), cooldown_s=0.0)
        self.assertIsNone(reader.tag_present())

    def test_lecteur_muet_ne_conclut_pas(self):
        reader = self.lecteur(FakeRc522Spi(b"\xDE\xAD\xBE\xEF"))

        def tombe(*args, **kwargs):
            raise Rc522Error("SPI muet")

        reader.rc522.request = tombe
        self.assertIsNone(reader.tag_present())

    def test_presence_apres_une_lecture(self):
        # After read_uid, the card has been selected: the presence must stay
        # true (exactly the scenario of the game starting again by itself).
        spi = FakeRc522Spi(b"\x36\x00\x00\x00", bad_bcc=True)
        reader = self.lecteur(spi)
        self.assertEqual(reader.read_uid(), "36000000")
        self.assertIs(reader.tag_present(), True)


class IoctlEncodingTest(unittest.TestCase):
    def test_struct_size(self):
        # struct spi_ioc_transfer is 32 bytes, on 32 as on 64 bits.
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
        """A wrong BCC (clone badge) must no longer make the read fail."""
        reader = Rc522(FakeRc522Spi(b"\xDE\xAD\xBE\xEF", bad_bcc=True))
        reader.begin()
        self.assertEqual(reader.read_uid(), b"\xDE\xAD\xBE\xEF")

    def test_badge_endormi_reveille_par_wupa(self):
        """A badge that only answers WUPA is still read."""
        reader = Rc522(FakeRc522Spi(b"\x11\x22\x33\x44", wupa_only=True))
        reader.begin()
        self.assertEqual(reader.read_uid(), b"\x11\x22\x33\x44")

    def test_crc_a_vecteur_halt(self):
        """The CRC_A of HALT is 57 CD: reference from the ISO 14443-3 sheet."""
        self.assertEqual(crc_a_software(b"\x50\x00"), b"\x57\xCD")

    def test_selection_meme_si_le_coprocesseur_est_faux(self):
        """The selection CRC must not depend on the reader coprocessor."""
        reader = Rc522(FakeRc522Spi(b"\x77\x00\x00\x00", broken_crc=True))
        reader.begin()
        self.assertEqual(reader.read_uid(), b"\x77\x00\x00\x00")

    def test_trace_montre_une_selection_sans_reponse(self):
        """A card silent on selection: the trace shows the full frame sent."""
        spi = FakeRc522Spi(b"\x77\x00\x00\x00")
        original = spi._respond

        def silencieux(payload):
            if len(payload) == 3 and payload[0] == 0x08:   # select answer
                spi.irq = 0x01                              # TIMER: no answer
                spi.fifo.clear()
                return
            original(payload)

        spi._respond = silencieux  # type: ignore[method-assign]
        reader = Rc522(spi)
        reader.begin()
        trace = {}
        self.assertIsNone(reader.read_uid(trace=trace))
        trames = [step["tx"][:4] for step in trace["steps"]]
        self.assertIn("9370", trames)
        self.assertEqual(trace["crc_sw"], trace["crc_hw"])

    def test_clone_qui_exige_son_bcc_errone(self):
        """A clone that compares the received BCC is read by the received-BCC strategy."""
        spi = FakeRc522Spi(b"\x36\x00\x00\x00", bad_bcc=True)
        spi.only_received_bcc = True
        reader = Rc522(spi)
        reader.begin()
        trace = {}
        self.assertEqual(reader.read_uid(trace=trace), b"\x36\x00\x00\x00")
        self.assertEqual(trace.get("strategie"), "bcc-recu")
        self.assertEqual(trace.get("bcc_recu"), "00")

    def test_badge_normal_utilise_le_bcc_recalcule(self):
        """A badge that recomputes the BCC goes through the recomputed strategy."""
        reader = Rc522(FakeRc522Spi(b"\x36\x00\x00\x00", bad_bcc=True))
        reader.begin()
        trace = {}
        self.assertEqual(reader.read_uid(trace=trace), b"\x36\x00\x00\x00")
        self.assertEqual(trace.get("strategie"), "bcc-recalcule")

    def test_uid_stable_si_la_selection_echoue(self):
        """A clone silent on selection is read after three identical frames."""
        spi = FakeRc522Spi(b"\x36\x00\x00\x00", bad_bcc=True)
        original = spi._respond

        def sans_sak(payload):
            if len(payload) == 3 and payload[0] == 0x08:
                spi.irq = 0x01
                spi.fifo.clear()
                return
            original(payload)

        spi._respond = sans_sak  # type: ignore[method-assign]
        reader = Rc522(spi)
        reader.begin()
        trace = {}
        self.assertIsNone(reader.read_uid(trace=trace))      # 1re trame
        self.assertIsNone(reader.read_uid(trace=trace))      # 2e
        self.assertEqual(reader.read_uid(trace=trace), b"\x36\x00\x00\x00")
        self.assertEqual(trace.get("strategie"), "anticollision-stable")

    def test_une_trame_differente_ne_compte_pas(self):
        """Disturbed reads must never become a badge."""
        spi = FakeRc522Spi(b"\x36\x00\x00\x00", bad_bcc=True)
        original = spi._respond

        def sans_sak(payload):
            if len(payload) == 3 and payload[0] == 0x08:
                spi.irq = 0x01
                spi.fifo.clear()
                return
            original(payload)

        spi._respond = sans_sak  # type: ignore[method-assign]
        reader = Rc522(spi)
        reader.begin()
        self.assertIsNone(reader.read_uid())
        spi.uid = b"\x37\x00\x00\x00"      # another badge: the series is broken
        self.assertIsNone(reader.read_uid())
        self.assertIsNone(reader.read_uid())
        self.assertEqual(reader.read_uid(), b"\x37\x00\x00\x00")

    def test_trace_des_trames(self):
        """The trace describes the sent frame and the answer, for diagnostics."""
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
        # Same badge read again immediately: ignored (debounce)
        self.assertIsNone(reader.read_uid())

    def test_lecteur_sans_anti_rebond(self):
        spi = FakeRc522Spi(b"\x01\x02\x03\x04")
        reader = Rc522Reader(spi, cooldown_s=0.0)
        reader.start()
        self.assertEqual(reader.read_uid(), "01020304")
        self.assertEqual(reader.read_uid(), "01020304")


if __name__ == "__main__":
    unittest.main()
