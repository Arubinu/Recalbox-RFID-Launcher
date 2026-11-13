"""SPI-level MFRC522 simulator, to test the driver without hardware.

It reproduces just what the identification sequence needs: command
registers, FIFO, interrupt flags and ISO 14443-3A answers.
"""

from __future__ import annotations

REG_COMMAND = 0x01
REG_COM_IRQ = 0x04
REG_DIV_IRQ = 0x05
REG_ERROR = 0x06
REG_STATUS2 = 0x08
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
                 wupa_only: bool = False, broken_crc: bool = False, card: str = "classic",
                 key: bytes = b"\xff" * 6, pages: int = 16):
        self.uid = bytes(uid) if uid else None
        #: Memory model: "classic" (MIFARE Classic 1K, key A) or "ultralight"
        #: (4-byte pages, ``pages`` in total: 16 for an Ultralight, 45 for an NTAG213).
        self.card = card
        self.key = bytes(key)
        self.pages = pages
        self.memory = {}
        self.status2 = 0
        self.auth_sector = None
        self.pending_block = None
        self.version = version
        #: Some clone badges return a wrong BCC: the driver must still read the
        #: UID (it recomputes the BCC for the selection).
        self.bad_bcc = bad_bcc
        #: Badge that only answers WUPA (halt state).
        self.wupa_only = wupa_only
        #: Faulty CRC coprocessor (returns garbage).
        self.broken_crc = broken_crc
        #: Clone badge that only accepts the BCC it returned (wrong BCC).
        self.only_received_bcc = False
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
        if register == REG_STATUS2:
            return bytes([self.status2])
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
            if value == 0x0E:  # MFAuthent
                self._authenticate()
                return
            self.command = value
            return
        if register == REG_CONTROL:
            self.control = value
            return
        if register == REG_ERROR:
            self.error = value
            return
        if register == REG_STATUS2:
            self.status2 = value
            if not value & 0x08:
                self.auth_sector = None
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

    @staticmethod
    def crc_a(data) -> bytes:
        """CRC_A ISO/IEC 14443-3, computed independently from the driver.

        Both implementations check each other: the driver does not depend on the
        coprocessor, the simulator does not depend on the driver.
        Reference: HALT (50 00) -> 57 CD.
        """
        crc = 0x6363
        for byte in bytes(data):
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
        return bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def _calculate_crc(self) -> None:
        """Real CRC_A of the bytes in the FIFO (like the chip)."""
        if self.broken_crc:
            self.crc = b"\x00\x00"
        else:
            self.crc = self.crc_a(bytes(self.fifo))
        self.div_irq |= 0x04

    def _authenticate(self) -> None:
        """MFAuthent: [0x60, block, key (6), uid (4)] in the FIFO."""
        frame = bytes(self.fifo)
        self.fifo.clear()
        self.irq = IRQ_IDLE
        ok = (self.uid is not None and self.card == "classic" and len(frame) == 12
              and frame[0] == 0x60 and frame[2:8] == self.key and frame[8:12] == self.uid[-4:])
        if ok:
            self.status2 |= 0x08
            self.auth_sector = frame[1] // 4
        else:
            self.status2 &= ~0x08
            self.auth_sector = None

    def _ack(self, ok: bool = True) -> None:
        self._respond(bytes([0x0A if ok else 0x00]))
        self.control = 4                    # 4 valid bits

    def _memory_command(self, frame: bytes) -> bool:
        """READ / WRITE of the badge memory; True when the frame was handled."""
        if self.pending_block is not None:
            block = self.pending_block
            self.pending_block = None
            if len(frame) == 18 and frame[16:18] == self.crc_a(frame[:16]):
                self.memory[block] = frame[:16]
                self._ack()
            else:
                self._ack(False)
            return True
        if len(frame) < 4 or frame[-2:] != self.crc_a(frame[:-2]):
            return False
        command, address = frame[0], frame[1]
        if self.card == "classic":
            authorized = self.auth_sector == address // 4
            if command == 0x30 and len(frame) == 4:
                if not authorized:
                    return False
                data = self.memory.get(address, bytes(16))
                self._respond(data + self.crc_a(data))
                return True
            if command == 0xA0 and len(frame) == 4:
                if not authorized or address % 4 == 3 or address == 0:
                    self._ack(False)
                    return True
                self.pending_block = address
                self._ack()
                return True
            return False
        if command == 0x30 and len(frame) == 4:
            if address >= self.pages:
                self._ack(False)
                return True
            data = b"".join(self.memory.get(page, bytes(4)) for page in range(address, address + 4))
            self._respond(data + self.crc_a(data))
            return True
        if command == 0xA2 and len(frame) == 8:
            if address < 4 or address >= self.pages:
                self._ack(False)
                return True
            self.memory[address] = frame[2:6]
            self._ack()
            return True
        return False

    def read_text(self) -> bytes:
        """Test helper: user memory as written (Classic blocks or pages)."""
        if self.card == "classic":
            return b"".join(self.memory.get(block, bytes(16)) for block in (4, 5, 6, 8, 9, 10))
        return b"".join(self.memory.get(page, bytes(4)) for page in range(4, self.pages))

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
        if self._memory_command(frame):
            return
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
            # SELECT: 2 bytes + UID (4) + BCC (1) + CRC_A (2) = 9 bytes,
            # or 7 bytes when the CRC is appended by the chip (TxCRCEn).
            tx_crc = bool(self.registers.get(0x12, 0) & 0x80)
            if tx_crc:
                frame = frame + self.crc_a(frame)
            self.select_frames.append(frame)
            if len(frame) != 9 or frame[7:9] != self.crc_a(frame[:7]):
                self.irq = IRQ_TIMER  # incomplete frame or wrong CRC: no answer
                return
            # A card checks the BCC of the select frame: the one it recomputes
            # (normal case), or the one it sent (clone whose BCC is wrong).
            attendu = frame[2] ^ frame[3] ^ frame[4] ^ frame[5]
            if self.only_received_bcc and self.bad_bcc:
                attendu = 0
            if frame[6] != attendu:
                self.irq = IRQ_TIMER
                return
            if frame[0] == 0x93:
                sak = 0x04 if len(uid) == 7 else 0x08
            else:
                sak = 0x00
            self._respond(bytes([sak, 0x00, 0x00]))
            return
        self.irq = IRQ_TIMER  # HALT or unknown command: no answer
