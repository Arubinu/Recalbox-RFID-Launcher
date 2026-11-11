"""Pilote du lecteur RFID MFRC522 (module RC522, par exemple nf-SL001).

Le composant est pilote en SPI : chaque transaction envoie un octet d'adresse
(bit 7 = lecture) suivi d'un octet de donnees. Toute la sequence d'identification
(REQA -> anticollision -> selection -> halt) suit la fiche technique NXP.

Le module ne necessite aucune dependance : il recoit simplement un objet SPI
exposant ``transfer(octets) -> octets`` (voir ``spi_port.py``).
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
# Constantes de protocole ISO/CEI 14443-3 (type A)
# ---------------------------------------------------------------------------
PICC_REQA = 0x26
PICC_WUPA = 0x52
PICC_SEL_CL1 = 0x93
PICC_SEL_CL2 = 0x95
PICC_SEL_CL3 = 0x97
PICC_HALTA = 0x50
PICC_NVB_ANTICOLL = 0x20
PICC_NVB_SELECT = 0x70

#: Bits de ComIrqReg
IRQ_TIMER = 0x01
IRQ_ERR = 0x02
IRQ_IDLE = 0x10
IRQ_RX = 0x20
IRQ_TX = 0x40

#: Bits de ErrorReg
ERR_PROTOCOL = 0x01
ERR_PARITY = 0x02
ERR_CRC = 0x04
ERR_COLL = 0x08
ERR_BUFFER_OVFL = 0x10

#: Bit "cascade" du SAK : l'UID continue au niveau suivant.
SAK_CASCADE = 0x04


class Rc522Error(Exception):
    """Erreur de communication avec le lecteur."""


class Rc522:
    """Pilote bas niveau du MFRC522."""

    def __init__(self, spi, log=None):
        self.spi = spi
        self.log = log
        self.version = None

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
        """Initialise le composant et retourne la version du registre VersionReg."""
        self.soft_reset()
        self._reset_baud_rates()
        self._write(REG_T_MODE, 0x80)          # TAuto : le timer demarre seul
        self._write(REG_T_PRESCALER, 0xA9)     # f_timer = 40 kHz
        self._write(REG_T_RELOAD_H, 0x03)      # 0x03E8 = 1000 -> 25 ms
        self._write(REG_T_RELOAD_L, 0xE8)
        self._write(REG_TX_ASK, 0x40)          # modulation ASK 100 %
        self._write(REG_MODE, 0x3D)            # CRC 0x6363
        self.antenna_on()
        self.version = self._read(REG_VERSION)
        return self.version

    # --------------------------------------------------------- transactions
    def _transceive(self, data, tx_last_bits: int = 0, timeout_s: float = 0.05):
        """Envoie ``data`` et retourne (octets_recus, bits_valides) ou None."""
        self._write(REG_COMMAND, CMD_IDLE)
        self._write(REG_COM_IRQ, 0x7F)          # efface les drapeaux
        self._write(REG_FIFO_LEVEL, 0x80)       # vide la FIFO
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
                return None
            if time.monotonic() > deadline:
                self._write(REG_BIT_FRAMING, tx_last_bits & 0x07)
                self._write(REG_COMMAND, CMD_IDLE)
                return None

        self._write(REG_BIT_FRAMING, tx_last_bits & 0x07)

        error = self._read(REG_ERROR)
        if error & (ERR_PROTOCOL | ERR_PARITY | ERR_BUFFER_OVFL):
            return None

        length = self._read(REG_FIFO_LEVEL)
        payload = self._read_many(REG_FIFO_DATA, length)
        valid_bits = self._read(REG_CONTROL) & 0x07
        return payload, valid_bits

    def crc_a(self, data) -> bytes:
        """Calcule le CRC_A (ISO 14443-3) avec le coprocesseur du MFRC522.

        Retourne les deux octets dans l'ordre de transmission (poids faible
        d'abord), comme le fait la bibliotheque de reference.
        """
        self._write(REG_COMMAND, CMD_IDLE)
        self._write(REG_DIV_IRQ, 0x04)          # efface CRCIRq
        self._write(REG_FIFO_LEVEL, 0x80)       # vide la FIFO
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
        """Remet les registres de modulation a leurs valeurs par defaut."""
        self._write(REG_TX_MODE, 0x00)
        self._write(REG_RX_MODE, 0x00)
        self._write(REG_MOD_WIDTH, 0x26)

    # ----------------------------------------------------------- commandes
    def request(self, mode: int = PICC_REQA):
        """REQA/WUPA : retourne l'ATQA (2 octets) ou None si aucun badge."""
        self._reset_baud_rates()
        result = self._transceive(bytes([mode]), tx_last_bits=7)
        if result is None:
            return None
        payload, _ = result
        return payload if len(payload) >= 2 else None

    def _anticollision(self, command: int):
        """Anticollision : retourne les 5 octets (UID partiel + BCC) ou None."""
        result = self._transceive(bytes([command, PICC_NVB_ANTICOLL]))
        if result is None:
            return None
        payload, _ = result
        if len(payload) != 5:
            return None
        checksum = 0
        for byte in payload[:4]:
            checksum ^= byte
        if checksum != payload[4]:
            return None
        return payload

    def _select(self, command: int, uid_with_bcc) -> "int | None":
        """Selection : retourne le SAK (1 octet) ou None."""
        frame = bytes([command, PICC_NVB_SELECT]) + bytes(uid_with_bcc)
        try:
            frame += self.crc_a(frame)
        except Rc522Error:
            return None
        result = self._transceive(frame)
        if result is None:
            return None
        payload, _ = result
        return payload[0] if payload else None

    def halt(self) -> None:
        # Le badge ne repond pas a HALT : le temps mort est normal.
        frame = bytes([PICC_HALTA, 0x00])
        try:
            frame += self.crc_a(frame)
        except Rc522Error:
            return
        self._transceive(frame, timeout_s=0.03)

    def read_uid(self):
        """Lit l'UID du badge present (4 ou 7 octets), ou None."""
        if self.request() is None:
            return None

        first = self._anticollision(PICC_SEL_CL1)
        if first is None:
            return None
        sak = self._select(PICC_SEL_CL1, first)
        if sak is None:
            return None

        if sak & SAK_CASCADE:
            second = self._anticollision(PICC_SEL_CL2)
            if second is None:
                return None
            next_sak = self._select(PICC_SEL_CL2, second)
            if next_sak is None:
                return None
            if next_sak & SAK_CASCADE:
                # UID de 10 octets : non gere (extremement rare sur des badges).
                if self.log:
                    self.log.warning("Badge a UID 10 octets ignore")
                return None
            uid = bytes(first[1:4]) + bytes(second[0:4])
            self.halt()
            return uid

        uid = bytes(first[0:4])
        self.halt()
        return uid

    def close(self) -> None:
        try:
            self.antenna_off()
        except Exception:  # noqa: BLE001 - la fermeture ne doit jamais echouer
            pass
        close = getattr(self.spi, "close", None)
        if callable(close):
            close()


class Rc522Reader:
    """Lecteur pret a l'emploi : anti-rebond badge + reprise apres erreur."""

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
            except Exception as exc:  # noqa: BLE001 - le reset est best effort
                if self.log:
                    self.log.warning("Reset materiel du RC522 impossible : %s" % exc)
        try:
            self.start()
        except Exception as exc:  # noqa: BLE001 - on retentera au prochain tour
            if self.log:
                self.log.warning("Lecteur RC522 toujours indisponible : %s" % exc)

    def read_uid(self):
        """Retourne l'UID (chaine hexa majuscule) d'un nouveau badge, sinon None."""
        if not self._started:
            try:
                self.start()
            except Exception:  # noqa: BLE001 - reessai au prochain appel
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

    def close(self) -> None:
        try:
            self.rc522.close()
        except Exception:  # noqa: BLE001
            pass
