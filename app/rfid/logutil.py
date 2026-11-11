"""Journalisation simple : console + fichier avec rotation.

Aucune dependance : le module ``logging`` de la bibliotheque standard ferait
l'affaire, mais une implementation minimale est plus previsible sur un systeme
embarque (et evite les handlers multiples quand le service redemarre).
"""

from __future__ import annotations

import os
import sys
import time

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}


class Logger:
    """Journal thread-safe (verrou implicite : ecriture d'une ligne = un write)."""

    def __init__(
        self,
        path=None,
        level: str = "INFO",
        max_bytes: int = 1048576,
        echo: bool = False,
    ):
        self.path = path
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.level = LEVELS.get(str(level).upper(), 20)
        self.echo = echo or sys.stdout.isatty()
        self._encoding = "utf-8"
        self._prepare()

    # ------------------------------------------------------------------ interne
    def _prepare(self) -> None:
        if not self.path:
            return
        directory = os.path.dirname(self.path)
        if directory:
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError:
                self.path = None

    def _rotate_if_needed(self) -> None:
        try:
            if os.path.getsize(self.path) > self.max_bytes:
                backup = self.path + ".1"
                if os.path.exists(backup):
                    os.remove(backup)
                os.replace(self.path, backup)
        except OSError:
            pass

    def set_level(self, level: str) -> None:
        self.level = LEVELS.get(str(level).upper(), 20)

    # ------------------------------------------------------------------ ecriture
    def log(self, level: str, message: str) -> None:
        if LEVELS.get(level, 20) < self.level:
            return
        line = "%s [%-7s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), level, message)
        if self.echo:
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except (OSError, ValueError):
                self.echo = False
        if not self.path:
            return
        try:
            self._rotate_if_needed()
            with open(self.path, "a", encoding=self._encoding) as handle:
                handle.write(line)
        except OSError:
            # Disque plein, permissions... le service continue de tourner.
            pass

    def debug(self, message: str) -> None:
        self.log("DEBUG", message)

    def info(self, message: str) -> None:
        self.log("INFO", message)

    def warning(self, message: str) -> None:
        self.log("WARNING", message)

    def error(self, message: str) -> None:
        self.log("ERROR", message)

    # Compatibilite avec l'API ``logging``
    warn = warning
