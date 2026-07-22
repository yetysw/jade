"""Préférences utilisateur (drapeaux d'interface), portables Windows/macOS/Linux.

Persistées dans un petit fichier JSON du dossier de configuration de
l'utilisateur (via platformdirs). Local à l'utilisateur courant : aucune donnée
de contenu, seulement des drapeaux (ex. état du mode incognito).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from platformdirs import user_config_dir

log = logging.getLogger(__name__)

_FILE = Path(user_config_dir("Jade", appauthor=False)) / "prefs.json"


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_bool(name: str, default: bool = False) -> bool:
    return bool(_load().get(name, default))


def set_bool(name: str, value: bool) -> None:
    try:
        data = _load()
        data[name] = bool(value)
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log.warning("Écriture de la préférence « %s » échouée : %s", name, e)
