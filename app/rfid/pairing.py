"""Appairage confirme physiquement.

Principe (propose par l'utilisateur, et c'est le bon modele de securite) :

1. la page web depose une **demande** d'appairage — une seule a la fois, valable
   ``PAIRING_WINDOW_S`` secondes ;
2. sur la Recalbox, le service attend un **appui long** sur le bouton physique
   (``CONFIRM_HOLD_S`` secondes) : c'est la preuve de presence ;
3. le service ecrit un **accord** qui porte l'identifiant exact de la demande ;
4. la page echange cet accord contre le jeton, une seule fois.

Le point delicat est la course entre deux demandes : un accord donne pour la
demande A ne peut jamais valider une demande B, car l'identifiant et l'echeance
de la demande sont recopies dans l'accord. Un appui commence avant la creation de
la demande (ou pendant qu'elle expirait) ne compte pas : il doit demarrer
``MIN_GAP_S`` apres la creation de la demande qu'il valide.
"""

from __future__ import annotations

import json
import os
import secrets
import time

# Duree de validite d'une demande d'appairage (secondes).
PAIRING_WINDOW_S = 30.0
# Appui continu demande pour confirmer (secondes).
CONFIRM_HOLD_S = 3.0
# L'appui doit commencer apres la creation de la demande (marge anti-rejeu).
MIN_GAP_S = 0.25

REQUEST_FILENAME = "pair-pending.json"
GRANT_FILENAME = "pair-grant.json"


class PairingError(Exception):
    """Demande refusee (deja en cours, ou delai expire)."""


# ---------------------------------------------------------------------------
# Fichiers d'etat
# ---------------------------------------------------------------------------
# Les etats d'appairage ne doivent pas etre ecrits sur le partage Samba : il est
# accessible en invite, donc n'importe quel poste du reseau pourrait y deposer un
# accord et s'autoriser sans appui sur le bouton. On les place donc dans un
# dossier prive (tmpfs), hors du partage. ``RFID_STATE_DIR`` force un chemin.
STATE_DIR_ENV = "RFID_STATE_DIR"
DEFAULT_STATE_DIR = "/tmp/rfid-launcher-pairing"


def state_dir(home: str) -> str:
    """Dossier des etats d'appairage : prive, et jamais le partage Samba."""
    forced = os.environ.get(STATE_DIR_ENV, "").strip()
    if forced:
        try:
            os.makedirs(forced, exist_ok=True)
        except OSError:
            pass
        return forced
    # Comparaison faite sur une forme normalisee : la meme fonction sert sous
    # Windows (tests, mode simulation) et sur la Recalbox.
    normalise = os.path.abspath(str(home or "")).replace("\\", "/")
    if "/recalbox/share" in normalise:
        try:
            os.makedirs(DEFAULT_STATE_DIR, exist_ok=True)
            try:
                # Dossier prive : le service et l'agent tournent en root.
                os.chmod(DEFAULT_STATE_DIR, 0o700)
            except OSError:
                pass
            probe = os.path.join(DEFAULT_STATE_DIR, ".probe")
            with open(probe, "w", encoding="ascii") as handle:
                handle.write("ok")
            os.remove(probe)
            return DEFAULT_STATE_DIR
        except OSError:
            pass
    return home


def request_path(home: str) -> str:
    return os.path.join(state_dir(home), REQUEST_FILENAME)


def grant_path(home: str) -> str:
    return os.path.join(state_dir(home), GRANT_FILENAME)


def _read(path: str):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _write(path: str, data: dict) -> None:
    """Ecriture atomique : fichier temporaire puis remplacement."""
    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Demande
# ---------------------------------------------------------------------------
def pending(home: str):
    """Demande en cours, ou ``None`` (une demande expiree est effacee)."""
    data = _read(request_path(home))
    if not data:
        return None
    try:
        until = float(data.get("until") or 0)
    except (TypeError, ValueError):
        _remove(request_path(home))
        return None
    if until <= time.time():
        _remove(request_path(home))
        return None
    return data


def create_request(home: str, source: str = "") -> dict:
    """Cree la demande ; leve ``PairingError`` si une autre est en cours."""
    current = pending(home)
    if current:
        remaining = max(0.0, float(current.get("until", 0)) - time.time())
        raise PairingError(
            "une demande d'appairage est deja en attente (%.0f s)" % remaining
        )
    now = time.time()
    request = {
        "id": secrets.token_hex(4).upper(),
        "created": now,
        "until": now + PAIRING_WINDOW_S,
        "source": str(source or ""),
    }
    # Un accord precedent ne doit jamais pouvoir servir pour cette demande.
    _remove(grant_path(home))
    _write(request_path(home), request)
    return request


def cancel(home: str) -> None:
    """Abandonne la demande et l'eventuel accord."""
    _remove(request_path(home))
    _remove(grant_path(home))


# ---------------------------------------------------------------------------
# Accord (cote service, apres appui long)
# ---------------------------------------------------------------------------
def grant(home: str, request: dict, press_started: float) -> bool:
    """Enregistre l'accord du bouton pour *cette* demande.

    Refuse un appui qui a commence avant la creation de la demande : sans cela,
    quelqu'un qui garde le doigt sur le bouton pourrait valider une demande
    arrivee entre-temps.
    """
    if not request:
        return False
    try:
        created = float(request.get("created") or 0)
    except (TypeError, ValueError):
        return False
    if press_started < created + MIN_GAP_S:
        return False
    _write(grant_path(home), {
        "request_id": str(request.get("id") or ""),
        "request_until": float(request.get("until") or 0),
        "press_started": press_started,
        "granted": time.time(),
    })
    return True


def take_grant(home: str, request_id: str) -> bool:
    """Verifie et consomme l'accord (une seule fois).

    L'accord n'est valable que pour l'identifiant fourni et tant que la demande
    correspondante n'a pas expire : une demande suivante ne peut donc pas etre
    validee par l'appui destine a la precedente.
    """
    data = _read(grant_path(home))
    if not data:
        return False
    _remove(grant_path(home))
    if str(data.get("request_id") or "") != str(request_id or ""):
        return False
    try:
        still_valid = float(data.get("request_until") or 0) > time.time()
    except (TypeError, ValueError):
        return False
    return still_valid
