"""Liste des dossiers / lecteurs réseau à indexer.

Stockée au niveau machine (data/index_roots.json, partagé entre les sessions du
serveur) : le premier administrateur qui configure un lecteur réseau le rend
disponible pour tous les utilisateurs du même serveur, puisque l'index est lui
aussi partagé. Repli sur DOCS_DIR si aucune configuration.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)


def _file(settings: Settings) -> Path:
    return settings.data_dir / "index_roots.json"


def get_roots(settings: Settings) -> list[Path]:
    f = _file(settings)
    if f.exists():
        # une configuration existe : on la respecte telle quelle, y compris une
        # liste VIDE (l'administrateur a choisi de n'indexer aucun dossier ->
        # Jade fonctionne alors comme un assistant général, sans documents).
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return [Path(p) for p in data.get("roots", []) if str(p).strip()]
        except (OSError, ValueError) as e:
            log.warning("Lecture de %s impossible : %s", f, e)
    return [settings.docs_dir]  # jamais configuré : repli sur le dossier par défaut


def set_roots(settings: Settings, paths: list[str]) -> list[str]:
    """Enregistre la liste (dé-doublonnée, ordre conservé). Retourne la liste."""
    seen: list[str] = []
    for p in paths:
        s = str(p).strip().rstrip("\\/")
        if s and s not in seen:
            seen.append(s)
    f = _file(settings)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"roots": seen}, ensure_ascii=False, indent=2), encoding="utf-8")
    return seen
