"""Ouverture de fichiers / URL / dossiers, portable Windows · macOS · Linux.

Une seule implémentation, avec la commande native de chaque OS — pas de branche
« grandement différente » : juste le lanceur système approprié.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _launch(target: str, *, reveal: bool = False) -> None:
    if sys.platform == "win32":
        if reveal:
            # ATTENTION : « /select, » et le chemin doivent former UN SEUL
            # argument collé (« /select,C:\\dossier\\fichier »). Passés séparément,
            # l'Explorateur ne les recolle pas et affiche « Emplacement non
            # disponible » alors que le chemin existe. On passe donc la ligne de
            # commande complète (pas de shell : CreateProcess la découpe lui-même,
            # et les guillemets couvrent les chemins contenant des espaces).
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
