"""Machine a etats de la licence cote client (ragagent/licensing.py).

Tests deterministes et hors ligne : aucune requete reseau (refresh n'est pas
appele). On genere une paire Ed25519 dans le test avec cryptography, on signe des
JWT courts nous-memes, et on injecte la cle publique dans un stub de Settings.
Le cache d'etat module (status) est reinitialise avant chaque test.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ragagent import licensing


@pytest.fixture(autouse=True)
def _reset_state_cache():
    """status() met l'etat en cache 1 h au niveau module : on repart a zero pour
    que chaque test (dont blocks_usage, qui appelle status sans force) recalcule."""
    licensing._state_cache = None
    licensing._state_at = 0.0
    yield
    licensing._state_cache = None
    licensing._state_at = 0.0


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    priv = Ed25519PrivateKey.generate()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub_pem


def _sign(priv: Ed25519PrivateKey, *, exp: float, sub_end: str = "2030-01-01T00:00:00+00:00",
          sub: str = "client-1", plan: str = "monthly") -> str:
    return jwt.encode(
        {"sub": sub, "exp": int(exp), "sub_end": sub_end, "plan": plan, "iss": "test"},
        priv, algorithm="EdDSA",
    )


def _settings(tmp_path, pub_pem: str, *, enabled: bool = True, grace_days: int = 7):
    """Stub de Settings : licensing n'utilise que ces attributs (duck typing).
    data_dir.parent est le dossier ou sont ecrits license.jwt et le marker."""
    return SimpleNamespace(
        license_enabled=enabled,
        grace_days=grace_days,
        data_dir=tmp_path / "data",
        license_public_key=pub_pem,
    )


def test_off_quand_licence_desactivee(tmp_path):
    _, pub = _keypair()
    s = _settings(tmp_path, pub, enabled=False)
    assert licensing._compute(s) == {"status": "off"}
    assert licensing.blocks_usage(s) is None


def test_grace_initiale_sans_jwt_ni_marker(tmp_path):
    _, pub = _keypair()
    s = _settings(tmp_path, pub)
    st = licensing._compute(s)
    assert st["status"] == "grace"
    assert "attente" in st["detail"]
    assert licensing.blocks_usage(s) is None


def test_active_avec_jwt_valide(tmp_path):
    priv, pub = _keypair()
    s = _settings(tmp_path, pub)
    exp = time.time() + 30 * 86400
    licensing._jwt_path(s).write_text(_sign(priv, exp=exp), encoding="utf-8")
    st = licensing._compute(s)
    assert st["status"] == "active"
    assert st["sub_end"] == "2030-01-01T00:00:00+00:00"
    assert 28 <= st["days_left"] <= 30
    assert licensing.blocks_usage(s) is None


def test_grace_jwt_expire_dans_la_fenetre(tmp_path):
    """JWT expire il y a 1 h, grace_days=7 : on tolere -> grace, usage non bloque."""
    priv, pub = _keypair()
    s = _settings(tmp_path, pub, grace_days=7)
    licensing._jwt_path(s).write_text(_sign(priv, exp=time.time() - 3600), encoding="utf-8")
    st = licensing._compute(s)
    assert st["status"] == "grace"
    assert st["sub_end"] == "2030-01-01T00:00:00+00:00"
    assert licensing.blocks_usage(s) is None


def test_expired_hors_fenetre_de_grace(tmp_path):
    """JWT expire il y a 30 j, grace_days=7 : hors grace -> expired, usage bloque."""
    priv, pub = _keypair()
    s = _settings(tmp_path, pub, grace_days=7)
    licensing._jwt_path(s).write_text(_sign(priv, exp=time.time() - 30 * 86400), encoding="utf-8")
    st = licensing._compute(s)
    assert st["status"] == "expired"
    msg = licensing.blocks_usage(s)
    assert msg and "Abonnement Jade" in msg and "Jade" in msg


def test_suspended_marker_invalid(tmp_path):
    """Le serveur a repondu 403 -> marker 'invalid' -> suspended, quel que soit le JWT."""
    priv, pub = _keypair()
    s = _settings(tmp_path, pub)
    licensing._jwt_path(s).write_text(_sign(priv, exp=time.time() + 30 * 86400), encoding="utf-8")
    licensing._marker_path(s).write_text('{"last": "invalid", "at": 0}', encoding="utf-8")
    st = licensing._compute(s)
    assert st["status"] == "suspended"
    assert licensing.blocks_usage(s) is not None


def test_grace_days_zero_rend_expire_immediatement(tmp_path):
    """grace_days=0 : un bail expire bascule directement en expired (pas de tolerance)."""
    priv, pub = _keypair()
    s = _settings(tmp_path, pub, grace_days=0)
    licensing._jwt_path(s).write_text(_sign(priv, exp=time.time() - 3600), encoding="utf-8")
    assert licensing._compute(s)["status"] == "expired"


def test_signature_etrangere_n_est_pas_active(tmp_path):
    """Un JWT (exp futur) signe par une AUTRE cle n'est pas 'active' : la signature
    est verifiee. exp etant futur, on retombe en grace, pas en active."""
    other_priv, _ = _keypair()
    _, pub = _keypair()  # cle publique differente de celle qui a signe
    s = _settings(tmp_path, pub)
    licensing._jwt_path(s).write_text(
        _sign(other_priv, exp=time.time() + 30 * 86400), encoding="utf-8")
    assert licensing._compute(s)["status"] != "active"


def test_payload_lit_un_jwt_meme_expire(tmp_path):
    """_payload decode le contenu SANS verifier signature/exp (pour lire sub_end)."""
    priv, _ = _keypair()
    token = _sign(priv, exp=time.time() - 10, sub_end="2027-06-30T00:00:00+00:00")
    p = licensing._payload(token)
    assert p["sub_end"] == "2027-06-30T00:00:00+00:00"
    assert p["sub"] == "client-1"
    assert licensing._payload("pas-un-jwt") is None


def test_days_arrondi_plancher_et_zero():
    now = 1_000_000.0
    assert licensing._days(now + 10 * 86400, now) == 10
    assert licensing._days(now + 86400 + 3600, now) == 1   # plancher
    assert licensing._days(now - 5, now) == 0              # jamais negatif
    assert licensing._days(None, now) == 0
