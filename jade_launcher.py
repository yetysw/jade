"""Point d'entrée du backend Jade installé (exécutable PyInstaller).

`Jade.exe` (avec ou sans argument `serve`) démarre le backend local, sans
fenêtre : l'interface est l'application native Flutter, qui lance ce backend
en sidecar et s'y connecte sur 127.0.0.1.

L'exécutable est « windowed » (pas de console) : les journaux vont dans le
dossier de logs partagé (%PROGRAMDATA%\\Jade\\logs\\jade.log).
"""

from __future__ import annotations

import logging
import multiprocessing
import sys
from logging.handlers import RotatingFileHandler


def _setup_logging(settings) -> None:
    settings.ensure_dirs()
    handler = RotatingFileHandler(
        settings.log_dir / "jade.log", maxBytes=2_000_000, backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def main() -> int:
    multiprocessing.freeze_support()
    # Application fenêtrée : sys.stdout/stderr valent None. Toute écriture d'une
    # bibliothèque (tqdm, onnxruntime...) sur ces flux planterait le thread
    # concerné — notamment l'extraction mémoire en arrière-plan. On les redirige
    # vers un flux nul inoffensif.
    if sys.stdout is None or sys.stderr is None:
        import io

        devnull = io.StringIO()
        if sys.stdout is None:
            sys.stdout = devnull
        if sys.stderr is None:
            sys.stderr = devnull

    from ragagent.config import load_settings

    settings = load_settings()
    _setup_logging(settings)
    log = logging.getLogger("jade")
    try:
        # Route via la CLI : « Jade.exe » = serve (port auto + fichier de
        # découverte, isolation par session RDS) ; « Jade.exe seal-env » =
        # scellement des secrets du .env (lancé par l'installateur).
        from ragagent.cli import main as cli_main

        argv = sys.argv[1:] or ["serve"]
        if argv == ["serve"] or argv == ["seal-env"]:
            return cli_main(argv)
        log.warning("Argument inconnu %s — démarrage du backend", argv)
        return cli_main(["serve"])
    except Exception:
        log.exception("Démarrage de Jade échoué")
        return 1


if __name__ == "__main__":
    sys.exit(main())
