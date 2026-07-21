"""Délestage mémoire Windows (working set).

Après le démarrage ou une indexation, une grande partie des pages chargées
(poids des modèles ONNX, buffers de parsing) n'est plus consultée. EmptyWorkingSet
rend ces pages au système : la RAM redevient disponible pour les autres
applications du serveur RDS, et les pages encore utiles reviennent à la demande
(coût unique de quelques ms). C'est le comportement attendu d'une application
« invitée » sur un poste partagé.
"""

from __future__ import annotations

import gc
import logging

log = logging.getLogger(__name__)


def trim_working_set() -> None:
    gc.collect()
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # HANDLE = pointeur 64 bits : sans restype explicite, ctypes tronque le
        # pseudo-handle (-1) en int 32 bits -> ERROR_INVALID_HANDLE
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        handle = kernel32.GetCurrentProcess()
        psapi = ctypes.windll.psapi
        psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
        if not psapi.EmptyWorkingSet(handle):
            log.debug("EmptyWorkingSet refusé (err %d)", kernel32.GetLastError())
    except (OSError, AttributeError) as e:
        log.debug("Délestage mémoire indisponible : %s", e)
