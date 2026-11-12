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


def crc_a_software(data) -> bytes:
    """CRC_A ISO/CEI 14443-3 (0x6363, polynome 0x8408, poids faible d'abord).

    Reference verifiable : le CRC du HALT (50 00) vaut 57 CD. On ne depend pas
    du coprocesseur du MFRC522 pour cela : la selection est trop importante pour
    reposer sur un calcul dont on ne maitrise pas l'etat.
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
    def _transceive(self, data, tx_last_bits: int = 0, timeout_s: float = 0.05, trace=None):
        """Envoie ``data`` et retourne (octets_recus, bits_valides) ou None.

        ``trace`` (dict optionnel) recoit la trame envoyee, la reponse brute et
        l'ErrorReg : c'est ce qui permet de diagnostiquer une carte qui repond
        mais dont l'identification echoue.

        On accepte la reponse des qu'elle contient des octets : les cartes
        clones signalent parfois un drapeau d'erreur sans que la trame soit
        inutilisable, et c'est la selection (verifiee ensuite) qui valide
        reellement l'UID.
        """
        step = None
        if trace is not None:
            step = {"tx": bytes(data).hex().upper(), "rx": "", "err": ""}
            trace.setdefault("steps", []).append(step)
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

    def _anticollision(self, command: int, trace=None):
        """Anticollision : retourne les 5 octets (UID partiel + BCC) ou None.

        Le BCC renvoye n'est pas verifie ici : certains badges clones le
        calculent faux, et la selection qui suit de toute facon est refaite avec
        un BCC recalcule. La longueur et la selection restent les vrais
        controles.
        """
        result = self._transceive(bytes([command, PICC_NVB_ANTICOLL]), trace=trace)
        if result is None:
            return None
        payload, _ = result
        if len(payload) < 5:
            return None
        return bytes(payload[:5])

    def _select(self, command: int, uid_with_bcc, trace=None) -> "int | None":
        """Selection : retourne le SAK (1 octet) ou None.

        Le CRC_A est calcule en logiciel : la tablette le verifie, et un CRC faux
        se traduit par un silence total de la carte (aucune erreur cote
        lecteur) — c'est exactement ce qui rendait les badges illisibles.
        """
        frame = bytes([command, PICC_NVB_SELECT]) + bytes(uid_with_bcc)
        crc = crc_a_software(frame)
        if trace is not None:
            trace["crc_sw"] = crc.hex().upper()
            try:
                trace["crc_hw"] = self.crc_a(frame).hex().upper()
            except Rc522Error as exc:
                trace["crc_hw"] = "erreur : %s" % exc
        result = self._transceive(frame + crc, trace=trace)
        if result is None:
            return None
        payload, _ = result
        return payload[0] if payload else None

    def halt(self) -> None:
        # Le badge ne repond pas a HALT : le temps mort est normal.
        frame = bytes([PICC_HALTA, 0x00])
        self._transceive(frame + crc_a_software(frame), timeout_s=0.03)

    def read_uid(self, trace=None):
        """Lit l'UID du badge present (4 ou 7 octets), ou None.

        Deux precautions pour les badges clones : WUPA en secours de REQA, et
        BCC recalcule pour la selection (celui renvoye par la carte n'est pas
        forcement juste, et une selection avec un BCC faux est ignoree par la
        carte).
        """
        for tentative in range(2):
            mode = PICC_REQA if tentative == 0 else PICC_WUPA
            atqa = self.request(mode)
            if trace is not None:
                trace["atqa"] = bytes(atqa).hex().upper() if atqa else ""
            if atqa is None:
                continue
            first = self._anticollision(PICC_SEL_CL1, trace)
            if first is None:
                continue
            partie = bytes(first[0:4])
            sak = self._select(PICC_SEL_CL1, partie + self._bcc(partie), trace)
            if sak is None:
                continue
            if trace is not None:
                trace["sak"] = "0x%02X" % sak
            if sak & SAK_CASCADE:
                second = self._anticollision(PICC_SEL_CL2, trace)
                if second is None:
                    continue
                partie2 = bytes(second[0:4])
                next_sak = self._select(PICC_SEL_CL2, partie2 + self._bcc(partie2), trace)
                if next_sak is None:
                    continue
                if next_sak & SAK_CASCADE:
                    # UID de 10 octets : non gere (extrement rare sur des badges).
                    if self.log:
                        self.log.warning("Badge a UID 10 octets ignore")
                    return None
                uid = bytes(first[1:4]) + bytes(second[0:4])
                self.halt()
                return uid
            uid = bytes(first[0:4])
            self.halt()
            return uid
        return None

    @staticmethod
    def _bcc(data) -> bytes:
        """BCC : ou exclusif des octets transmis (ISO/CEI 14443-3)."""
        checksum = 0
        for byte in data:
            checksum ^= byte
        return bytes([checksum])

    def tag_present(self) -> bool:
        """Vrai si un badge est physiquement pose sur le lecteur.

        Contourne l'anti-rebond : sert au mode "cartouche" a savoir quand le
        badge a vraiment ete retire, pour pouvoir refaire l'action ensuite.
        """
        if not self._started:
            return False
        try:
            return bool(self.rc522.read_uid())
        except (Rc522Error, OSError):
            return False

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
