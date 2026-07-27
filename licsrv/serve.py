"""Point d'entrée du conteneur : lance les DEUX serveurs dans le même processus.

- App PUBLIQUE (`app.py`, port `LICSRV_PUBLIC_PORT`, défaut 8790) : uniquement
  `POST /api/verify`. C'est ce port que les postes clients joignent (à exposer via
  Cloudflare Tunnel + Access).
- App ADMIN (`admin.py`, port `LICSRV_ADMIN_PORT`, défaut 8791) : web-UI + API de
  gestion. À n'exposer QU'EN LOCAL (le docker-compose la publie sur 127.0.0.1).

Les deux partagent la même base SQLite (`db.py`) et la même clé privée.
"""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from .admin import app as admin_app
from .app import app as public_app

log = logging.getLogger("licsrv.serve")
_ADMIN_TOKEN = os.environ.get("LICSRV_ADMIN_TOKEN", "").strip()


async def _run(app, host: str, port: int) -> None:
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()


async def _main() -> None:
    public_port = int(os.environ.get("LICSRV_PUBLIC_PORT", "8790"))
    admin_port = int(os.environ.get("LICSRV_ADMIN_PORT", "8791"))
    # App publique : joignable depuis l'extérieur du conteneur -> 0.0.0.0.
    public_host = os.environ.get("LICSRV_PUBLIC_HOST", "0.0.0.0")
    # App admin : défaut SÛR = 127.0.0.1 (protège l'exécution bare-metal). Sous
    # Docker, le forwarding impose 0.0.0.0 DANS le conteneur : le compose met
    # LICSRV_ADMIN_HOST=0.0.0.0 et restreint l'exposition via le mapping hôte
    # "127.0.0.1:8791:8791". Ne jamais publier ce port sur une interface publique.
    admin_host = os.environ.get("LICSRV_ADMIN_HOST", "127.0.0.1")
    if admin_host not in ("127.0.0.1", "localhost", "::1") and not _ADMIN_TOKEN:
        log.warning(
            "SECURITE licsrv : l'admin ecoute sur %s (hors loopback) SANS "
            "LICSRV_ADMIN_TOKEN. N'exposez ce port qu'en local (mapping "
            "127.0.0.1:) et definissez un jeton.", admin_host)
    await asyncio.gather(
        _run(public_app, public_host, public_port),
        _run(admin_app, admin_host, admin_port),
    )


if __name__ == "__main__":
    asyncio.run(_main())
