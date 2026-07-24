"""Base SQLite du serveur de licences — volontairement minimale, AUCUNE PII.

Un client = un identifiant opaque + le hash d'un secret + une date d'expiration.
La clé distribuée au client est « <id>.<secret> » ; le serveur ne stocke que le
hash du secret (PBKDF2), donc une fuite de la base ne livre aucune clé utilisable.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DB_PATH = Path(os.environ.get("LICSRV_DB", Path(__file__).resolve().parent / "licenses.db"))
_PBKDF2_ROUNDS = 200_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            id           TEXT PRIMARY KEY,
            secret_hash  TEXT NOT NULL,
            salt         TEXT NOT NULL,
            label        TEXT NOT NULL,
            plan         TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            active       INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL,
            last_seen_at TEXT
        )
        """
    )
    return conn


def _hash(secret: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, _PBKDF2_ROUNDS).hex()


def create_license(label: str, plan: str, months: int) -> str:
    """Crée un client, retourne la clé EN CLAIR (à copier UNE fois)."""
    if plan not in ("monthly", "quarterly"):
        raise ValueError("plan doit être 'monthly' ou 'quarterly'")
    cid = uuid.uuid4().hex
    secret = secrets.token_urlsafe(24)
    salt = os.urandom(16)
    expires = _now() + timedelta(days=30 * months)
    with connect() as conn:
        conn.execute(
            "INSERT INTO licenses(id, secret_hash, salt, label, plan, expires_at, "
            "active, created_at) VALUES (?,?,?,?,?,?,1,?)",
            (cid, _hash(secret, salt), salt.hex(), label, plan,
             expires.isoformat(), _now().isoformat()),
        )
    return f"{cid}.{secret}"


def verify_key(key: str) -> sqlite3.Row | None:
    """Retourne la ligne si la clé est valide, active et non expirée ; sinon None.
    Aucune distinction (inconnu/suspendu/expiré) — pas d'oracle d'énumération."""
    if "." not in key:
        return None
    cid, _, secret = key.partition(".")
    with connect() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE id=?", (cid,)).fetchone()
        if row is None:
            return None
        expected = row["secret_hash"]
        got = _hash(secret, bytes.fromhex(row["salt"]))
        if not hmac.compare_digest(expected, got):
            return None
        if not row["active"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) < _now():
            return None
        conn.execute("UPDATE licenses SET last_seen_at=? WHERE id=?",
                     (_now().isoformat(), cid))
        return row


def extend(cid: str, months: int) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT expires_at FROM licenses WHERE id=?", (cid,)).fetchone()
        if row is None:
            return False
        base = max(datetime.fromisoformat(row["expires_at"]), _now())
        new = base + timedelta(days=30 * months)
        conn.execute("UPDATE licenses SET expires_at=?, active=1 WHERE id=?",
                     (new.isoformat(), cid))
        return True


def set_active(cid: str, active: bool) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE licenses SET active=? WHERE id=?",
                           (1 if active else 0, cid))
        return cur.rowcount > 0


def list_licenses() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, label, plan, expires_at, active, last_seen_at "
            "FROM licenses ORDER BY created_at DESC").fetchall()
