"""Chiffrement au repos.

Sur **Windows** : DPAPI pour les chaînes (conversations) + EFS pour marquer les
dossiers de données comme chiffrés, de façon transparente, lié au compte
propriétaire. Aucune clé à gérer côté application.

Sur **macOS / Linux** : ces API n'existent pas. Le stockage se fait alors en
clair (dégradation contrôlée) — le confinement local (poste, permissions du
système de fichiers) reste la première ligne de défense. Un chiffrement portable
(keyring / cryptography) pourra être ajouté ultérieurement sans changer l'API.

Best-effort partout : on journalise et on continue.
"""

from __future__ import annotations

import base64
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

DPAPI_PREFIX = "dpapi:"
DPAPI_MACHINE_PREFIX = "dpapi-m:"
_WINDOWS = sys.platform == "win32"
_CRYPTPROTECT_LOCAL_MACHINE = 0x4  # clé liée à la MACHINE (tous les comptes)

if _WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data: bytes):
        buf = ctypes.create_string_buffer(data, len(data))
        return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def dpapi_available() -> bool:
    if not _WINDOWS:
        return False
    try:
        return protect("test").startswith(DPAPI_PREFIX)
    except Exception:
        return False


def protect(text: str) -> str:
    """Chiffre une chaîne avec DPAPI (clé dérivée du compte Windows courant).
    Retourne 'dpapi:<base64>'. Lève OSError si indisponible (hors Windows)."""
    if not _WINDOWS:
        raise OSError("DPAPI indisponible (Windows uniquement)")
    blob_in = _blob(text.encode("utf-8"))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptProtectData a échoué")
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return DPAPI_PREFIX + base64.b64encode(out).decode("ascii")


def protect_machine(text: str) -> str:
    """Chiffre une chaîne avec DPAPI **à l'échelle machine** (déchiffrable par
    tout processus de CETTE machine, aucun autre poste). Sert à sceller les
    secrets du .env : nécessaire sur RDS où chaque session utilisateur doit
    pouvoir les lire, tout en rendant le fichier inutilisable s'il est copié
    hors du serveur (sauvegarde, partage, exfiltration du fichier seul)."""
    if not _WINDOWS:
        raise OSError("DPAPI indisponible (Windows uniquement)")
    blob_in = _blob(text.encode("utf-8"))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_LOCAL_MACHINE, ctypes.byref(blob_out)
    ):
        raise OSError("CryptProtectData (machine) a échoué")
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return DPAPI_MACHINE_PREFIX + base64.b64encode(out).decode("ascii")


def unprotect(value: str) -> str:
    """Déchiffre une valeur 'dpapi:<base64>' ou 'dpapi-m:<base64>' (le champ
    machine/utilisateur est encodé dans le blob, l'API est la même). Une valeur
    sans préfixe est renvoyée telle quelle (rétro-compat données en clair)."""
    if value.startswith(DPAPI_MACHINE_PREFIX):
        prefix = DPAPI_MACHINE_PREFIX
    elif value.startswith(DPAPI_PREFIX):
        prefix = DPAPI_PREFIX
    else:
        return value
    if not _WINDOWS:
        return value
    data = base64.b64decode(value[len(prefix):])
    blob_in = _blob(data)
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptUnprotectData a échoué")
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return out.decode("utf-8")


def encrypt_at_rest(path: Path) -> bool:
    """Marque un dossier comme chiffré (EFS). No-op hors Windows."""
    path.mkdir(parents=True, exist_ok=True)
    if not _WINDOWS:
        return False
    try:
        ok = bool(ctypes.windll.advapi32.EncryptFileW(str(path)))
        if not ok:
            err = ctypes.get_last_error()
            log.info("Chiffrement EFS non appliqué à %s (code %s)", path, err)
        return ok
    except (OSError, AttributeError) as e:
        log.info("Chiffrement EFS indisponible pour %s : %s", path, e)
        return False
