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
import os

import uvicorn

from .admin import app as admin_app
from .app import app as public_app


async def _run(app, port: int) -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    await uvicorn.Server(config).serve()


async def _main() -> None:
    public_port = int(os.environ.get("LICSRV_PUBLIC_PORT", "8790"))
    admin_port = int(os.environ.get("LICSRV_ADMIN_PORT", "8791"))
    await asyncio.gather(
        _run(public_app, public_port),
        _run(admin_app, admin_port),
    )


if __name__ == "__main__":
    asyncio.run(_main())
