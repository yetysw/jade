"""Serveur de licences : base SQLite, cles Ed25519 et emission/verif des JWT.

Tout est isole dans tmp_path : on remplace les chemins module (_DB_PATH, _PRIV_PATH)
et on ne touche jamais a la vraie base ni a la vraie cle. Aucun reseau.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from licsrv import db, keys, tokens


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirige base et cle privee vers tmp_path (les constantes sont resolues a
    l'import : on les remplace par setattr, les fonctions les relisent a l'appel)."""
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "licenses.db")
    monkeypatch.setattr(keys, "_PRIV_PATH", tmp_path / "license_ed25519.pem")


def _pub_pem() -> str:
    return keys.public_pem()


# --- db.py --------------------------------------------------------------------

def test_create_license_format_et_verif():
    key = db.create_license("Client A", "monthly", 1)
    cid, _, secret = key.partition(".")
    assert cid and secret and "." in key
    row = db.verify_key(key)
    assert row is not None
    assert row["id"] == cid
    assert row["plan"] == "monthly"
    assert row["label"] == "Client A"


def test_create_license_plan_invalide():
    with pytest.raises(ValueError):
        db.create_license("X", "yearly", 12)


def test_verify_key_mauvais_secret_rejete():
    key = db.create_license("Client B", "quarterly", 3)
    cid, _, _ = key.partition(".")
    assert db.verify_key(f"{cid}.mauvais-secret") is None


def test_verify_key_id_inconnu_et_format_invalide():
    assert db.verify_key("inconnu.secret") is None
    assert db.verify_key("sans-point") is None  # pas de separateur


def test_verify_key_licence_inactive_rejetee():
    key = db.create_license("Client C", "monthly", 1)
    cid, _, _ = key.partition(".")
    assert db.set_active(cid, False) is True
    assert db.verify_key(key) is None
    assert db.set_active(cid, True) is True
    assert db.verify_key(key) is not None


def test_verify_key_licence_expiree_rejetee():
    key = db.create_license("Client D", "monthly", 1)
    cid, _, _ = key.partition(".")
    passe = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE licenses SET expires_at=? WHERE id=?", (passe, cid))
    assert db.verify_key(key) is None


def test_verify_key_met_a_jour_last_seen():
    key = db.create_license("Client E", "monthly", 1)
    cid, _, _ = key.partition(".")
    with db.connect() as conn:
        assert conn.execute("SELECT last_seen_at FROM licenses WHERE id=?",
                            (cid,)).fetchone()["last_seen_at"] is None
    db.verify_key(key)
    with db.connect() as conn:
        assert conn.execute("SELECT last_seen_at FROM licenses WHERE id=?",
                            (cid,)).fetchone()["last_seen_at"] is not None


def test_extend_repousse_expiration_et_reactive():
    key = db.create_license("Client F", "monthly", 1)
    cid, _, _ = key.partition(".")
    db.set_active(cid, False)
    with db.connect() as conn:
        avant = conn.execute("SELECT expires_at FROM licenses WHERE id=?",
                            (cid,)).fetchone()["expires_at"]
    assert db.extend(cid, 2) is True
    with db.connect() as conn:
        row = conn.execute("SELECT expires_at, active FROM licenses WHERE id=?",
                          (cid,)).fetchone()
    assert datetime.fromisoformat(row["expires_at"]) > datetime.fromisoformat(avant)
    assert row["active"] == 1  # extend reactive
    assert db.extend("inexistant", 1) is False


def test_set_active_id_inconnu():
    assert db.set_active("inexistant", False) is False


def test_list_licenses():
    db.create_license("Un", "monthly", 1)
    db.create_license("Deux", "quarterly", 3)
    labels = {r["label"] for r in db.list_licenses()}
    assert {"Un", "Deux"} <= labels


# --- keys.py ------------------------------------------------------------------

def test_load_or_create_private_cree_et_est_idempotent(tmp_path):
    assert not keys._PRIV_PATH.exists()
    k1 = keys.load_or_create_private()
    assert keys._PRIV_PATH.exists()
    k2 = keys.load_or_create_private()  # relit le fichier, meme cle
    b1 = k1.private_bytes_raw()
    b2 = k2.private_bytes_raw()
    assert b1 == b2


def test_public_pem_format():
    pem = keys.public_pem()
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert "END PUBLIC KEY" in pem


# --- tokens.py ----------------------------------------------------------------

def _row_for(cid: str) -> sqlite3.Row:
    with db.connect() as conn:
        return conn.execute("SELECT * FROM licenses WHERE id=?", (cid,)).fetchone()


def test_issue_jwt_verifiable_avec_cle_publique():
    key = db.create_license("Client JWT", "monthly", 12)
    cid, _, _ = key.partition(".")
    token = tokens.issue(_row_for(cid))
    claims = jwt.decode(token, _pub_pem(), algorithms=["EdDSA"],
                        options={"require": ["exp", "sub"]})
    assert claims["sub"] == cid
    assert claims["plan"] == "monthly"
    assert claims["iss"] == tokens.ISSUER
    assert "sub_end" in claims


def test_issue_exp_borne_par_le_bail(monkeypatch):
    """sub_end lointain : exp = now + BAIL_DAYS (le bail borne la duree du JWT)."""
    monkeypatch.setattr(tokens, "BAIL_DAYS", 14)
    key = db.create_license("Client Long", "monthly", 12)  # ~360 j
    cid, _, _ = key.partition(".")
    now = datetime.now(timezone.utc)
    claims = jwt.decode(tokens.issue(_row_for(cid)), _pub_pem(),
                        algorithms=["EdDSA"], options={"require": ["exp"]})
    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    attendu = now + timedelta(days=14)
    assert abs((exp - attendu).total_seconds()) < 120


def test_issue_exp_borne_par_fin_abonnement(monkeypatch):
    """sub_end proche (< bail) : exp = sub_end (on ne prolonge pas au-dela)."""
    monkeypatch.setattr(tokens, "BAIL_DAYS", 14)
    key = db.create_license("Client Court", "monthly", 1)
    cid, _, _ = key.partition(".")
    proche = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE licenses SET expires_at=? WHERE id=?", (proche, cid))
    claims = jwt.decode(tokens.issue(_row_for(cid)), _pub_pem(),
                        algorithms=["EdDSA"], options={"require": ["exp"]})
    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    assert abs((exp - datetime.fromisoformat(proche)).total_seconds()) < 5


def test_issue_signature_etrangere_rejetee():
    """Un JWT emis par le serveur ne se verifie pas avec une AUTRE cle publique."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = db.create_license("Client Sig", "monthly", 1)
    cid, _, _ = key.partition(".")
    token = tokens.issue(_row_for(cid))
    autre_pub = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, autre_pub, algorithms=["EdDSA"])
