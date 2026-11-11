"""Acces au bus SPI du Raspberry Pi, sans aucune dependance.

Deux implementations :

* ``SpiDevPort``  : utilise le module Python ``spidev`` s'il existe (il n'est pas
  fourni par defaut sur Recalbox) ;
* ``IoctlSpiPort``: parle directement a l'API ``spidev`` du noyau (ioctl) avec
  ``ctypes``, qui fait partie de la bibliotheque standard. C'est le mode utilise
  sur Recalbox.

Les deux exposent ``transfer(octets) -> octets`` en full-duplex, ce qui suffit au
lecteur MFRC522 (une transaction = 1 octet d'adresse + N octets de donnees).
"""

from __future__ import annotations

import ctypes
import os
import struct

try:  # fcntl n'existe pas sous Windows (developpement / simulation sur PC)
    import fcntl
except ImportError:  # pragma: no cover - depend de la plateforme
    fcntl = None


class SpiError(Exception):
    """Erreur d'ouverture ou de transfert SPI."""


# ---------------------------------------------------------------------------
# Encodage des ioctl du noyau (asm-generic/ioctl.h)
# ---------------------------------------------------------------------------
_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_WRITE = 1

SPI_IOC_MAGIC = ord("k")


def _ioc(direction: int, type_: int, nr: int, size: int) -> int:
    return (
        (direction << _IOC_DIRSHIFT)
        | (type_ << _IOC_TYPESHIFT)
        | (nr << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


SPI_IOC_WR_MODE = _ioc(_IOC_WRITE, SPI_IOC_MAGIC, 1, 1)
SPI_IOC_WR_BITS_PER_WORD = _ioc(_IOC_WRITE, SPI_IOC_MAGIC, 3, 1)
SPI_IOC_WR_MAX_SPEED_HZ = _ioc(_IOC_WRITE, SPI_IOC_MAGIC, 4, 4)

#: Taille de ``struct spi_ioc_transfer`` (identique en 32 et 64 bits).
_STRUCT_SIZE = 32


def spi_ioc_message(count: int) -> int:
    """Numero d'ioctl ``SPI_IOC_MESSAGE(count)``."""
    size = count * _STRUCT_SIZE
    if size >= (1 << _IOC_SIZEBITS):
        raise SpiError("trop de transferts SPI dans un seul ioctl")
    return _ioc(_IOC_WRITE, SPI_IOC_MAGIC, 0, size)


class SpiIocTransfer(ctypes.Structure):
    """Copie de ``struct spi_ioc_transfer`` du noyau."""

    _fields_ = [
        ("tx_buf", ctypes.c_uint64),
        ("rx_buf", ctypes.c_uint64),
        ("len", ctypes.c_uint32),
        ("speed_hz", ctypes.c_uint32),
        ("delay_usecs", ctypes.c_uint16),
        ("bits_per_word", ctypes.c_uint8),
        ("cs_change", ctypes.c_uint8),
        ("tx_nbits", ctypes.c_uint8),
        ("rx_nbits", ctypes.c_uint8),
        ("word_delay_usecs", ctypes.c_uint8),
        ("pad", ctypes.c_uint8),
    ]


def _parse_spidev_path(path: str):
    """``/dev/spidev0.1`` -> (0, 1)."""
    name = os.path.basename(path)
    if not name.startswith("spidev"):
        raise SpiError("nom de peripherique SPI inattendu : %s" % path)
    try:
        bus, device = name[len("spidev"):].split(".")
        return int(bus), int(device)
    except (ValueError, IndexError):
        raise SpiError("nom de peripherique SPI inattendu : %s" % path)


class IoctlSpiPort:
    """Peripherique SPI pilote par ioctl (aucune dependance)."""

    backend = "ioctl"

    def __init__(self, path: str, speed_hz: int = 1000000, mode: int = 0, bits: int = 8):
        if fcntl is None:
            raise SpiError("ioctl SPI indisponible sur cette plateforme")
        self.path = path
        self.speed_hz = int(speed_hz)
        self._fd = -1
        try:
            self._fd = os.open(path, os.O_RDWR)
        except FileNotFoundError:
            raise SpiError(
                "Peripherique SPI introuvable : %s (SPI non active ?)" % path
            )
        except PermissionError:
            raise SpiError("Acces refuse a %s (lancer en root)" % path)
        except OSError as exc:
            raise SpiError("Ouverture de %s impossible : %s" % (path, exc))
        try:
            fcntl.ioctl(self._fd, SPI_IOC_WR_MODE, bytearray(struct.pack("B", mode & 0x03)))
            fcntl.ioctl(self._fd, SPI_IOC_WR_BITS_PER_WORD, bytearray(struct.pack("B", bits)))
            fcntl.ioctl(
                self._fd, SPI_IOC_WR_MAX_SPEED_HZ, bytearray(struct.pack("I", self.speed_hz))
            )
        except OSError as exc:
            self.close()
            raise SpiError("Configuration de %s impossible : %s" % (path, exc))

    def transfer(self, data) -> bytes:
        payload = bytes(data)
        length = len(payload)
        if length == 0:
            return b""
        tx_buffer = (ctypes.c_ubyte * length).from_buffer_copy(payload)
        rx_buffer = (ctypes.c_ubyte * length)()
        message = SpiIocTransfer(
            ctypes.addressof(tx_buffer),
            ctypes.addressof(rx_buffer),
            length,
            self.speed_hz,
            0,
            8,
            0,
            0,
            0,
            0,
            0,
        )
        try:
            fcntl.ioctl(self._fd, spi_ioc_message(1), bytearray(bytes(message)))
        except OSError as exc:
            raise SpiError("Transfert SPI refuse : %s" % exc)
        return bytes(rx_buffer)

    def set_speed(self, speed_hz: int) -> None:
        self.speed_hz = int(speed_hz)
        try:
            fcntl.ioctl(
                self._fd, SPI_IOC_WR_MAX_SPEED_HZ, bytearray(struct.pack("I", self.speed_hz))
            )
        except OSError:
            pass

    def close(self) -> None:
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


class SpiDevPort:
    """Peripherique SPI pilote par le module ``spidev`` (si disponible)."""

    backend = "spidev"

    def __init__(self, path: str, speed_hz: int = 1000000, mode: int = 0, bits: int = 8):
        try:
            import spidev  # type: ignore
        except ImportError:
            raise SpiError("module spidev absent")
        bus, device = _parse_spidev_path(path)
        self.path = path
        self.speed_hz = int(speed_hz)
        self._spi = spidev.SpiDev()
        try:
            self._spi.open(bus, device)
            self._spi.mode = mode
            self._spi.bits_per_word = bits
            self._spi.max_speed_hz = self.speed_hz
        except OSError as exc:
            raise SpiError("Ouverture de %s impossible : %s" % (path, exc))

    def transfer(self, data) -> bytes:
        try:
            return bytes(self._spi.xfer2(list(bytes(data))))
        except OSError as exc:
            raise SpiError("Transfert SPI refuse : %s" % exc)

    def set_speed(self, speed_hz: int) -> None:
        self.speed_hz = int(speed_hz)
        try:
            self._spi.max_speed_hz = self.speed_hz
        except OSError:
            pass

    def close(self) -> None:
        try:
            self._spi.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def open_spi(path: str, speed_hz: int = 1000000) -> object:
    """Ouvre le peripherique SPI en preferant le module ``spidev`` s'il existe."""
    if not os.path.exists(path):
        raise SpiError(
            "Peripherique SPI introuvable : %s\n"
            "Verifiez que 'dtparam=spi=on' est present dans /boot/recalbox-user-config.txt "
            "puis redemarrez." % path
        )
    try:
        return SpiDevPort(path, speed_hz)
    except SpiError as exc:
        if "spidev" not in str(exc):
            raise
    return IoctlSpiPort(path, speed_hz)


class SpiStub:
    """Implementation de secours pour les tests (reponses scriptees)."""

    backend = "stub"

    def __init__(self, responder):
        self._responder = responder

    def transfer(self, data) -> bytes:
        return self._responder(bytes(data))

    def set_speed(self, speed_hz: int) -> None:
        pass

    def close(self) -> None:
        pass
