"""Driver for the MFRC522 RFID reader (RC522 module, e.g. nf-SL001).

The chip is driven over SPI: each transaction sends an address byte
(bit 7 = read) followed by a data byte. The whole identification sequence
(REQA -> anticollision -> select -> halt) follows the NXP datasheet.

The module has no dependency: it simply receives an SPI object exposing
``transfer(bytes) -> bytes`` (see ``spi_port.py``).
"""

from __future__ import annotations

import time

# ---------------------------------------------------------------------------
# Registres
# ---------------------------------------------------------------------------
REG_COMMAND = 0x01
REG_COM_IRQ = 0x04
REG_DIV_IRQ = 0x05
REG_ERROR = 0x06
REG_STATUS2 = 0x08
REG_FIFO_DATA = 0x09
REG_FIFO_LEVEL = 0x0A
REG_CONTROL = 0x0C
REG_BIT_FRAMING = 0x0D
REG_COLL = 0x0E
REG_MODE = 0x11
REG_TX_MODE = 0x12
REG_RX_MODE = 0x13
REG_TX_CONTROL = 0x14
REG_TX_ASK = 0x15
REG_TX_SEL = 0x16
REG_RX_SEL = 0x17
REG_RX_THRESHOLD = 0x18
REG_DEMOD = 0x19
REG_MF_TX = 0x1C
REG_MF_RX = 0x1D
REG_SERIAL_SPEED = 0x1F
REG_CRC_RESULT_H = 0x21
REG_CRC_RESULT_L = 0x22
REG_MOD_WIDTH = 0x24
REG_T_MODE = 0x2A
REG_T_PRESCALER = 0x2B
REG_T_RELOAD_H = 0x2C
REG_T_RELOAD_L = 0x2D
REG_VERSION = 0x37

# ---------------------------------------------------------------------------
# Commandes
# ---------------------------------------------------------------------------
CMD_IDLE = 0x00
CMD_CALC_CRC = 0x03
CMD_TRANSCEIVE = 0x0C
CMD_SOFT_RESET = 0x0F

# ---------------------------------------------------------------------------
# ISO/IEC 14443-3 protocol constants (type A)
# ---------------------------------------------------------------------------
PICC_REQA = 0x26
PICC_WUPA = 0x52
PICC_SEL_CL1 = 0x93
PICC_SEL_CL2 = 0x95
PICC_SEL_CL3 = 0x97
PICC_HALTA = 0x50
PICC_NVB_ANTICOLL = 0x20
PICC_NVB_SELECT = 0x70

#: ComIrqReg bits
IRQ_TIMER = 0x01
IRQ_ERR = 0x02
IRQ_IDLE = 0x10
IRQ_RX = 0x20
IRQ_TX = 0x40

#: ErrorReg bits
ERR_PROTOCOL = 0x01
ERR_PARITY = 0x02
ERR_CRC = 0x04
ERR_COLL = 0x08
ERR_BUFFER_OVFL = 0x10

#: SAK "cascade" bit: the UID continues at the next level.
SAK_CASCADE = 0x04

# ---------------------------------------------------------------------------
# Badge memory (portable cards: the game is written in the badge)
# ---------------------------------------------------------------------------
CMD_MF_AUTHENT = 0x0E
STATUS2_CRYPTO1_ON = 0x08
PICC_AUTH_KEY_A = 0x60
PICC_READ = 0x30
PICC_WRITE_CLASSIC = 0xA0
PICC_WRITE_PAGE = 0xA2

#: Factory keys of MIFARE Classic cards (transport key first).
DEFAULT_KEYS = (
    bytes.fromhex("FFFFFFFFFFFF"),
    bytes.fromhex("A0A1A2A3A4A5"),
    bytes.fromhex("D3F7D3F7D3F7"),
    bytes(6),
)
#: MIFARE Classic data blocks used: sectors 1 and 2 (block 0 holds the
#: manufacturer data, every 4th block holds the keys).
CLASSIC_BLOCKS = (4, 5, 6, 8, 9, 10)
#: First user page of Ultralight / NTAG badges.
FIRST_PAGE = 4
#: Room used in the badge (Ultralight: 48 bytes, NTAG213 and Classic: more).
MEMORY_BYTES = 96


def crc_a_software(data) -> bytes:
    """CRC_A ISO/IEC 14443-3 (0x6363, polynomial 0x8408, least significant first).

    Checkable reference: the CRC of HALT (50 00) is 57 CD. We do not rely on
    the MFRC522 coprocessor for this: the selection is too important to depend
    on a computation whose state we do not control.
    """
    crc = 0x6363
    for byte in bytes(data):
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


class Rc522Error(Exception):
    """Communication error with the reader."""


class Rc522:
    """Low-level MFRC522 driver."""

    def __init__(self, spi, log=None):
        self.spi = spi
        self.log = log
        self.version = None
        #: Last anticollision frame seen, to recognize a stable badge that
        #: never answers the selection (clones).
        self._last_frame = None
        self._frame_count = 0

    # ------------------------------------------------------------- bas niveau
    def _write(self, register: int, value: int) -> None:
        self.spi.transfer(bytes([(register << 1) & 0x7E, value & 0xFF]))

    def _read(self, register: int) -> int:
        answer = self.spi.transfer(bytes([((register << 1) & 0x7E) | 0x80, 0x00]))
        return answer[1] if len(answer) > 1 else 0

    def _write_many(self, register: int, data) -> None:
        payload = bytes([(register << 1) & 0x7E]) + bytes(data)
        self.spi.transfer(payload)

    def _read_many(self, register: int, count: int) -> bytes:
        if count <= 0:
            return b""
        answer = self.spi.transfer(bytes([((register << 1) & 0x7E) | 0x80]) + bytes(count))
        return answer[1:]

    def _set_bits(self, register: int, mask: int) -> None:
        self._write(register, self._read(register) | mask)

    def _clear_bits(self, register: int, mask: int) -> None:
        self._write(register, self._read(register) & (~mask & 0xFF))

    # ------------------------------------------------------------------ init
    def soft_reset(self) -> None:
        self._write(REG_COMMAND, CMD_SOFT_RESET)
        time.sleep(0.05)
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            if not (self._read(REG_COMMAND) & 0x10):  # bit PowerDown
                return
            time.sleep(0.005)
        raise Rc522Error("le lecteur ne repond pas apres un reset logiciel")

    def antenna_on(self) -> None:
        value = self._read(REG_TX_CONTROL)
        if (value & 0x03) != 0x03:
            self._write(REG_TX_CONTROL, value | 0x03)

    def antenna_off(self) -> None:
        self._clear_bits(REG_TX_CONTROL, 0x03)

    def begin(self) -> int:
        """Initializes the chip and returns the VersionReg register value."""
        self.soft_reset()
        self._reset_baud_rates()
        self._write(REG_T_MODE, 0x80)          # TAuto: the timer starts by itself
        self._write(REG_T_PRESCALER, 0xA9)     # f_timer = 40 kHz
        self._write(REG_T_RELOAD_H, 0x03)      # 0x03E8 = 1000 -> 25 ms
        self._write(REG_T_RELOAD_L, 0xE8)
        self._write(REG_TX_ASK, 0x40)          # modulation ASK 100 %
        self._write(REG_MODE, 0x3D)            # CRC 0x6363
        self.antenna_on()
        self.version = self._read(REG_VERSION)
        return self.version

    def read_version(self) -> int:
        """Reads VersionReg (0x37) again: bus integrity at a given speed.

        Used by the automatic tuning to compare SPI speeds without needing a
        badge on the reader.
        """
        return self._read(REG_VERSION)

    # --------------------------------------------------------- transactions
    def _transceive(self, data, tx_last_bits: int = 0, timeout_s: float = 0.05, trace=None,
                    etape: str = ""):
        """Sends ``data`` and returns (received_bytes, valid_bits) or None.

        ``trace`` (optional dict) receives the sent frame, the raw answer and
        ErrorReg: this is what makes it possible to diagnose a card that answers
        but whose identification fails.

        The answer is accepted as soon as it holds bytes: clone cards sometimes
        raise an error flag while the frame is still usable, and the selection
        (checked afterwards) is what really validates the UID.
        """
        step = None
        if trace is not None:
            step = {"tx": bytes(data).hex().upper(), "rx": "", "err": "", "etape": etape}
            trace.setdefault("steps", []).append(step)
        self._write(REG_COMMAND, CMD_IDLE)
        self._write(REG_COM_IRQ, 0x7F)          # clear the flags
        self._write(REG_FIFO_LEVEL, 0x80)       # flush the FIFO
        self._write_many(REG_FIFO_DATA, data)
        self._write(REG_BIT_FRAMING, tx_last_bits & 0x07)
        self._write(REG_COMMAND, CMD_TRANSCEIVE)
        self._write(REG_BIT_FRAMING, (tx_last_bits & 0x07) | 0x80)  # StartSend

        deadline = time.monotonic() + timeout_s
        while True:
            irq = self._read(REG_COM_IRQ)
            if irq & (IRQ_RX | IRQ_IDLE):
                break
            if irq & IRQ_TIMER:
                self._write(REG_BIT_FRAMING, tx_last_bits & 0x07)
                if step is not None:
                    step["err"] = "pas de reponse (timer)"
                return None
            if time.monotonic() > deadline:
                self._write(REG_BIT_FRAMING, tx_last_bits & 0x07)
                self._write(REG_COMMAND, CMD_IDLE)
                if step is not None:
                    step["err"] = "pas de reponse (delai)"
                return None

        self._write(REG_BIT_FRAMING, tx_last_bits & 0x07)

        error = self._read(REG_ERROR)
        length = self._read(REG_FIFO_LEVEL) & 0x7F
        payload = self._read_many(REG_FIFO_DATA, length)
        valid_bits = self._read(REG_CONTROL) & 0x07
        if step is not None:
            step["rx"] = payload.hex().upper()
            step["err"] = "0x%02X" % error
        if not payload:
            return None
        return payload, valid_bits

    def crc_a(self, data) -> bytes:
        """Computes CRC_A (ISO 14443-3) with the MFRC522 coprocessor.

        Returns both bytes in transmission order (least significant first), like
        the reference library does.
        """
        self._write(REG_COMMAND, CMD_IDLE)
        self._write(REG_DIV_IRQ, 0x04)          # efface CRCIRq
        self._write(REG_FIFO_LEVEL, 0x80)       # flush the FIFO
        self._write_many(REG_FIFO_DATA, data)
        self._write(REG_COMMAND, CMD_CALC_CRC)

        deadline = time.monotonic() + 0.09
        while True:
            if self._read(REG_DIV_IRQ) & 0x04:
                self._write(REG_COMMAND, CMD_IDLE)
                low = self._read(REG_CRC_RESULT_L)
                high = self._read(REG_CRC_RESULT_H)
                return bytes([low, high])
            if time.monotonic() > deadline:
                self._write(REG_COMMAND, CMD_IDLE)
                raise Rc522Error("calcul du CRC_A impossible")

    def _reset_baud_rates(self) -> None:
        """Resets the modulation registers to their default values."""
        self._write(REG_TX_MODE, 0x00)
        self._write(REG_RX_MODE, 0x00)
        self._write(REG_MOD_WIDTH, 0x26)

    # ----------------------------------------------------------- commandes
    def request(self, mode: int = PICC_REQA):
        """REQA/WUPA: returns the ATQA (2 bytes) or None when there is no badge."""
        self._reset_baud_rates()
        result = self._transceive(bytes([mode]), tx_last_bits=7)
        if result is None:
            return None
        payload, _ = result
        return payload if len(payload) >= 2 else None

    def _anticollision(self, command: int, trace=None):
        """Anticollision: returns the 5 bytes (partial UID + BCC) or None.

        The returned BCC is not checked here: some clone badges compute it wrong,
        and the following selection is redone with a recomputed BCC anyway. The
        length and the selection remain the real checks.
        """
        result = self._transceive(bytes([command, PICC_NVB_ANTICOLL]), trace=trace)
        if result is None:
            return None
        payload, _ = result
        if len(payload) < 5:
            return None
        return bytes(payload[:5])

    def _select(self, command: int, uid_with_bcc, trace=None, etape: str = "",
                crc_materiel: bool = False) -> "int | None":
        """Selection: returns the SAK (1 byte) or None.

        Two variants are tried by ``read_uid``:
        * CRC_A computed in software (ISO reference, independent of the chip);
        * CRC_A appended by the coprocessor (TxCRCEn), for badges that only answer
          that form of frame.
        """
        frame = bytes([command, PICC_NVB_SELECT]) + bytes(uid_with_bcc)
        if crc_materiel:
            # TxCRCEn = bit 7 of TxModeReg: the chip appends the CRC itself
            # (the low byte must then not be sent).
            self._set_bits(REG_TX_MODE, 0x80)
            try:
                result = self._transceive(frame, trace=trace, etape=etape + "-crc-hw")
            finally:
                self._clear_bits(REG_TX_MODE, 0x80)
        else:
            crc = crc_a_software(frame)
            if trace is not None:
                trace["crc_sw"] = crc.hex().upper()
                try:
                    trace["crc_hw"] = self.crc_a(frame).hex().upper()
                except Rc522Error as exc:
                    trace["crc_hw"] = "erreur : %s" % exc
            result = self._transceive(frame + crc, trace=trace, etape=etape + "-crc-sw")
        if result is None:
            return None
        payload, _ = result
        return payload[0] if payload else None

    def reset_field(self, pause_s: float = 0.004) -> None:
        """Turns the field off then on again: every badge goes back to IDLE.

        More reliable than HALT for clone badges: after a HALT, some no longer
        answer WUPA and stay silent until they have left the field (which is
        exactly what made a badge look invisible).
        """
        try:
            self.antenna_off()
            time.sleep(max(0.001, float(pause_s)))
            self.antenna_on()
        except (Rc522Error, OSError):
            pass

    def halt(self) -> None:
        # The badge does not answer HALT: the timeout is expected.
        frame = bytes([PICC_HALTA, 0x00])
        self._transceive(frame + crc_a_software(frame), timeout_s=0.03)

    def read_uid(self, trace=None):
        """Reads the UID of the badge on the reader (4 or 7 bytes), or None.

        Several strategies are tried, because clone badges differ on two points:
        the BCC they expect in the select frame (the one they return, or the one
        recomputed from the UID) and how the CRC must be appended (by us, or by
        the chip). A genuine card accepts the first one; a clone often accepts
        another. The trace tells which one worked.
        """
        strategies = (
            ("bcc-recu", False, False),
            ("bcc-recalcule", True, False),
            ("bcc-recalcule-crc-materiel", True, True),
        )
        derniere = None
        for tentative, mode in enumerate((PICC_REQA, PICC_WUPA, PICC_REQA)):
            if tentative == 2 and derniere is None:
                # Two rounds without any answer: the badge may have stayed stuck
                # (HALT from a previous version). A field cycle puts it back to IDLE
                # without having to remove it.
                self.reset_field()
            atqa = self.request(mode)
            if trace is not None:
                trace["atqa"] = bytes(atqa).hex().upper() if atqa else ""
            if atqa is None:
                continue
            first = self._anticollision(PICC_SEL_CL1, trace)
            if first is None:
                continue
            derniere = first
            if trace is not None:
                trace["anticoll"] = first.hex().upper()
                trace["bcc_recu"] = "%02X" % first[4]
            partie = bytes(first[0:4])
            for nom, recalcule, materiel in strategies:
                bcc = self._bcc(partie) if recalcule else bytes(first[4:5])
                sak = self._select(
                    PICC_SEL_CL1, partie + bcc, trace,
                    etape="select-%s-%s" % (nom, "wupa" if mode == PICC_WUPA else "reqa"),
                    crc_materiel=materiel,
                )
                if sak is None:
                    continue
                if trace is not None:
                    trace["sak"] = "0x%02X" % sak
                    trace["strategie"] = nom
                    trace["tentative"] = tentative + 1
                if sak & SAK_CASCADE:
                    second = self._anticollision(PICC_SEL_CL2, trace)
                    if second is None:
                        break
                    partie2 = bytes(second[0:4])
                    next_sak = self._select(PICC_SEL_CL2, partie2 + self._bcc(partie2), trace,
                                            etape="select2", crc_materiel=materiel)
                    if next_sak is None:
                        break
                    if next_sak & SAK_CASCADE:
                        # 10-byte UID: not supported (extremely rare on badges).
                        if self.log:
                            self.log.warning("Badge a UID 10 octets ignore")
                        return None
                    uid = bytes(first[1:4]) + bytes(second[0:4])
                    self.reset_field()
                    return uid
                uid = bytes(first[0:4])
                self.reset_field()
                return uid
        # Every selection failed: a badge that answers the anticollision in a
        # stable way stays usable (we only need its UID, never its memory). The
        # counter moves one step per read, not per internal attempt.
        if derniere is not None:
            stable = self._stable_uid(derniere)
            if stable is not None:
                if trace is not None:
                    trace["strategie"] = "anticollision-stable"
                self.reset_field()
                return stable
        return None

    def _stable_uid(self, first):
        """UID taken from the anticollision when the selection stays silent.

        Some clone badges never answer the selection. Their anticollision frame,
        however, is perfectly stable: it is only accepted after three identical
        frames, so that a disturbed read is never taken for a badge.
        """
        frame = bytes(first)
        if frame == self._last_frame:
            self._frame_count += 1
        else:
            self._last_frame = frame
            self._frame_count = 1
        if self._frame_count < 3:
            return None
        if frame[0] == 0x88:          # cascaded UID: not supported without selection
            return None
        return frame[0:4]

    @staticmethod
    def _bcc(data) -> bytes:
        """BCC: exclusive or of the sent bytes (ISO/IEC 14443-3)."""
        checksum = 0
        for byte in data:
            checksum ^= byte
        return bytes([checksum])

    def tag_present(self):
        """True if a badge is present, False if there is none, None if silent.

        Three findings led to this shape:

        * **REQA or WUPA.** A badge that has just been selected (or halted) no
          longer answers REQA: asking REQA alone made a badge lying on the reader
          look removed, which started the game again by itself and triggered the
          "badge removed" stop right after a launch.
        * **A field cycle as a last resort.** Some clones get stuck in a state
          that only a field cut wakes them from.
        * **None when the reader does not answer at all.** A silent SPI bus does
          not prove that a badge was removed: nothing is concluded.
        """
        erreurs = 0
        try:
            if self.request(PICC_REQA) is not None:
                return True
        except (Rc522Error, OSError):
            erreurs += 1
        try:
            if self.request(PICC_WUPA) is not None:
                return True
        except (Rc522Error, OSError):
            erreurs += 1
        try:
            self.reset_field()
            if self.request(PICC_REQA) is not None:
                return True
        except (Rc522Error, OSError):
            erreurs += 1
        if erreurs >= 3:
            return None
        return False

    # ------------------------------------------------------- badge memory
    def select_card(self):
        """Selects the badge and keeps it selected: (uid, sak) or None.

        Needed before touching its memory. Badges that never answer the
        selection (some clones) cannot store anything: None.
        """
        for mode in (PICC_REQA, PICC_WUPA):
            if self.request(mode) is None:
                continue
            first = self._anticollision(PICC_SEL_CL1)
            if first is None:
                continue
            part = bytes(first[0:4])
            for recompute, hardware in ((False, False), (True, False), (True, True)):
                bcc = self._bcc(part) if recompute else bytes(first[4:5])
                sak = self._select(PICC_SEL_CL1, part + bcc, crc_materiel=hardware)
                if sak is None:
                    continue
                if not sak & SAK_CASCADE:
                    return part, sak
                second = self._anticollision(PICC_SEL_CL2)
                if second is None:
                    return None
                part2 = bytes(second[0:4])
                sak2 = self._select(PICC_SEL_CL2, part2 + self._bcc(part2), crc_materiel=hardware)
                if sak2 is None or sak2 & SAK_CASCADE:
                    return None
                return bytes(first[1:4]) + part2, sak2
        return None

    def _command(self, data, timeout_s: float = 0.05):
        """Transceive with the CRC_A appended (memory commands)."""
        frame = bytes(data)
        return self._transceive(frame + crc_a_software(frame), timeout_s=timeout_s)

    @staticmethod
    def _is_ack(result) -> bool:
        """A 4-bit ACK (0xA): the badge accepted the command."""
        if result is None:
            return False
        payload, _bits = result
        return bool(payload) and (payload[0] & 0x0F) == 0x0A

    def authenticate(self, block: int, key: bytes, uid: bytes) -> bool:
        """MIFARE Classic authentication with key A (Crypto1 runs in the chip)."""
        self._write(REG_COMMAND, CMD_IDLE)
        self._write(REG_COM_IRQ, 0x7F)
        self._write(REG_FIFO_LEVEL, 0x80)
        self._write_many(REG_FIFO_DATA, bytes([PICC_AUTH_KEY_A, block]) + bytes(key) + bytes(uid[-4:]))
        self._write(REG_COMMAND, CMD_MF_AUTHENT)
        deadline = time.monotonic() + 0.05
        while time.monotonic() < deadline:
            irq = self._read(REG_COM_IRQ)
            if irq & (IRQ_IDLE | IRQ_TIMER | IRQ_ERR):
                break
        return bool(self._read(REG_STATUS2) & STATUS2_CRYPTO1_ON)

    def stop_crypto(self) -> None:
        self._clear_bits(REG_STATUS2, STATUS2_CRYPTO1_ON)

    def read_block(self, address: int):
        """READ: 16 bytes (a Classic block, or 4 Ultralight pages), or None."""
        result = self._command(bytes([PICC_READ, address]))
        if result is None:
            return None
        payload, _bits = result
        return bytes(payload[:16]) if len(payload) >= 16 else None

    def write_classic(self, block: int, data: bytes) -> bool:
        if not self._is_ack(self._command(bytes([PICC_WRITE_CLASSIC, block]))):
            return False
        return self._is_ack(self._command(bytes(data).ljust(16, b"\x00")[:16], timeout_s=0.1))

    def write_page(self, page: int, data: bytes) -> bool:
        return self._is_ack(self._command(bytes([PICC_WRITE_PAGE, page]) + bytes(data).ljust(4, b"\x00")[:4],
                                          timeout_s=0.1))

    def _classic_session(self, block: int, uid: bytes, sector_keys: dict) -> bool:
        """Authenticates the sector of ``block`` (default keys tried in turn)."""
        sector = block // 4
        if sector in sector_keys:
            return True
        for key in DEFAULT_KEYS:
            if self.authenticate(block, key, uid):
                sector_keys[sector] = key
                return True
            # A failed authentication leaves the card in HALT: wake it up.
            self.stop_crypto()
            self.reset_field()
            if self.select_card() is None:
                return False
            sector_keys.clear()
        return False

    def read_memory(self, length: int = MEMORY_BYTES):
        """User memory of the badge (up to ``length`` bytes), or None."""
        selected = self.select_card()
        if selected is None:
            return None
        uid, sak = selected
        data = bytearray()
        try:
            if sak & 0x08:                                    # MIFARE Classic
                keys = {}
                for block in CLASSIC_BLOCKS:
                    if len(data) >= length:
                        break
                    if not self._classic_session(block, uid, keys):
                        return bytes(data) or None
                    chunk = self.read_block(block)
                    if chunk is None:
                        break
                    data += chunk
                    if 0 in chunk:
                        break
            else:                                             # Ultralight / NTAG
                for page in range(FIRST_PAGE, FIRST_PAGE + length // 4, 4):
                    chunk = self.read_block(page)
                    if chunk is None:
                        break
                    data += chunk
                    if 0 in chunk:
                        break
        finally:
            self.stop_crypto()
            self.reset_field()
        return bytes(data[:length])

    def write_memory(self, payload: bytes, expected_uid: bytes = None) -> None:
        """Writes ``payload`` in the user memory; raises Rc522Error on failure."""
        payload = bytes(payload)
        if len(payload) > MEMORY_BYTES:
            raise Rc522Error("donnees trop longues pour le badge (%d octets)" % len(payload))
        selected = self.select_card()
        if selected is None:
            raise Rc522Error("badge absent, ou badge qui ne peut pas garder de donnees")
        uid, sak = selected
        if expected_uid is not None and bytes(uid) != bytes(expected_uid):
            self.reset_field()
            raise Rc522Error("ce n'est pas le bon badge (%s)" % uid.hex().upper())
        try:
            if sak & 0x08:
                keys = {}
                chunks = [payload[i:i + 16] for i in range(0, len(payload), 16)]
                for block, chunk in zip(CLASSIC_BLOCKS, chunks):
                    if not self._classic_session(block, uid, keys):
                        raise Rc522Error("cle du badge inconnue : il est protege")
                    if not self.write_classic(block, chunk):
                        raise Rc522Error("ecriture refusee (bloc %d)" % block)
            else:
                for index in range(0, len(payload), 4):
                    page = FIRST_PAGE + index // 4
                    if not self.write_page(page, payload[index:index + 4]):
                        raise Rc522Error("ecriture refusee (page %d) : badge trop petit ou verrouille" % page)
        finally:
            self.stop_crypto()
            self.reset_field()

    def close(self) -> None:
        try:
            self.antenna_off()
        except Exception:  # noqa: BLE001 - closing must never fail
            pass
        close = getattr(self.spi, "close", None)
        if callable(close):
            close()


class Rc522Reader:
    """Ready-to-use reader: badge debounce + recovery after an error."""

    def __init__(self, spi, log=None, cooldown_s: float = 2.5, on_reset=None):
        self.log = log
        self.rc522 = Rc522(spi, log)
        self.cooldown_s = float(cooldown_s)
        self.on_reset = on_reset
        self._last_uid = None
        self._last_time = 0.0
        self._errors = 0
        self._started = False
        self.version = None

    def start(self) -> int:
        try:
            self.version = self.rc522.begin()
            self._started = True
            self._errors = 0
        except (Rc522Error, OSError) as exc:
            if self.log:
                self.log.error("Initialisation du lecteur RC522 impossible : %s" % exc)
            raise
        if self.log:
            self.log.info("Lecteur RC522 pret (version 0x%02X)" % self.version)
        return self.version

    def _recover(self) -> None:
        self._started = False
        if self.on_reset:
            try:
                self.on_reset()
            except Exception as exc:  # noqa: BLE001 - the reset is best effort
                if self.log:
                    self.log.warning("Reset materiel du RC522 impossible : %s" % exc)
        try:
            self.start()
        except Exception as exc:  # noqa: BLE001 - retried at the next turn
            if self.log:
                self.log.warning("Lecteur RC522 toujours indisponible : %s" % exc)

    def tag_present(self):
        """True if a badge is present, False otherwise, None if the reader is silent.

        Delegates to the driver, which asks REQA **and** WUPA: an already selected
        badge no longer answers REQA, and mistaking it for an absence started the
        game again by itself.
        """
        if not self._started:
            return None
        try:
            return self.rc522.tag_present()
        except (Rc522Error, OSError, AttributeError) as exc:
            if self.log:
                self.log.warning("Presence du badge illisible : %s" % exc)
            return None

    def read_uid(self):
        """Returns the UID (uppercase hex string) of a new badge, otherwise None."""
        if not self._started:
            try:
                self.start()
            except Exception:  # noqa: BLE001 - retried at the next call
                return None
        try:
            raw = self.rc522.read_uid()
            self._errors = 0
        except (Rc522Error, OSError) as exc:
            self._errors += 1
            if self.log:
                self.log.warning("Lecture RFID en echec (%d) : %s" % (self._errors, exc))
            if self._errors >= 3:
                self._recover()
            return None

        if raw is None:
            return None

        uid = raw.hex().upper()
        now = time.monotonic()
        if uid == self._last_uid and (now - self._last_time) < self.cooldown_s:
            return None
        self._last_uid = uid
        self._last_time = now
        if self.log:
            self.log.info("Badge detecte : %s" % ":".join(uid[i:i + 2] for i in range(0, len(uid), 2)))
        return uid

    def read_memory(self):
        """User memory of the badge on the reader (bytes), or None."""
        if not self._started:
            return None
        try:
            return self.rc522.read_memory()
        except (Rc522Error, OSError) as exc:
            if self.log:
                self.log.debug("Memoire du badge illisible : %s" % exc)
            return None

    def write_memory(self, payload: bytes, uid_hex: str = "") -> None:
        """Writes in the badge on the reader; raises Rc522Error when it fails."""
        if not self._started:
            raise Rc522Error("lecteur indisponible")
        expected = bytes.fromhex(uid_hex) if uid_hex else None
        try:
            self.rc522.write_memory(payload, expected)
        except OSError as exc:
            raise Rc522Error(str(exc))

    def close(self) -> None:
        try:
            self.rc522.close()
        except Exception:  # noqa: BLE001
            pass
