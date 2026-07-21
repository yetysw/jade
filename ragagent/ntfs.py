"""Filtrage des accès NTFS par utilisateur.

L'index vectoriel est partagé entre tous les utilisateurs du serveur, mais un
utilisateur ne doit jamais recevoir d'extrait d'un fichier qu'il n'a pas le
droit de lire sur le disque (document RH, dossier de direction…).

L'application de bureau s'exécute dans la session Windows de l'utilisateur :
tenter d'ouvrir le fichier en lecture reflète fidèlement les ACL NTFS effectives
(héritage, refus explicite, appartenance aux groupes) — bien plus fiable que
`os.access`, qui ignore les ACL sous Windows. Le résultat est mis en cache
(par chemin, TTL court) pour ne pas rouvrir chaque fichier à chaque question.
"""

from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

_TTL = 300.0  # secondes
_CACHE: dict[str, tuple[bool, float]] = {}
_LOCK = threading.Lock()


def _probe(path: str) -> bool:
    """True si le processus (donc l'utilisateur de la session) peut lire le fichier."""
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except PermissionError:
        return False
    except OSError:
        # Fichier hors ligne, verrouillé ou déplacé : ce n'est pas un refus
        # d'ACL. On ne filtre pas (l'extrait est de toute façon déjà dans l'index
        # partagé) — on évite ainsi de masquer un lecteur réseau momentanément
        # indisponible.
        return True


def can_read(path: str | None) -> bool:
    if not path:
        return True  # extrait web ou sans chemin : rien à filtrer
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(path)
        if hit and now - hit[1] < _TTL:
            return hit[0]
    ok = _probe(path)
    with _LOCK:
        _CACHE[path] = (ok, now)
    return ok


def filter_readable(hits: list[dict]) -> tuple[list[dict], int]:
    """Retourne (hits lisibles par l'utilisateur courant, nombre retiré)."""
    kept: list[dict] = []
    removed = 0
    for h in hits:
        path = (h.get("meta") or {}).get("path")
        if can_read(path):
            kept.append(h)
        else:
            removed += 1
    if removed:
        log.info("Filtrage NTFS : %d extrait(s) masqué(s) (droits insuffisants)", removed)
    return kept, removed
