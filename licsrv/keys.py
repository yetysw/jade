"""Paire de clés Ed25519 du serveur de licences.

- clé PRIVÉE : uniquement sur le serveur (fichier hors dépôt, ACL restreinte) ;
  signe les JWT de licence.
- clé PUBLIQUE : à embarquer dans le client Jade (constante) pour vérifier les
  JWT 100 % hors ligne. `print_public_key()` l'affiche au format PEM.

Générer une fois : `python -m licsrv.keys`  (crée la privée si absente, imprime la publique).
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_PRIV_PATH = Path(os.environ.get(
    "LICSRV_PRIVATE_KEY", Path(__file__).resolve().parent / "keys" / "license_ed25519.pem"))


def load_or_create_private() -> Ed25519PrivateKey:
    if _PRIV_PATH.exists():
        return serialization.load_pem_private_key(_PRIV_PATH.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    _PRIV_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PRIV_PATH.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:  # durcir les droits (POSIX ; sous Windows utiliser icacls côté déploiement)
        os.chmod(_PRIV_PATH, 0o600)
    except OSError:
        pass
    return key


def public_pem() -> str:
    priv = load_or_create_private()
    return priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


if __name__ == "__main__":
    print("Clé publique à embarquer dans le client (LICENSE_PUBLIC_KEY) :\n")
    print(public_pem())
    print(f"(clé privée : {_PRIV_PATH} — NE JAMAIS versionner ni distribuer)")
