"""API du serveur de licences — face client (derrière Cloudflare Tunnel + Access).

Un seul endpoint exposé : POST /api/verify. Réponse d'erreur constante (403
générique) pour ne donner aucun oracle (inconnu vs suspendu vs expiré). Le JWT
retourné ne porte que les claims du client demandeur — jamais d'info sur d'autres.

Lancer : uvicorn licsrv.app:app --host 127.0.0.1 --port 8790
(puis exposer 127.0.0.1:8790 via un tunnel Cloudflare protégé par Access token).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import db, tokens

app = FastAPI(title="Jade License Server", docs_url=None, redoc_url=None)


class VerifyRequest(BaseModel):
    key: str


@app.get("/")
def root():
    return {"app": "jade-licsrv", "api": "ok"}


@app.post("/api/verify")
def verify(req: VerifyRequest):
    row = db.verify_key(req.key.strip())
    if row is None:
        # réponse constante : ni la cause, ni l'existence de la clé n'est révélée
        raise HTTPException(403, "invalid")
    return {"token": tokens.issue(row)}
