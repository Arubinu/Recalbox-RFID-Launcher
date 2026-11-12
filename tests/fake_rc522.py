"""Simulateur de MFRC522 au niveau SPI, pour tester le pilote sans materiel.

Il reproduit juste ce qui est necessaire a la sequence d'identification :
registres de commande, FIFO, drapeaux d'interruption et reponses ISO 14443-3A.
"""

from __future__ import annotations

REG_COMMAND = 0x01
REG_COM_IRQ = 0x04
REG_DIV_IRQ = 0x05
REG_ERROR = 0x06
REG_FIFO_DATA = 0x09
REG_FIFO_LEVEL = 0x0A
REG_CONTROL = 0x0C
REG_BIT_FRAMING = 0x0D
REG_TX_MODE = 0x12
REG_TX_CONTROL = 0x14
REG_CRC_RESULT_H = 0x21
REG_CRC_RESULT_L = 0x22
REG_VERSION = 0x37

IRQ_TIMER = 0x01
IRQ_IDLE = 0x10
IRQ_RX = 0x20


class FakeRc522Spi:
    """Faux bus SPI : ``uid=None`` simule l'absence de badge."""

    backend = "fake"

    def __init__(self, uid=None, version: int = 0x92, bad_bcc: bool = False,
                 wupa_only: bool = False):
        self.uid = bytes(uid) if uid else None
        self.version = version
        #: Certains badges clones renvoient un BCC faux : le pilote doit lire
        #: quand meme l'UID (il recalcule le BCC pour la selection).
        self.bad_bcc = bad_bcc
        #: Badge qui ne repond qu'a WUPA (etat de veille).
        self.wupa_only = wupa_only
        self.registers = {}
        self.fifo = bytearray()
        self.irq = 0
        self.div_irq = 0
        self.command = 0
        self.error = 0
        self.control = 0
        self.bit_framing = 0
        self.crc = b"\x00\x00"
        self.transactions = 0
        self.select_frames = []

    # ------------------------------------------------------------------ SPI
    def transfer(self, data) -> bytes:
        payload = bytes(data)
        if not payload:
            return b""
        address = payload[0]
        register = (address & 0x7E) >> 1
        if address & 0x80:
            count = len(payload) - 1
            return b"\x00" + bytes(self._read_block(register, count))
        for byte in payload[1:]:
            self._write(register, byte)
        return b"\x00" * len(payload)

    def set_speed(self, speed_hz: int) -> None:
        pass

    def close(self) -> None:
        pass

    # ------------------------------------------------------------- registres
    def _read_block(self, register: int, count: int) -> bytes:
        if count <= 0:
            return b""
        if register == REG_FIFO_DATA:
            values = bytes(self.fifo[:count])
            del self.fifo[:count]
            return values
        if register == REG_FIFO_LEVEL:
            return bytes([min(len(self.fifo), 0xFF)])
        if register == REG_COM_IRQ:
            return bytes([self.irq])
        if register == REG_DIV_IRQ:
            return bytes([self.div_irq])
        if register == REG_CRC_RESULT_L:
            return bytes([self.crc[0]])
        if register == REG_CRC_RESULT_H:
            return bytes([self.crc[1]])
        if register == REG_ERROR:
            return bytes([self.error])
        if register == REG_CONTROL:
            return bytes([self.control])
        if register == REG_BIT_FRAMING:
            return bytes([self.bit_framing])
        if register == REG_VERSION:
            return bytes([self.version])
        if register == REG_COMMAND:
            return bytes([self.command])
        return bytes([self.registers.get(register, 0)] * count)

    def _write(self, register: int, value: int) -> None:
        value &= 0xFF
        if register == REG_FIFO_DATA:
            self.fifo.append(value)
            return
        if register == REG_FIFO_LEVEL:
            if value & 0x80:
                self.fifo.clear()
            return
        if register == REG_COM_IRQ:
            self.irq &= ~value & 0xFF
            return
        if register == REG_DIV_IRQ:
            self.div_irq &= ~value & 0xFF
            return
        if register == REG_BIT_FRAMING:
            self.bit_framing = value
            if value & 0x80:  # StartSend
                self._execute()
            return
        if register == REG_COMMAND:
            if value == 0x0F:  # SoftReset
                self._soft_reset()
                return
            if value == 0x03:  # CalcCRC
                self._calculate_crc()
                return
            self.command = value
            return
        if register == REG_CONTROL:
            self.control = value
            return
        if register == REG_ERROR:
            self.error = value
            return
        self.registers[register] = value

    def _soft_reset(self) -> None:
        self.registers.clear()
        self.fifo.clear()
        self.irq = 0
        self.div_irq = 0
        self.command = 0
        self.error = 0
        self.control = 0
        self.bit_framing = 0
        self.crc = b"\x00\x00"

    def _calculate_crc(self) -> None:
        """Calcule 2 octets deterministes a partir de la FIFO.

        Le simulateur ne verifie pas la valeur du CRC_A (c'est le vrai
        composant qui la calcule) : il verifie que le pilote lit bien les deux
        octets de resultat et les ajoute a la trame.
        """
        low = 0
        high = 0
        for index, byte in enumerate(self.fifo):
            low = (low + byte + index) & 0xFF
            high = (high ^ ((byte << 1) & 0xFF) ^ index) & 0xFF
        self.crc = bytes([low, high])
        self.div_irq |= 0x04

    def _respond(self, payload: bytes) -> None:
        self.fifo = bytearray(payload)
        self.irq = IRQ_RX | IRQ_IDLE
        self.control = 0
        self.error = 0

    # --------------------------------------------------------------- commandes
    def _execute(self) -> None:
        self.transactions += 1
        frame = bytes(self.fifo)
        self.fifo.clear()
        self.irq = 0
        self.control = 0
        self.error = 0
        tx_last_bits = self.bit_framing & 0x07
        self.bit_framing &= 0x07

        if self.command != 0x0C or not frame:  # 0x0C = Transceive
            self.irq = IRQ_IDLE
            return
        if self.uid is None:
            self.irq = IRQ_TIMER
            return

        uid = self.uid
        if frame[:1] == b"\x26" and tx_last_bits == 7:  # REQA
            if self.wupa_only:
                self.irq = IRQ_TIMER
                return
            self._respond(b"\x04\x00")
            return
        if frame[:1] == b"\x52" and tx_last_bits == 7:  # WUPA
            self._respond(b"\x04\x00")
            return
        if frame[:2] == bytes([0x93, 0x20]):  # anticollision niveau 1
            if len(uid) == 7:
                part = bytes([0x88]) + uid[:3]
            else:
                part = uid[:4]
            bcc = 0 if self.bad_bcc else (part[0] ^ part[1] ^ part[2] ^ part[3])
            self._respond(part + bytes([bcc]))
            return
        if frame[:2] == bytes([0x95, 0x20]) and len(uid) == 7:  # niveau 2
            part = uid[3:7]
            bcc = 0 if self.bad_bcc else (part[0] ^ part[1] ^ part[2] ^ part[3])
            self._respond(part + bytes([bcc]))
            return
        if frame[:2] == bytes([0x93, 0x70]) or frame[:2] == bytes([0x95, 0x70]):
            # SELECT : 2 octets + UID (4) + BCC (1) + CRC_A (2) = 9 octets.
            self.select_frames.append(frame)
            if len(frame) != 9 or frame[7:9] != self.crc:
                self.irq = IRQ_TIMER  # trame incomplete ou CRC faux : pas de reponse
                return
            if frame[0] == 0x93:
                sak = 0x04 if len(uid) == 7 else 0x08
            else:
                sak = 0x00
            self._respond(bytes([sak, 0x00, 0x00]))
            return
        self.irq = IRQ_TIMER  # HALT ou commande inconnue : pas de reponse
