"""Ouverture de fichiers / URL / dossiers, portable Windows · macOS · Linux.

Une seule implémentation, avec la commande native de chaque OS — pas de branche
« grandement différente » : juste le lanceur système approprié.

Contient aussi la copie d'un fichier dans le presse-papier « en tant que
fichier » (Windows : format CF_HDROP), utilisée par le retour utilisateur :
un lien `mailto:` ne peut pas porter de pièce jointe (limitation du standard),
mais l'utilisateur peut coller le fichier directement dans son message.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("jade.openers")


def _launch(target: str, *, reveal: bool = False) -> None:
    if sys.platform == "win32":
        if reveal:
            # ATTENTION : « /select, » et le chemin doivent former UN SEUL
            # argument collé (« /select,C:\\dossier\\fichier »). Passés séparément,
            # l'Explorateur ne les recolle pas et affiche « Emplacement non
            # disponible » alors que le chemin existe. On passe donc la ligne de
            # commande complète (pas de shell : CreateProcess la découpe lui-même,
            # et les guillemets couvrent les chemins contenant des espaces —
            # indispensable pour un compte Windows du type « Jean Dupont »).
            subprocess.Popen(f'explorer /select,"{target}"')
        else:
            os.startfile(target)  # type: ignore[attr-defined]  # Windows uniquement
    elif sys.platform == "darwin":
        subprocess.Popen(["open"] + (["-R"] if reveal else []) + [target])
    else:  # Linux / autres UNIX
        # xdg-open ne sait pas « sélectionner » : on ouvre le dossier parent
        path = str(Path(target).parent) if reveal else target
        subprocess.Popen(["xdg-open", path])


def open_path(path: str | Path) -> None:
    """Ouvre un fichier avec l'application par défaut du système."""
    _launch(str(path))


def open_url(url: str) -> None:
    """Ouvre une URL (http/https/mailto) avec le gestionnaire par défaut."""
    _launch(url)


def reveal_path(path: str | Path) -> None:
    """Affiche le fichier dans l'explorateur de fichiers (sélectionné si possible)."""
    _launch(str(path), reveal=True)


# --------------------------------------------------------------- presse-papier

def copy_file_to_clipboard(path: str | Path) -> bool:
    """Place un fichier dans le presse-papier **en tant que fichier**, pour que
    l'utilisateur n'ait qu'à faire Coller (Ctrl+V) dans son message e-mail.

    Windows : format CF_HDROP (celui qu'utilise l'Explorateur pour copier/coller
    un fichier) — accepté par tous les clients mail (Outlook, Thunderbird,
    webmails dans un navigateur récent). macOS : `POSIX file` via osascript.
    Linux : aucun mécanisme standard, on renvoie False.

    Ne lève jamais : renvoie True si la copie a réussi, False sinon.
    """
    try:
        target = Path(path)
        if not target.is_file():
            log.warning("Presse-papier : fichier introuvable (%s)", target)
            return False
        full = str(target.resolve())
        if sys.platform == "win32":
            return _clipboard_files_windows([full])
        if sys.platform == "darwin":
            # argv évite toute injection dans le script AppleScript
            subprocess.run(
                ["osascript", "-e", "on run argv",
                 "-e", "set the clipboard to POSIX file (item 1 of argv)",
                 "-e", "end run", "--", full],
                check=True, timeout=10,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        log.info("Presse-papier fichier non supporté sur %s", sys.platform)
        return False
    except Exception as e:  # jamais bloquant : le chemin du fichier reste affiché
        log.warning("Copie du fichier dans le presse-papier impossible : %s", e)
        return False


def _clipboard_files_windows(paths: list[str]) -> bool:
    """CF_HDROP : en-tête DROPFILES suivi des chemins UTF-16 séparés par NUL et
    terminés par un NUL supplémentaire. La mémoire allouée est cédée au système
    dès que SetClipboardData réussit (elle survit à l'arrêt du processus)."""
    import ctypes
    from ctypes import wintypes

    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # restype explicite : sans cela ctypes tronque les handles à 32 bits (crash
    # ou corruption en 64 bits).
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    class DROPFILES(ctypes.Structure):
        _fields_ = [
            ("pFiles", wintypes.DWORD),   # décalage du 1er chemin
            ("pt", wintypes.POINT),
            ("fNC", wintypes.BOOL),
            ("fWide", wintypes.BOOL),     # chemins en UTF-16
        ]

    blob = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    header = DROPFILES(pFiles=ctypes.sizeof(DROPFILES), pt=wintypes.POINT(0, 0),
                       fNC=False, fWide=True)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(DROPFILES) + len(blob))
    if not handle:
        log.warning("Presse-papier : GlobalAlloc a échoué (%s)",
                    ctypes.get_last_error())
        return False
    addr = kernel32.GlobalLock(handle)
    if not addr:
        log.warning("Presse-papier : GlobalLock a échoué (%s)",
                    ctypes.get_last_error())
        kernel32.GlobalFree(handle)
        return False
    try:
        ctypes.memmove(addr, ctypes.byref(header), ctypes.sizeof(header))
        ctypes.memmove(addr + ctypes.sizeof(header), blob, len(blob))
    finally:
        kernel32.GlobalUnlock(handle)

    # le presse-papier est une ressource globale : un autre processus peut le
    # tenir une fraction de seconde, on réessaie brièvement.
    opened = False
    for _ in range(10):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        log.warning("Presse-papier : OpenClipboard a échoué (%s)",
                    ctypes.get_last_error())
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_HDROP, handle):
            log.warning("Presse-papier : SetClipboardData a échoué (%s)",
                        ctypes.get_last_error())
            kernel32.GlobalFree(handle)
            return False
    finally:
        user32.CloseClipboard()
    return True
