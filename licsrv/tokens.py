"""Signature des JWT de licence (Ed25519 / EdDSA)."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT[crypto]

from .keys import load_or_create_private

ISSUER = os.environ.get("LICSRV_ISSUER", "jade-licsrv")
# durée du « bail » : le JWT est valable au plus ce nombre de jours, borné par la
# fin d'abonnement. Le client rafraîchit avant expiration ; hors ligne il tolère
# le bail + période de grâce (côté client). Défaut recommandé par le plan.
BAIL_DAYS = int(os.environ.get("LICSRV_BAIL_DAYS", "14"))


def issue(row: sqlite3.Row) -> str:
    now = datetime.now(timezone.utc)
    sub_end = datetime.fromisoformat(row["expires_at"])
    exp = min(now + timedelta(days=BAIL_DAYS), sub_end)
    payload = {
        "iss": ISSUER,
        "sub": row["id"],
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "sub_end": sub_end.isoformat(),
        "plan": row["plan"],
    }
    return jwt.encode(payload, load_or_create_private(), algorithm="EdDSA")
